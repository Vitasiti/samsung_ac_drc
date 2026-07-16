from custom_components.samsung_ac_drc import drc_client as d


def test_parse_attrs():
    xml = ('<Response Type="DeviceState" Status="Okay"><DeviceState><Device DUID="X" '
           'GroupID="AC" ModelID="AC"><Attr ID="AC_FUN_POWER" Type="RW" Value="On"/>'
           '<Attr ID="AC_FUN_TEMPSET" Type="RW" Value="23"/></Device></DeviceState></Response>')
    assert d.parse_attrs(xml) == {"AC_FUN_POWER": "On", "AC_FUN_TEMPSET": "23"}


def test_build_control():
    out = d.build_control("AABBCCDDEEFF", "AC_FUN_POWER", "Off")
    assert out == (b'<Request Type="DeviceControl"><Control CommandID="AC_FUN_POWER" '
                   b'DUID="AABBCCDDEEFF"><Attr ID="AC_FUN_POWER" Value="Off"/></Control></Request>\r\n')


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
    st = await p.get_state("AABBCCDDEEFF")
    assert st["AC_FUN_POWER"] == "On" and st["AC_FUN_TEMPSET"] == "23"


async def test_control_roundtrip(mock_drc):
    srv, host, port = mock_drc
    p = await _proto(host, port); await p.authenticate("t")
    await p.set_attr("AABBCCDDEEFF", "AC_FUN_POWER", "Off")
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
    c = d.SamsungDrcClient(host, token="t", duid="AABBCCDDEEFF", _connect=connect)
    assert (await c.get_state())["AC_FUN_POWER"] == "On"
    await c.set_attr("AC_FUN_POWER", "Off")
    assert (await c.get_state())["AC_FUN_POWER"] == "Off"
    await c.close()


async def test_discover_duid_when_module_rejects_empty_duid(mock_drc):
    """The module answers an empty-DUID DeviceState with Status="Fail", so DUID
    discovery must not rely on it volunteering its identity that way."""
    import asyncio
    from tests.conftest import MOCK_DUID
    srv, host, port = mock_drc
    async def connect():
        return await asyncio.open_connection(host, port)
    c = d.SamsungDrcClient(host, token="tok", _connect=connect)
    assert await c.ensure_duid() == MOCK_DUID
    await c.close()


async def test_fail_response_is_not_treated_as_success():
    """A rejection echoes the request type it is rejecting, so matching on the
    type alone accepts a failure as success and silently yields empty data."""
    import asyncio, pytest
    reader = asyncio.StreamReader()
    reader.feed_data(b'<?xml?><Response Status="Fail" Type="DeviceState" '
                     b'ErrorCode="103" />\r\n')
    proto = d.DrcProtocol(reader, None)
    with pytest.raises(d.DrcError, match="rejected"):
        await proto._read_until('Type="DeviceState"', 2)


async def test_okay_response_still_returns_normally():
    """The Fail guard must not reject legitimate responses."""
    import asyncio
    reader = asyncio.StreamReader()
    reader.feed_data(b'<?xml?><Response Type="DeviceState" Status="Okay">'
                     b'<Attr ID="AC_FUN_POWER" Value="On"/></Response>\r\n')
    proto = d.DrcProtocol(reader, None)
    line = await proto._read_until('Type="DeviceState"', 2)
    assert d.parse_attrs(line) == {"AC_FUN_POWER": "On"}
