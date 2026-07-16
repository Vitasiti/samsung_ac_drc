from custom_components.samsung_ac_drc import mappings as m


def test_tempnow_fahrenheit():
    assert round(m.tempnow_to_c("76"), 1) == 24.4


def test_tempnow_celsius_passthrough():
    assert m.tempnow_to_c("24") == 24.0


def test_state_to_ha_off():
    r = m.state_to_ha({"AC_FUN_POWER": "Off", "AC_FUN_OPMODE": "Heat",
                       "AC_FUN_TEMPSET": "23", "AC_FUN_TEMPNOW": "76", "AC_FUN_WINDLEVEL": "Auto"})
    assert r["hvac_mode"] == "off" and r["target_c"] == 23.0 and r["fan_mode"] == "auto"


def test_state_to_ha_heat():
    r = m.state_to_ha({"AC_FUN_POWER": "On", "AC_FUN_OPMODE": "Wind",
                       "AC_FUN_TEMPSET": "21", "AC_FUN_TEMPNOW": "70", "AC_FUN_WINDLEVEL": "High"})
    assert r["hvac_mode"] == "fan_only" and r["fan_mode"] == "high"
