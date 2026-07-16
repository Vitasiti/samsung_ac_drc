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
