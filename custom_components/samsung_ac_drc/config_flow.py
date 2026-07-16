from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from .const import DOMAIN, CONF_TOKEN, CONF_DUID
from .drc_client import SamsungDrcClient, AuthError, DrcError

class SamsungDrcConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1
    def __init__(self): self._host = None

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            self._host = user_input[CONF_HOST]
            self._async_abort_entries_match({CONF_HOST: self._host})
            return await self.async_step_token()
        return self.async_show_form(step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_HOST): str}))

    async def async_step_token(self, user_input=None):
        return self.async_show_menu(step_id="token", menu_options=["capture", "paste"])

    async def async_step_capture(self, user_input=None):
        errors = {}
        if user_input is not None:
            client = SamsungDrcClient(self._host)
            try:
                token = await client.get_token(power_on_timeout=40)
            except DrcError:
                errors["base"] = "no_token"
            else:
                return await self._finish(token)
            finally:
                await client.close()
        return self.async_show_form(step_id="capture", errors=errors,
            data_schema=vol.Schema({}))  # instructions in strings.json

    async def async_step_paste(self, user_input=None):
        errors = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN]
            client = SamsungDrcClient(self._host, token=token)
            try:
                await client.get_state()  # validates auth
            except AuthError:
                errors["base"] = "auth"
            except DrcError:
                errors["base"] = "cannot_connect"
            else:
                return await self._finish(token)
            finally:
                await client.close()
        return self.async_show_form(step_id="paste", errors=errors,
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}))

    async def _finish(self, token: str):
        client = SamsungDrcClient(self._host, token=token)
        try:
            duid = await client.ensure_duid()
        finally:
            await client.close()
        await self.async_set_unique_id(duid)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title=f"Samsung AC ({self._host})",
            data={CONF_HOST: self._host, CONF_TOKEN: token, CONF_DUID: duid})
