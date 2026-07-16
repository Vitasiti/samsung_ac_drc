from __future__ import annotations
from datetime import timedelta
import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .const import DOMAIN, DEFAULT_SCAN_INTERVAL, CONF_TOKEN, CONF_DUID
from .drc_client import SamsungDrcClient, DrcError, AuthError

_LOGGER = logging.getLogger(__name__)

class SamsungDrcCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        self.client = SamsungDrcClient(entry.data["host"], token=entry.data[CONF_TOKEN],
                                       duid=entry.data.get(CONF_DUID))
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL))

    async def _async_update_data(self) -> dict:
        try:
            return await self.client.get_state()
        except AuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except DrcError as err:
            raise UpdateFailed(str(err)) from err
