"""Config flow tests.

This module had no coverage at all, which is how a DUID-discovery bug that made
the integration unusable on real hardware reached a release: every failure path
rendered a form, so nothing distinguished "working" from "always fails".
"""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.samsung_ac_drc.const import CONF_DUID, CONF_TOKEN, DOMAIN
from custom_components.samsung_ac_drc.drc_client import AuthError, DrcError

HOST = "192.0.2.10"          # TEST-NET-1, never routable
TOKEN = "TOKEN-1234"
DUID = "AABBCCDDEEFF0000"

CLIENT = "custom_components.samsung_ac_drc.config_flow.SamsungDrcClient"
# Creating an entry makes HA set the integration up for real, which would open a
# socket to the AC. These tests are about the flow, not the setup.
SETUP = "custom_components.samsung_ac_drc.async_setup_entry"


def _client(*, get_token=None, get_state=None, ensure_duid=None):
    """A SamsungDrcClient stub. Each hook is an AsyncMock side effect."""
    stub = AsyncMock()
    stub.get_token = AsyncMock(side_effect=get_token, return_value=TOKEN)
    stub.get_state = AsyncMock(side_effect=get_state, return_value={})
    stub.ensure_duid = AsyncMock(side_effect=ensure_duid, return_value=DUID)
    stub.close = AsyncMock()
    return stub


async def _start(hass: HomeAssistant):
    """Advance the flow to the capture/paste menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["step_id"] == "user"
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )


async def test_paste_creates_the_entry(hass: HomeAssistant) -> None:
    menu = await _start(hass)
    assert menu["type"] == data_entry_flow.FlowResultType.MENU

    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "paste"}
    )
    assert form["step_id"] == "paste"

    with patch(CLIENT, return_value=_client()), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {CONF_TOKEN: TOKEN}
        )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_HOST: HOST, CONF_TOKEN: TOKEN, CONF_DUID: DUID}
    # The IP must not leak into the title -- it is neither stable nor readable.
    assert HOST not in result["title"]


async def test_capture_creates_the_entry(hass: HomeAssistant) -> None:
    menu = await _start(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "capture"}
    )
    assert form["step_id"] == "capture"

    with patch(CLIENT, return_value=_client()), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(form["flow_id"], {})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_TOKEN] == TOKEN


@pytest.mark.parametrize(
    ("raised", "expected"),
    [
        (DrcError("could not discover DUID"), "cannot_connect"),
        (TimeoutError(), "cannot_connect"),
        (OSError(), "cannot_connect"),
        (AuthError("token rejected"), "auth"),
        (ValueError("something unforeseen"), "unknown"),
    ],
)
async def test_paste_surfaces_the_right_error(
    hass: HomeAssistant, raised: Exception, expected: str
) -> None:
    """Every failure must reach the user as a specific message. A DrcError here
    is exactly what the DUID bug raised, and it must not be silent."""
    menu = await _start(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "paste"}
    )

    with patch(CLIENT, return_value=_client(get_state=raised)):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {CONF_TOKEN: TOKEN}
        )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": expected}


async def test_failed_paste_keeps_the_token_in_the_form(hass: HomeAssistant) -> None:
    """Re-typing a token after every failed attempt is needless friction."""
    menu = await _start(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "paste"}
    )

    with patch(CLIENT, return_value=_client(get_state=OSError())):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {CONF_TOKEN: TOKEN}
        )

    suggested = [
        key.description["suggested_value"]
        for key in result["data_schema"].schema
        if getattr(key, "description", None)
    ]
    assert suggested == [TOKEN], "the token should be pre-filled after a failure"


async def test_capture_reports_a_missed_power_cycle(hass: HomeAssistant) -> None:
    menu = await _start(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "capture"}
    )

    with patch(CLIENT, return_value=_client(get_token=TimeoutError())):
        result = await hass.config_entries.flow.async_configure(form["flow_id"], {})

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "no_token"}


async def test_capture_recovers_after_a_failed_attempt(hass: HomeAssistant) -> None:
    """Missing the 40-second window is routine, so a retry must work rather than
    leave the flow wedged."""
    menu = await _start(hass)
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "capture"}
    )

    with patch(CLIENT, return_value=_client(get_token=TimeoutError())):
        failed = await hass.config_entries.flow.async_configure(form["flow_id"], {})
    assert failed["errors"] == {"base": "no_token"}

    with patch(CLIENT, return_value=_client()), patch(SETUP, return_value=True):
        result = await hass.config_entries.flow.async_configure(failed["flow_id"], {})
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY


async def test_the_same_address_is_rejected_immediately(hass: HomeAssistant) -> None:
    """A duplicate host aborts at the first step, without troubling the AC."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: HOST, CONF_TOKEN: TOKEN, CONF_DUID: DUID},
        unique_id=DUID,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: HOST}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_the_same_device_at_a_new_address_is_rejected(hass: HomeAssistant) -> None:
    """The host check cannot catch an AC whose DHCP lease moved, so the DUID
    unique id has to. Otherwise one unit gets two entries fighting over a module
    that accepts a single client."""
    MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "192.0.2.99", CONF_TOKEN: TOKEN, CONF_DUID: DUID},
        unique_id=DUID,
    ).add_to_hass(hass)

    menu = await _start(hass)          # HOST differs from the entry above
    form = await hass.config_entries.flow.async_configure(
        menu["flow_id"], {"next_step_id": "paste"}
    )
    with patch(CLIENT, return_value=_client()):
        result = await hass.config_entries.flow.async_configure(
            form["flow_id"], {CONF_TOKEN: TOKEN}
        )

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "already_configured"
