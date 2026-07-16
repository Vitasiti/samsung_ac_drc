from __future__ import annotations
from homeassistant.components.climate import (ClimateEntity, ClimateEntityFeature, HVACMode, HVACAction)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from . import mappings
from .const import DOMAIN

HVAC_MODES = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL,
              HVACMode.DRY, HVACMode.FAN_ONLY]
# HA HVACMode.HEAT_COOL <-> DRC "Auto"
_HA_TO_DRCMODE = {"heat": "Heat", "cool": "Cool", "heat_cool": "Auto", "dry": "Dry", "fan_only": "Wind"}
_DRCMODE_TO_HA = {"Heat": HVACMode.HEAT, "Cool": HVACMode.COOL, "Auto": HVACMode.HEAT_COOL,
                  "Dry": HVACMode.DRY, "Wind": HVACMode.FAN_ONLY}
_DRCMODE_TO_ACTION = {"Heat": HVACAction.HEATING, "Cool": HVACAction.COOLING,
                      "Dry": HVACAction.DRYING, "Wind": HVACAction.FAN,
                      "Auto": HVACAction.IDLE}

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    async_add_entities([SamsungDrcClimate(entry.runtime_data, entry)])

class SamsungDrcClimate(CoordinatorEntity, ClimateEntity):
    _attr_has_entity_name = True
    _attr_name = None
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_hvac_modes = HVAC_MODES
    _attr_fan_modes = ["auto", "low", "medium", "high"]
    _attr_min_temp = 16
    _attr_max_temp = 32
    _attr_target_temperature_step = 1
    _attr_supported_features = (ClimateEntityFeature.TARGET_TEMPERATURE
                                | ClimateEntityFeature.FAN_MODE
                                | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF)

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.unique_id}_climate"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.unique_id)},
                                  "manufacturer": "Samsung", "name": f"Samsung AC ({entry.data['host']})",
                                  "model": "DRC / 2878"}

    @property
    def _attrs(self): return self.coordinator.data or {}

    @property
    def hvac_mode(self):
        if self._attrs.get("AC_FUN_POWER") != "On": return HVACMode.OFF
        return _DRCMODE_TO_HA.get(self._attrs.get("AC_FUN_OPMODE"), HVACMode.HEAT)

    @property
    def hvac_action(self):
        if self._attrs.get("AC_FUN_POWER") != "On":
            return HVACAction.OFF
        return _DRCMODE_TO_ACTION.get(self._attrs.get("AC_FUN_OPMODE"), HVACAction.IDLE)

    @property
    def current_temperature(self): return mappings.tempnow_to_c(self._attrs.get("AC_FUN_TEMPNOW", ""))
    @property
    def target_temperature(self):
        try: return float(self._attrs.get("AC_FUN_TEMPSET"))
        except (TypeError, ValueError): return None
    @property
    def fan_mode(self): return mappings.DRC_TO_FAN.get(self._attrs.get("AC_FUN_WINDLEVEL"), "auto")

    async def async_set_hvac_mode(self, hvac_mode):
        c = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await c.set_attr("AC_FUN_POWER", "Off")
        else:
            if self._attrs.get("AC_FUN_POWER") != "On":
                await c.set_attr("AC_FUN_POWER", "On")
            await c.set_attr("AC_FUN_OPMODE", _HA_TO_DRCMODE[hvac_mode])
        await self.coordinator.async_request_refresh()

    async def async_set_temperature(self, **kwargs):
        temp = kwargs.get(ATTR_TEMPERATURE)
        if temp is not None:
            await self.coordinator.client.set_attr("AC_FUN_TEMPSET", str(int(round(temp))))
            await self.coordinator.async_request_refresh()

    async def async_set_fan_mode(self, fan_mode):
        await self.coordinator.client.set_attr("AC_FUN_WINDLEVEL", mappings.FAN_TO_DRC[fan_mode])
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self):
        await self.coordinator.client.set_attr("AC_FUN_POWER", "On")
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self): await self.async_set_hvac_mode(HVACMode.OFF)
