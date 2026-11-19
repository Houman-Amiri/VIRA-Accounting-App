"""Start the NOA API for the installed launcher, without dying on a taken port.

The owner starts NOA from a shortcut.  If an earlier session is still running
(his window is minimised, or he simply clicked the icon twice) the second start
used to bind the same port, fail with a raw ``WinError 10048`` and print
«Startup failed».  From the owner's side nothing happened, twice.

This launcher pre-flight replaces that:

* an already running NOA is recognised (its health + OpenAPI signature, and the
  instance file it leaves behind) and **opened in the browser** instead of
  starting a second writer on the same SQLite file;
* a port occupied by some other program makes NOA move to the next free port,
  and the browser opens on that port;
* every message names what happened and what NOA did about it.

Console text stays English deliberately: the Windows console code page cannot be
relied upon to show Persian, and the app itself opens right after.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

HOST = "127.0.0.1"
DEFAULT_PORT = 8787
# How far up from the requested port NOA is willing to move.
PORT_ATTEMPTS = 10
# A freshly started NOA answers /health/live a few seconds after the socket is
# bound; waiting briefly avoids mistaking it for "some other program".
PROBE_SECONDS = 15.0


def data_dir() -> Path:
    """Same folder the launcher uses for data, logs and the session secret."""
    override = os.environ.get("DATA_DIR")
    if override:
        return Path(override)
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / ".local" / "share"
    return base / "NOA"


def instance_file() -> Path:
    return data_dir() / "instance.json"


def _request(path: str, timeout: float) -> tuple[int, bytes] | None:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"http://{HOST}:{path}", timeout=timeout) as response:  # noqa: S310
            return response.status, response.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def is_noa(port: int, timeout: float = 1.0) -> bool:
    """True only when this port serves NOA itself, not merely *some* HTTP app.

    Two independent marks are required: the liveness payload and the OpenAPI
    title.  A lookalike on the same port must never be mistaken for our own
    instance — NOA would then skip starting and the owner would see someone
    else's page.
    """
    live = _request(f"{port}/api/v1/health/live", timeout)
    if live is None:
        return False
    status, body = live
    try:
        payload = json.loads(body)
    except ValueError:
        return False
    if status != 200 or payload != {"status": "alive"}:
        return False
    spec = _request(f"{port}/api/openapi.json", timeout)
    if spec is None:
        return False
    try:
        document = json.loads(spec[1])
    except ValueError:
        return False
    info = document.get("info") if isinstance(document, dict) else None
    title = info.get("title") if isinstance(info, dict) else None
    return isinstance(title, str) and "NOA" in title


def port_is_free(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:  # pragma: no cover - Windows raises a generic OSError
        return False
    return True


def read_instance() -> dict[str, object] | None:
    try:
        raw = json.loads(instance_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    port, pid = raw.get("port"), raw.get("pid")
    if type(port) is not int or type(pid) is not int:
        return None
    return raw


def write_instance(port: int) -> None:
    try:
        instance_file().parent.mkdir(parents=True, exist_ok=True)
        instance_file().write_text(
            json.dumps({"pid": os.getpid(), "port": port, "started_at": time.time()}),
            encoding="utf-8",
        )
    except OSError:  # pragma: no cover - diagnostics only, never blocks startup
        pass


def clear_instance() -> None:
    record = read_instance()
    if record is None or int(record["pid"]) != os.getpid():
        return
    with contextlib.suppress(OSError):  # pragma: no cover - best effort
        instance_file().unlink()


def wait_for_noa(port: int, seconds: float = PROBE_SECONDS) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if is_noa(port, timeout=0.5):
            return True
        time.sleep(0.25)
    return False


def find_existing(requested: int) -> int | None:
    """Port of a NOA that is already running (healthy or still booting)."""
    record = read_instance()
    if record is not None and pid_alive(int(record["pid"])):
        port = int(record["port"])
        if is_noa(port) or wait_for_noa(port):
            return port  # a NOA that is still booting counts as running
        # The recorded process exists but never became healthy; fall through to
        # the ordinary port scan so a restart can still happen.
    for port in range(requested, requested + PORT_ATTEMPTS):
        if is_noa(port):
            return port
    return None


def wait_for_free(port: int, seconds: float = 5.0) -> bool:
    """Give a just-closed instance a moment to release its socket.

    The updater kills the old process and immediately relaunches; treating that
    one-second gap as "some other program owns the port" would move the new
    version to 8788 while the updater waits on 8787.
    """
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if port_is_free(port):
            return True
        time.sleep(0.25)
    return port_is_free(port)


def choose_port(requested: int, attempts: int = PORT_ATTEMPTS) -> int | None:
    """First free port at or above ``requested``; None when none is free."""
    for port in range(requested, requested + attempts):
        if port_is_free(port):
            return port
    return None


def open_browser_when_ready(port: int) -> None:
    def run() -> None:
        if wait_for_noa(port, seconds=120):
            webbrowser.open(f"http://{HOST}:{port}/")

    threading.Thread(target=run, name="NOA browser", daemon=True).start()


def start(port: int) -> int:
    """Serve on a socket this process owns, so a lost race is an OSError here."""
    import uvicorn

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind((HOST, port))  # raises OSError when the port went to someone else
    server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=0, log_level="info"))
    write_instance(port)
    open_browser_when_ready(port)
    try:
        server.run(sockets=[sock])
    finally:
        clear_instance()
    return 0


def strict_port() -> bool:
    """CI sets this: the smoke test proves NOA binds the port it was given."""
    return os.environ.get("NOA_STRICT_PORT", "").strip().lower() in {"1", "true", "yes"}


def serve(port: int, requested: int) -> int:
    """Start on ``port``, moving up when a race steals it, and say each move."""
    candidate: int | None = port
    announced = port == requested
    while candidate is not None:
        if not announced:
            print(f"[NOA] Port {requested} is used by another program — using {candidate}.")
        announced = False
        print(
            f"[NOA] Starting server on http://{HOST}:{candidate}/ "
            "(logs below — Ctrl+C or close to stop)"
        )
        try:
            return start(candidate)
        except OSError as exc:
            # Lost a race for the port between the check and the bind: move on
            # instead of printing a raw socket error.
            print(f"[NOA] Port {candidate} became busy ({exc}); trying the next one.")
            candidate = choose_port(candidate + 1)
    print(f"[NOA] No free port was found between {requested} and {requested + PORT_ATTEMPTS - 1}.")
    print("[NOA] Close the other program (or NOA itself) and start NOA again.")
    return 1


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        requested = int(os.environ.get("NOA_PORT") or DEFAULT_PORT)
    except ValueError:
        requested = DEFAULT_PORT

    if strict_port():
        if not port_is_free(requested):
            print(f"[NOA] Port {requested} is already in use and NOA_STRICT_PORT is set.")
            return 1
        return serve(requested, requested)

    existing = find_existing(requested)
    if existing is not None:
        print(f"[NOA] NOA is already running at http://{HOST}:{existing}/ — opening it.")
        webbrowser.open(f"http://{HOST}:{existing}/")
        return 0

    if wait_for_free(requested):
        return serve(requested, requested)
    next_port = choose_port(requested + 1)
    if next_port is None:
        return _no_port(requested)
    return serve(next_port, requested)


def _no_port(requested: int) -> int:
    print(f"[NOA] No free port was found between {requested} and {requested + PORT_ATTEMPTS - 1}.")
    print("[NOA] Close the other program (or NOA itself) and start NOA again.")
    return 1


if __name__ == "__main__":  # pragma: no cover - exercised by the launcher/CI smoke
    sys.exit(main())
