import asyncio, pytest

class MockDRC:
    """Plain-TCP server that mimics the DRC line protocol (no TLS) for tests."""
    def __init__(self): self.token_after_power_on = None; self.state = {}; self._writers = []
    async def handle(self, reader, writer):
        self._writers.append(writer)
        writer.write(b"DRC-1.00\r\n"); writer.write(
            b'<?xml version="1.0"?><Update Type="InvalidateAccount"/>\r\n'); await writer.drain()
        while not reader.at_eof():
            line = await reader.readline()
            if not line: break
            s = line.decode()
            if 'Type="AuthToken"' in s:
                writer.write(b'<?xml?><Response Type="AuthToken" Status="Okay" '
                             b'StartFrom="2026-07-16/06:57:11"/>\r\n')
            elif 'Type="DeviceState"' in s:
                attrs = "".join(f'<Attr ID="{k}" Type="RW" Value="{v}"/>' for k, v in self.state.items())
                writer.write(f'<?xml?><Response Type="DeviceState" Status="Okay"><DeviceState>'
                             f'<Device DUID="AABBCCDDEEFF" GroupID="AC" ModelID="AC">{attrs}'
                             f'</Device></DeviceState></Response>\r\n'.encode())
            elif 'Type="DeviceControl"' in s:
                import re
                m = re.search(r'CommandID="([^"]+)".*Value="([^"]*)"', s)
                if m: self.state[m.group(1)] = m.group(2)
                writer.write(b'<?xml?><Response Type="DeviceControl" Status="Okay"/>\r\n')
            elif 'Type="GetToken"' in s:
                writer.write(b'<?xml?><Response Type="GetToken" Status="Ready"/>\r\n')
                if self.token_after_power_on:
                    await asyncio.sleep(0.05)
                    writer.write(f'<?xml?><Update Type="GetToken" Status="Completed" '
                                 f'Token="{self.token_after_power_on}"/>\r\n'.encode())
            await writer.drain()

@pytest.fixture
async def mock_drc():
    srv = MockDRC()
    server = await asyncio.start_server(srv.handle, "127.0.0.1", 0)
    host, port = server.sockets[0].getsockname()[:2]
    try:
        yield srv, host, port
    finally:
        # Python 3.12.1+ made Server.wait_closed() (invoked by `async with
        # server:`) block until *all* accepted connections are dropped, not
        # just the listening socket. The test client never explicitly closes
        # its connection, so the accepted server-side transport must be
        # force-closed here or teardown hangs forever.
        for w in srv._writers:
            w.close()
        server.close()
        await server.wait_closed()
