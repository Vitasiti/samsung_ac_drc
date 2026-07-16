"""Config flow for the Samsung AC (DRC / 2878) integration."""
from __future__ import annotations

import asyncio
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST

from .const import DOMAIN, CONF_TOKEN, CONF_DUID
from .drc_client import SamsungDrcClient, AuthError, DrcError

_LOGGER = logging.getLogger(__name__)

_CONNECT_ERRORS = (DrcError, OSError, asyncio.TimeoutError, asyncio.IncompleteReadError)


class SamsungDrcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle initial setup and reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: self._host})
            return await self.async_step_token()
        return self.async_show_form(
            step_id="user", data_schema=vol.Schema({vol.Required(CONF_HOST): str})
        )

    async def async_step_token(self, user_input=None):
        return self.async_show_menu(step_id="token", menu_options=["capture", "paste"])

    async def async_step_capture(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            _LOGGER.debug("capture: submit received (host=%s)", self._host)
            client = SamsungDrcClient(self._host)
            try:
                token = await client.get_token(power_on_timeout=40)
            except _CONNECT_ERRORS as err:
                _LOGGER.debug("capture: no token (%s: %s)", type(err).__name__, err)
                errors["base"] = "no_token"
            except asyncio.CancelledError:
                _LOGGER.warning("capture: step cancelled before completing")
                raise
            except Exception:  # noqa: BLE001 - diagnostic: surface anything _CONNECT_ERRORS misses
                _LOGGER.exception("capture: unexpected exception escaped _CONNECT_ERRORS")
                errors["base"] = "no_token"
            else:
                return await self._validate_and_finish(token, errors, step="capture")
            finally:
                await client.close()
        else:
            _LOGGER.debug("capture: rendering form (no user_input)")
        _LOGGER.debug("capture: showing form, errors=%s", errors)
        return self.async_show_form(
            step_id="capture", errors=errors, data_schema=vol.Schema({})
        )

    async def async_step_paste(self, user_input=None):
        errors: dict[str, str] = {}
        if user_input is not None:
            return await self._validate_and_finish(
                user_input[CONF_TOKEN], errors, step="paste"
            )
        return self.async_show_form(
            step_id="paste",
            errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
        )

    async def _validate_and_finish(self, token, errors, step):
        """Validate the token and discover the DUID on a SINGLE connection, then
        close it before creating/reloading the entry (the module allows one client)."""
        _LOGGER.debug("validate: connecting to %s to verify token", self._host)
        client = SamsungDrcClient(self._host, token=token)
        try:
            await client.get_state()  # validates authentication
            duid = await client.ensure_duid()  # cached; reuses the same connection
        except AuthError as err:
            _LOGGER.debug("validate: token rejected (%s)", err)
            errors["base"] = "auth"
        except _CONNECT_ERRORS as err:
            _LOGGER.debug("validate: connect failed (%s: %s)", type(err).__name__, err)
            errors["base"] = "cannot_connect"
        except Exception:  # noqa: BLE001 - diagnostic: surface anything _CONNECT_ERRORS misses
            _LOGGER.exception("validate: unexpected exception escaped _CONNECT_ERRORS")
            errors["base"] = "cannot_connect"
        else:
            await client.close()  # close BEFORE _finish (reauth reload reconnects)
            return await self._finish(token, duid)
        finally:
            await client.close()
        schema = (
            vol.Schema({vol.Required(CONF_TOKEN): str})
            if step == "paste"
            else vol.Schema({})
        )
        return self.async_show_form(step_id=step, errors=errors, data_schema=schema)

    async def _finish(self, token, duid):
        await self.async_set_unique_id(duid)
        if self._reauth_entry is not None:
            self.hass.config_entries.async_update_entry(
                self._reauth_entry,
                data={**self._reauth_entry.data, CONF_TOKEN: token, CONF_DUID: duid},
            )
            await self.hass.config_entries.async_reload(self._reauth_entry.entry_id)
            return self.async_abort(reason="reauth_successful")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Samsung AC",
            data={CONF_HOST: self._host, CONF_TOKEN: token, CONF_DUID: duid},
        )

    async def async_step_reauth(self, entry_data):
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._host = entry_data[CONF_HOST]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return self.async_show_menu(
            step_id="reauth_confirm", menu_options=["capture", "paste"]
        )
