"""Standalone async client for Samsung DRC-1.00 / 2878 AC modules. No HA imports."""
from __future__ import annotations
import asyncio, os, re, ssl, time

TERM = b"\r\n"
DEFAULT_PORT = 2878
_ATTR_RE = re.compile(r'Attr ID="([^"]+)"[^>]*?Value="([^"]*)"')
_TOKEN_RE = re.compile(r'Token="([^"]*)"')
_DUID_RE = re.compile(r'Device DUID="([^"]+)"')
GETTOKEN = b'<Request Type="GetToken" />' + TERM

def default_cert_path() -> str:
    return os.path.join(os.path.dirname(__file__), "ac14k_m.pem")

def build_ssl_context(cert_path: str | None = None) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ctx.minimum_version = ssl.TLSVersion.TLSv1
    ctx.set_ciphers("HIGH:!DH:!aNULL:@SECLEVEL=0")
    ctx.load_cert_chain(cert_path or default_cert_path())
    return ctx

def parse_attrs(xml: str) -> dict[str, str]:
    return {m[0]: m[1] for m in _ATTR_RE.findall(xml)}

def build_auth(token: str) -> bytes:
    return f'<Request Type="AuthToken"><User Token="{token}"/></Request>'.encode() + TERM

def build_state(duid: str) -> bytes:
    return f'<Request Type="DeviceState" DUID="{duid}"></Request>'.encode() + TERM

def build_control(duid: str, attr: str, value: str) -> bytes:
    return (f'<Request Type="DeviceControl"><Control CommandID="{attr}" DUID="{duid}">'
            f'<Attr ID="{attr}" Value="{value}"/></Control></Request>').encode() + TERM


class DrcError(Exception): ...
class AuthError(DrcError): ...

async def _readline(reader: asyncio.StreamReader, timeout: float = 5.0) -> str:
    data = await asyncio.wait_for(reader.readuntil(TERM), timeout)
    return data.decode("utf-8", "replace").strip()

class DrcProtocol:
    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        self._r, self._w = reader, writer

    async def read_greeting(self) -> None:
        greet = await _readline(self._r)
        if "DRC-1.00" not in greet:
            raise DrcError(f"Unexpected greeting: {greet!r}")
        # InvalidateAccount line (best-effort)
        try: await _readline(self._r, 3)
        except asyncio.TimeoutError: pass

    async def _send(self, data: bytes) -> None:
        self._w.write(data); await self._w.drain()

    async def _read_until(self, needle: str, timeout: float) -> str:
        end = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < end:
            line = await _readline(self._r, timeout)
            if needle in line: return line
        raise asyncio.TimeoutError

    async def authenticate(self, token: str) -> None:
        await self._send(build_auth(token))
        for _ in range(4):
            line = await _readline(self._r, 6)
            if 'Type="AuthToken"' in line and 'Status="Okay"' in line: return
            if 'Status="Fail"' in line and "Auth" in line:
                raise AuthError(f"Token rejected: {line}")
        raise AuthError("No AuthToken Okay received")

    async def get_state(self, duid: str) -> dict[str, str]:
        await self._send(build_state(duid))
        line = await self._read_until('Type="DeviceState"', 6)
        return parse_attrs(line)

    async def set_attr(self, duid: str, attr: str, value: str) -> None:
        await self._send(build_control(duid, attr, value))
        # Wait for the device to acknowledge the control command so callers
        # can rely on the write having landed before this returns.
        await self._read_until('Type="DeviceControl"', 6)

    async def discover_duid(self) -> str:
        await self._send(build_state(""))
        line = await self._read_until("DeviceState", 6)
        m = _DUID_RE.search(line)
        if not m: raise DrcError("Could not discover DUID")
        return m.group(1)

    async def get_token(self, power_on_timeout: float = 120) -> str:
        await self._send(GETTOKEN)
        await self._read_until('Type="GetToken"', 6)  # Status="Ready"
        line = await self._read_until("Token=", power_on_timeout)
        m = _TOKEN_RE.search(line)
        if not m: raise DrcError(f"No token in: {line}")
        return m.group(1)


class SamsungDrcClient:
    def __init__(self, host, token=None, duid=None, port=DEFAULT_PORT,
                 ssl_context=None, _connect=None):
        self._host, self._port, self._token, self._duid = host, port, token, duid
        self._ctx = ssl_context
        self._connect_override = _connect
        self._proto: DrcProtocol | None = None
        self._reader = self._writer = None
        self._lock = asyncio.Lock()

    async def _open(self):
        if self._connect_override:
            reader, writer = await self._connect_override()
        else:
            ctx = self._ctx or build_ssl_context()
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self._host, self._port, ssl=ctx,
                                        server_hostname=self._host), 15)
        self._reader, self._writer = reader, writer
        self._proto = DrcProtocol(reader, writer)
        await self._proto.read_greeting()
        if self._token:
            await self._proto.authenticate(self._token)

    async def _ensure(self):
        if self._proto is None:
            await self._open()

    async def _with_retry(self, coro_factory):
        async with self._lock:
            for attempt in (1, 2):
                try:
                    await self._ensure()
                    return await coro_factory()
                except (OSError, asyncio.IncompleteReadError, asyncio.TimeoutError, DrcError):
                    await self._drop()
                    if attempt == 2: raise
        return None

    async def _drop(self):
        if self._writer:
            try: self._writer.close()
            except Exception: pass
        self._proto = self._reader = self._writer = None

    async def ensure_duid(self) -> str:
        if not self._duid:
            self._duid = await self._with_retry(lambda: self._proto.discover_duid())
        return self._duid

    async def get_state(self) -> dict[str, str]:
        duid = await self.ensure_duid()
        return await self._with_retry(lambda: self._proto.get_state(duid))

    async def set_attr(self, attr: str, value: str) -> None:
        duid = await self.ensure_duid()
        await self._with_retry(lambda: self._proto.set_attr(duid, attr, value))

    async def get_token(self, power_on_timeout: float = 120) -> str:
        async with self._lock:
            await self._open()  # no token yet
            try:
                return await self._proto.get_token(power_on_timeout)
            finally:
                await self._drop()

    async def close(self):
        async with self._lock:
            await self._drop()
