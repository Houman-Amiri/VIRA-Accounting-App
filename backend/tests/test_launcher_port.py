"""The installed launcher must survive a port that is already taken.

Owner-reported (v1.0.23): starting NOA while an earlier session was still open
printed a raw ``WinError 10048`` and «Startup failed», and nothing opened. The
launcher pre-flight now recognises its own running instance and moves to the
next free port instead of dying.
"""

from __future__ import annotations

import importlib.util
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# A real module (not runpy's copied globals) so tests can patch its functions.
SPEC = importlib.util.spec_from_file_location(
    "noa_start_server", ROOT / "scripts" / "start_noa_server.py"
)
assert SPEC is not None and SPEC.loader is not None
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _serve(payloads: dict[str, object]) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib name
            body = payloads.get(self.path)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            raw = json.dumps(body).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def log_message(self, *args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


NOA_PAYLOADS = {
    "/api/v1/health/live": {"status": "alive"},
    "/api/openapi.json": {"openapi": "3.1.0", "info": {"title": "NOA Accounting API"}},
}
LOOKALIKE_PAYLOADS = {
    "/api/v1/health/live": {"status": "alive"},
    "/api/openapi.json": {"openapi": "3.1.0", "info": {"title": "Some Other Service"}},
}


def test_port_is_free_tracks_a_real_listener() -> None:
    port = _free_port()
    assert launcher.port_is_free(port) is True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        assert launcher.port_is_free(port) is False


def test_only_a_real_noa_counts_as_running() -> None:
    noa = _serve(NOA_PAYLOADS)
    lookalike = _serve(LOOKALIKE_PAYLOADS)
    try:
        assert launcher.is_noa(noa.server_port) is True
        assert launcher.is_noa(lookalike.server_port) is False
        assert launcher.find_existing(noa.server_port) == noa.server_port
        assert launcher.find_existing(lookalike.server_port) is None
    finally:
        noa.shutdown()
        lookalike.shutdown()


def test_a_foreign_program_pushes_noa_to_the_next_port() -> None:
    lookalike = _serve(LOOKALIKE_PAYLOADS)
    try:
        requested = lookalike.server_port
        assert launcher.find_existing(requested) is None
        assert launcher.choose_port(requested) == requested + 1
    finally:
        lookalike.shutdown()


def test_instance_file_roundtrip_and_stale_pid(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert launcher.read_instance() is None

    path = launcher.instance_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"pid": 999_999_999, "port": 8787}), encoding="utf-8")
    record = launcher.read_instance()
    assert record == {"pid": 999_999_999, "port": 8787}
    # A pid that is gone must not make NOA believe it is already running.
    assert launcher.pid_alive(999_999_999) is False
    assert launcher.find_existing(8787) is None

    path.write_text(json.dumps({"pid": "not-a-pid", "port": 8787}), encoding="utf-8")
    assert launcher.read_instance() is None


def test_an_already_running_noa_is_opened_instead_of_restarted(monkeypatch) -> None:
    opened: list[str] = []
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    monkeypatch.setattr(launcher, "find_existing", lambda requested: 8789)

    def refuse(port: int) -> int:  # pragma: no cover - must not be reached
        raise AssertionError("NOA must not start a second server")

    monkeypatch.setattr(launcher, "start", refuse)
    monkeypatch.delenv("NOA_PORT", raising=False)
    monkeypatch.delenv("NOA_STRICT_PORT", raising=False)

    assert launcher.main() == 0
    assert opened == ["http://127.0.0.1:8789/"]


def test_start_moves_to_a_free_port_and_says_so(monkeypatch, capsys) -> None:
    started: list[int] = []
    monkeypatch.setattr(launcher, "find_existing", lambda requested: None)
    monkeypatch.setattr(launcher, "wait_for_free", lambda port, seconds=5.0: False)
    monkeypatch.setattr(launcher, "choose_port", lambda port, attempts=10: 8801)
    monkeypatch.setattr(launcher, "start", lambda port: started.append(port) or 0)
    monkeypatch.setenv("NOA_PORT", "8787")
    monkeypatch.delenv("NOA_STRICT_PORT", raising=False)

    assert launcher.main() == 0
    assert started == [8801]
    out = capsys.readouterr().out
    assert "Port 8787 is used by another program — using 8801" in out


def test_no_free_port_reports_a_usable_message(monkeypatch, capsys) -> None:
    monkeypatch.setattr(launcher, "find_existing", lambda requested: None)
    monkeypatch.setattr(launcher, "wait_for_free", lambda port, seconds=5.0: False)
    monkeypatch.setattr(launcher, "choose_port", lambda port, attempts=10: None)
    monkeypatch.delenv("NOA_STRICT_PORT", raising=False)

    assert launcher.main() == 1
    out = capsys.readouterr().out
    assert "No free port was found" in out
    assert "Startup failed" not in out


def test_a_lost_race_moves_on_instead_of_a_raw_socket_error(monkeypatch, capsys) -> None:
    attempts: list[int] = []

    def start(port: int) -> int:
        attempts.append(port)
        raise OSError(10048, "address already in use")

    monkeypatch.setattr(launcher, "find_existing", lambda requested: None)
    monkeypatch.setattr(launcher, "wait_for_free", lambda port, seconds=5.0: True)
    monkeypatch.setattr(launcher, "start", start)
    monkeypatch.setattr(launcher, "choose_port", lambda port, attempts=10: None)
    monkeypatch.delenv("NOA_STRICT_PORT", raising=False)

    assert launcher.main() == 1
    assert attempts == [8787]
    out = capsys.readouterr().out
    assert "became busy" in out
    assert "No free port was found" in out
    assert "Try 'netstat'" not in out


@pytest.mark.parametrize("value", ["", "not-a-number"])
def test_a_bad_port_setting_falls_back_to_the_default(monkeypatch, value) -> None:
    seen: list[int] = []
    monkeypatch.setenv("NOA_PORT", value)
    monkeypatch.delenv("NOA_STRICT_PORT", raising=False)
    monkeypatch.setattr(launcher, "find_existing", lambda requested: seen.append(requested) or 8787)

    assert launcher.main() == 0
    assert seen == [8787]


def test_strict_mode_never_moves_to_another_port(monkeypatch, capsys) -> None:
    """CI launches with NOA_STRICT_PORT so a smoke leg can prove the binding."""
    port = _free_port()
    started: list[int] = []
    monkeypatch.setenv("NOA_PORT", str(port))
    monkeypatch.setenv("NOA_STRICT_PORT", "1")
    monkeypatch.setattr(launcher, "start", lambda value: started.append(value) or 0)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", port))
        sock.listen(1)
        assert launcher.main() == 1
    assert started == []
    assert "NOA_STRICT_PORT" in capsys.readouterr().out
