"""Pure conversions between HA climate values and DRC attribute strings."""
from __future__ import annotations

MODE_TO_DRC = {"heat": "Heat", "cool": "Cool", "auto": "Auto", "dry": "Dry", "fan_only": "Wind"}
DRC_TO_MODE = {v: k for k, v in MODE_TO_DRC.items()}
FAN_TO_DRC = {"auto": "Auto", "low": "Low", "medium": "Mid", "high": "High"}
DRC_TO_FAN = {v: k for k, v in FAN_TO_DRC.items()}


def tempnow_to_c(raw: str) -> float | None:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return round((v - 32) * 5 / 9, 1) if v > 45 else v


def _to_float(raw):
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def state_to_ha(attrs: dict[str, str]) -> dict:
    power = attrs.get("AC_FUN_POWER", "Off")
    opmode = attrs.get("AC_FUN_OPMODE", "Heat")
    hvac_mode = "off" if power != "On" else DRC_TO_MODE.get(opmode, "heat")
    return {
        "hvac_mode": hvac_mode,
        "current_c": tempnow_to_c(attrs.get("AC_FUN_TEMPNOW", "")),
        "target_c": _to_float(attrs.get("AC_FUN_TEMPSET")),
        "fan_mode": DRC_TO_FAN.get(attrs.get("AC_FUN_WINDLEVEL", "Auto"), "auto"),
    }
