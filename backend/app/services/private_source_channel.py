"""Explicit private installed-source update binding, NOT a public activation flag.

An env marker alone is insufficient: CI profile, app root, old external anchor,
owned business-state marker and exact runtime Settings must agree. No QA hooks.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import Settings
from ..private_installed_source import anchor, location, read
from .errors import DomainError


@dataclass(frozen=True)
class SourceScope:
    root: Path
    home: Path
    pin: dict[str, Any]
    files: dict[str, dict[str, Any]]


def no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or (
            part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Private update reparse path")


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def scope(settings: Settings, root: Path | None) -> SourceScope | None:
    if os.environ.get("VIRA_PRIVATE_INSTALLED_SOURCE") != "1":
        return None
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" or root is None:
            raise ValueError("Private CI installation required")
        pin_path, state = location()
        runner = Path(os.environ["RUNNER_TEMP"])
        for path in (
            root,
            pin_path,
            state,
            state / "private-desktop-state.json",
            state / "data/data/vira.sqlite3",
            state / "data/updates",
        ):
            no_links(path)
            if (
                ".." in path.parts
                or not path.is_absolute()
                or not path.is_relative_to(runner)
                or path == runner
            ):
                raise ValueError("Disposable private update paths required")
        if root.is_relative_to(state.parent) or state.parent.is_relative_to(root):
            raise ValueError("Disjoint private payload/state required")
        if (
            settings.data_dir != state / "data"
            or settings.sqlite_database_path != state / "data/data/vira.sqlite3"
            or read(state / "private-desktop-state.json")
            != {"schema": 1, "role": "PRIVATE_SOURCE_DESKTOP_STATE", "payload_root": str(root)}
        ):
            raise ValueError("Runtime Settings do not own private source state")
        pin = anchor(read(pin_path))
        manifest = root / "install_manifest.json"
        no_links(manifest)
        if sha(manifest) != pin["manifest_sha256"]:
            raise ValueError("Old installed manifest digest differs")
        if pin["schema"] == 2:
            no_links(root / "version.json")
            if read(root / "version.json").get("version") != pin["version"]:
                raise ValueError("Installed version differs from independent anchor")
        entries = read(manifest)["files"]
        files = {e["path"]: e for e in entries}
        if len(files) != len(entries):
            raise ValueError("Duplicate old manifest entry")
        return SourceScope(root, state.parent, pin, files)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DomainError(
            "مسیر خصوصی به‌روزرسانی با نصب و دادهٔ فعال هم‌خوان نیست؛ نصب تغییر نکرد."
        ) from exc


def write_new(path: Path, value: dict) -> None:
    no_links(path)
    with path.open("xb") as stream:
        stream.write((json.dumps(value, indent=2) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def clone_installed_helper(context: SourceScope, run: str) -> Path:
    """Execute OLD anchored bytes outside {app}; a running EXE cannot replace itself."""
    source = context.root / "vira-updater.exe"
    no_links(source)
    expected = context.files["vira-updater.exe"]
    if source.stat().st_size != expected["size"] or sha(source) != expected["sha256"]:
        raise ValueError("Old installed helper changed")
    directory = Path(os.environ["RUNNER_TEMP"]) / ("VIRA updater خصوصی ! & " + run)
    no_links(directory)
    if (
        directory.is_relative_to(context.root)
        or context.root.is_relative_to(directory)
        or directory.is_relative_to(context.home)
        or context.home.is_relative_to(directory)
    ):
        raise ValueError("Private helper clone must be disjoint from payload and profile")
    directory.mkdir()  # Fresh nonce; never adopt an existing helper directory.
    target = directory / "vira-updater.exe"
    with source.open("rb") as original, target.open("xb") as cloned:
        shutil.copyfileobj(original, cloned)
        cloned.flush()
        os.fsync(cloned.fileno())
    no_links(target)
    if target.stat().st_size != expected["size"] or sha(target) != expected["sha256"]:
        raise ValueError("Old helper clone differs from independent baseline")
    return target


def command(context: SourceScope, stage: Path) -> tuple[list[str], Path]:
    """Use the anchored OLD real helper, never execute a newly downloaded helper."""
    try:
        fault = os.environ.get("VIRA_PRIVATE_SOURCE_FORCE_FAILURE", "")
        if fault and (
            fault not in {"AFTER_APPLY", "CRASH_FIRST_FILE", "CRASH_AFTER_APPLY"}
            or context.pin["schema"] != 2
            or os.environ.get("GITHUB_ACTIONS") != "true"
            or os.environ.get("VIRA_PRIVATE_INSTALLED_SOURCE") != "1"
        ):
            raise ValueError("Explicit schema2 private CI fault selection required")
        expected_updates = context.home / "state/data/updates"
        if not stage.is_relative_to(expected_updates) or stage.name != "payload":
            raise ValueError("Foreign private staging directory")
        for path in (
            stage,
            stage / "version.json",
            stage / "install_manifest.json",
            context.root / "version.json",
            stage.parent / "package.zip",
            stage.parent / "source-download-receipt.json",
        ):
            no_links(path)
        receipt = read(stage.parent / "source-download-receipt.json")
        archive = stage.parent / "package.zip"
        if receipt["archive_sha256"] != sha(archive):
            raise ValueError("Verified private download changed before apply")
        # Archive SHA was recorded only after the ordinary streaming verifier.
        from .update_staging import validate_private_anchor

        with zipfile.ZipFile(archive) as packet:
            target_pin = validate_private_anchor(packet, context.pin)
            target_raw = packet.read("private-source-anchor.json")
        target = stage / "private-source-anchor.json"
        no_links(target)
        if target.read_bytes() != target_raw:
            raise ValueError("Private target anchor changed after download")
        if read(stage / "version.json")["version"] != receipt["target_version"]:
            raise ValueError("Private target version changed")
        if read(context.root / "version.json")["version"] != receipt["base_version"]:
            raise ValueError("Private base version changed")
        if target_pin["manifest_sha256"] != sha(stage / "install_manifest.json"):
            raise ValueError("Private staged manifest changed")
        run = secrets.token_hex(16)
        helper = clone_installed_helper(context, run)
        transaction = stage.parent / ("private-transaction-" + run + ".json")
        attempt = Path(os.environ["RUNNER_TEMP"]) / ("VIRA تراکنش خصوصی ! & " + run)
        write_new(
            transaction,
            dict(
                role="PRIVATE_SOURCE_TRANSACTION",
                archive=str(archive),
                archive_sha256=receipt["archive_sha256"],
                target_anchor=str(target),
                attempt=str(attempt),
            ),
        )
        log = stage / "update.log"
        argv = [
            str(helper),
            "-Stage",
            str(stage),
            "-Log",
            str(log),
            "-InstallDir",
            str(context.root),
            "-PrivateSourceTransaction",
            str(transaction),
        ]
        if fault == "AFTER_APPLY":
            argv.append("-ForceFailure")
        elif fault:
            argv += ["-PrivateSourceCrashPoint", fault.removeprefix("CRASH_")]
        return argv, log
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as exc:
        raise DomainError(
            "بسته یا updater خصوصی پس از تأیید تغییر کرده است؛ اعمال متوقف شد."
        ) from exc
