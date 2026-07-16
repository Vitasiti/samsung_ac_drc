from custom_components.samsung_ac_drc import drc_client as d


def test_parse_attrs():
    xml = ('<Response Type="DeviceState" Status="Okay"><DeviceState><Device DUID="X" '
           'GroupID="AC" ModelID="AC"><Attr ID="AC_FUN_POWER" Type="RW" Value="On"/>'
           '<Attr ID="AC_FUN_TEMPSET" Type="RW" Value="23"/></Device></DeviceState></Response>')
    assert d.parse_attrs(xml) == {"AC_FUN_POWER": "On", "AC_FUN_TEMPSET": "23"}


def test_build_control():
    out = d.build_control("7825AD10BB57", "AC_FUN_POWER", "Off")
    assert out == (b'<Request Type="DeviceControl"><Control CommandID="AC_FUN_POWER" '
                   b'DUID="7825AD10BB57"><Attr ID="AC_FUN_POWER" Value="Off"/></Control></Request>\r\n')


def test_build_auth_and_state():
    assert d.build_auth("T") == b'<Request Type="AuthToken"><User Token="T"/></Request>\r\n'
    assert d.build_state("D") == b'<Request Type="DeviceState" DUID="D"></Request>\r\n'
