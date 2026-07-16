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


import asyncio, pytest


async def _proto(host, port):
    reader, writer = await asyncio.open_connection(host, port)
    p = d.DrcProtocol(reader, writer)
    await p.read_greeting()
    return p


async def test_auth_and_state(mock_drc):
    srv, host, port = mock_drc
    srv.state = {"AC_FUN_POWER": "On", "AC_FUN_TEMPSET": "23", "AC_FUN_TEMPNOW": "76"}
    p = await _proto(host, port)
    await p.authenticate("tok")
    st = await p.get_state("7825AD10BB57")
    assert st["AC_FUN_POWER"] == "On" and st["AC_FUN_TEMPSET"] == "23"


async def test_control_roundtrip(mock_drc):
    srv, host, port = mock_drc
    p = await _proto(host, port); await p.authenticate("t")
    await p.set_attr("7825AD10BB57", "AC_FUN_POWER", "Off")
    assert srv.state["AC_FUN_POWER"] == "Off"


async def test_get_token(mock_drc):
    srv, host, port = mock_drc
    srv.token_after_power_on = "ABC-123"
    p = await _proto(host, port)
    assert await p.get_token(power_on_timeout=2) == "ABC-123"


async def test_client_serialises_and_reconnects(mock_drc):
    srv, host, port = mock_drc
    srv.state = {"AC_FUN_POWER": "On"}
    async def connect():
        return await asyncio.open_connection(host, port)
    c = d.SamsungDrcClient(host, token="t", duid="7825AD10BB57", _connect=connect)
    assert (await c.get_state())["AC_FUN_POWER"] == "On"
    await c.set_attr("AC_FUN_POWER", "Off")
    assert (await c.get_state())["AC_FUN_POWER"] == "Off"
    await c.close()
