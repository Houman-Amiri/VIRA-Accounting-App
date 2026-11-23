"""LAN access (v1.0.28): NOA listens on every interface and keeps login working.

The owner opens the same app from another computer on the home network
(``http://192.168.1.20:8787``).  Two things must hold for that:

* the launcher binds ``0.0.0.0``, not loopback, and prints the LAN address;
* session cookies are not marked ``Secure`` when the request came over plain
  HTTP — browsers drop Secure cookies on a LAN IP and the login would silently
  fail (``localhost`` is exempt in browsers, a LAN address is not).
"""

from __future__ import annotations

import importlib.util
import ipaddress
import socket
from pathlib import Path

import pytest
from starlette.requests import Request

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "noa_start_server_lan", ROOT / "scripts" / "start_noa_server.py"
)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def _request(scheme: str) -> Request:
    return Request(
        {
            "type": "http",
            "scheme": scheme,
            "method": "GET",
            "path": "/api/v1/auth/me",
            "headers": [],
            "query_string": b"",
            "server": ("192.168.1.20", 8787),
        }
    )


def test_the_server_binds_every_interface() -> None:
    assert launcher.BIND_HOST == "0.0.0.0"
    # loopback stays the address NOA itself opens; the bind is what widens
    assert launcher.HOST == "127.0.0.1"

    port = launcher.port_is_free(0)  # sanity: the helper still answers
    assert isinstance(port, bool)


def test_lan_address_is_a_real_private_or_public_ip_or_none() -> None:
    address = launcher.lan_address()
    if address is None:  # offline sandbox — acceptable
        return
    parsed = ipaddress.ip_address(address)
    assert not parsed.is_loopback


def test_cookie_secure_flag_follows_the_request_scheme() -> None:
    from app.api.auth import _cookies_secure
    from app.security.session import SessionManager

    manager = SessionManager("s" * 40, secure=True)
    assert _cookies_secure(_request("http"), manager) is False
    assert _cookies_secure(_request("https"), manager) is True
    # development instances never ask for Secure cookies at all
    assert _cookies_secure(_request("https"), SessionManager("s" * 40)) is False


@pytest.mark.anyio
async def test_login_from_a_lan_ip_sets_a_usable_cookie(app) -> None:
    """Over http://192.168.x.x the cookie must be accepted by the browser."""
    from httpx import ASGITransport, AsyncClient

    from app.api.deps import get_session_manager
    from app.security.session import SessionManager

    manager = SessionManager("s" * 40, secure=True)  # as a production install
    app.dependency_overrides[get_session_manager] = lambda: manager
    try:

        async def login(base_url: str) -> list[str]:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url=base_url) as client:
                response = await client.post(
                    "/api/v1/auth/login",
                    json={"username": "owner", "password": "test-password-1"},
                )
            assert response.status_code == 200, response.text
            return response.headers.get_list("set-cookie")

        lan = await login("http://192.168.1.20:8787")
        assert lan and all("secure" not in cookie.lower() for cookie in lan)
        # the same install behind TLS keeps the flag
        tls = await login("https://192.168.1.20:8787")
        assert tls and all("secure" in cookie.lower() for cookie in tls)
    finally:
        app.dependency_overrides.pop(get_session_manager, None)


@pytest.fixture()
def anyio_backend() -> str:
    return "asyncio"


def test_the_bind_scope_reaches_a_non_loopback_socket() -> None:
    """A socket bound the way the launcher binds accepts LAN connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((launcher.BIND_HOST, 0))
        host, port = sock.getsockname()
    assert host == "0.0.0.0"
    assert port > 0


def test_the_console_output_stays_ascii(monkeypatch, capsys) -> None:
    """The Windows console is cp1252; a Persian print aborted startup in CI."""
    monkeypatch.setattr(launcher, "lan_address", lambda: "192.168.1.20")
    monkeypatch.setattr(launcher, "start", lambda port: 0)
    assert launcher.serve(8787, 8787) == 0
    out = capsys.readouterr().out
    assert "[NOA] LAN access: http://192.168.1.20:8787/" in out
    out.encode("ascii")  # raises UnicodeEncodeError if a stray character slips in
