"""App-owned PRIVATE CI installed-source bridge; never selected by public startup.

The installer supplies an external digest anchor. Every invocation generates a
fresh request and delegates to the unchanged REAL start_vira.cmd/app entry.
Stdlib only. No QA factory, renderer, migration or HTTP hooks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import runpy
import secrets
import subprocess
import sys
from pathlib import Path

ANCHOR_KEYS = {
    "schema",
    "role",
    "manifest_sha256",
    "inventory_sha256",
    "source_audit_sha256",
    "port",
    "no_browser",
}


def unique_json(raw: bytes) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate anchor key")
            value[key] = item
        return value

    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Anchor object required")
    return value


def read(path: Path) -> dict:
    return unique_json(path.read_bytes())


def anchor(value: dict) -> dict:
    if (
        type(value.get("schema")) is not int
        or value["schema"] not in (1, 2)
        or set(value) != (ANCHOR_KEYS | {"version"} if value["schema"] == 2 else ANCHOR_KEYS)
        or value["role"] != "PRIVATE_SOURCE_INSTALLED_ANCHOR"
        or type(value["port"]) is not int
        or not 1 <= value["port"] <= 65535
        or type(value["no_browser"]) is not bool
    ):
        raise ValueError("Invalid private installed anchor")
    for key in ("manifest_sha256", "inventory_sha256", "source_audit_sha256"):
        digest = value[key]
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Independent installed SHA256 required")
    if value["schema"] == 2 and (
        not isinstance(value["version"], str)
        or re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", value["version"]) is None
    ):
        raise ValueError("Exact private installed release version required")
    return value


def location() -> tuple[Path, Path]:
    profile = Path(os.environ["LOCALAPPDATA"])
    runner = Path(os.environ["RUNNER_TEMP"])
    if (
        not profile.is_absolute()
        or ".." in profile.parts
        or not profile.is_relative_to(runner)
        or profile == runner
    ):
        raise ValueError("Disposable CI profile below runner TEMP required")
    home = profile / "VIRA/private-native-installed"
    return home / "anchor.json", home / "state"


def prepare(root: Path, pin: Path):
    options = anchor(read(pin))
    raw = (root / "install_manifest.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != options["manifest_sha256"]:
        raise ValueError("Installed manifest differs from external anchor")
    entries = json.loads(raw)["files"]
    module = "app/private_pdf_bootstrap.py"
    expected = [v["sha256"] for v in entries if v["path"] == module]
    if expected != [hashlib.sha256((root / module).read_bytes()).hexdigest()]:
        raise ValueError("Installed bootstrap differs before execution")
    boot = runpy.run_path(str(root / module))
    boot["_no_links"](pin)
    _, state = location()
    launch_id = secrets.token_hex(16)
    plan = boot["PrivateBootstrapPlan"](
        root,
        state.parent / ("bootstrap-" + launch_id),
        options["manifest_sha256"],
        options["inventory_sha256"],
        source_audit_sha256=options["source_audit_sha256"],
        installed_anchor=pin if options["schema"] == 2 else None,
        installed_anchor_sha256=hashlib.sha256(pin.read_bytes()).hexdigest() if options["schema"] == 2 else None,
    )
    boot["prepare_private_plan"](plan)
    return options, state, launch_id, boot


def real_cmd_command(root: Path, request: Path, comspec: str) -> str:
    return (
        f'"{comspec}" /d /s /c ""{root / "start_vira.cmd"}" --private-source-candidate "{request}""'
    )


def main() -> int:
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Private installed-source Windows CI only")
    root = Path(__file__).resolve().parents[1]
    pin, _ = location()
    verify_only = len(sys.argv) == 3 and sys.argv[1] == "--verify"
    if verify_only:
        pin = Path(sys.argv[2])
    elif len(sys.argv) != 1:
        raise ValueError("No public/alternate installed-source options")
    options, state, launch_id, boot = prepare(root, pin)
    if verify_only:
        print(
            json.dumps({"role": "PRIVATE_INSTALLED_SOURCE_READ_ONLY_PREFLIGHT", "verified": True})
        )
        return 0
    lock = state.parent / ".native-update.lock"
    boot["_no_links"](lock)
    if lock.exists():
        token = read(lock).get("token")
        supplied = os.environ.get("VIRA_PRIVATE_UPDATE_TOKEN", "")
        if (
            not isinstance(token, str)
            or len(token) != 64
            or not supplied
            or not secrets.compare_digest(token, supplied)
        ):
            raise ValueError("Private native transaction in progress")
    state.parent.mkdir(parents=True, exist_ok=True)
    request = state.parent / ("request-" + launch_id + ".json")
    value = {
        k: options[k]
        for k in (
            "manifest_sha256",
            "inventory_sha256",
            "source_audit_sha256",
            "port",
            "no_browser",
        )
    }
    value.update(role="PRIVATE_SOURCE_DESKTOP_REQUEST", state_root=str(state), launch_id=launch_id)
    if options["schema"] == 2:
        value.update(role="PRIVATE_INSTALLED_SOURCE_DESKTOP_REQUEST", installed_anchor=str(pin),
                     installed_anchor_sha256=hashlib.sha256(pin.read_bytes()).hexdigest())
    with request.open("xb") as stream:
        stream.write((json.dumps(value, indent=2) + "\n").encode())
    # Publication is exclusive while this installed bridge has a live child.
    active = state.parent / "active-launch.json"
    try:
        with active.open("xb") as stream:
            stream.write(json.dumps({"launch_id": launch_id, "payload_root": str(root)}).encode())
    except BaseException:
        request.unlink()
        raise
    try:
        # Use the same raw Windows command line as the proven Phase2 driver;
        # list2cmdline escaping is NOT cmd.exe /s /c quoting.
        command = real_cmd_command(root, request, os.environ["COMSPEC"])
        return subprocess.call(
            command,
            cwd=state.parent,
            env={
                **os.environ,
                "VIRA_PRIVATE_INSTALLED_SOURCE": "1",
                "VIRA_PORT": str(options["port"]),
            },
        )

    finally:
        if read(active) != {"launch_id": launch_id, "payload_root": str(root)}:
            raise RuntimeError("Installed active-launch ownership changed")
        active.unlink()
        # Retain only app-owned receipts under state; requests contain no secret.
        request.unlink()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("Private installed-source rejected: " + type(exc).__name__, file=sys.stderr)
        raise SystemExit(1) from None
