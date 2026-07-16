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
