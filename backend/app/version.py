"""Application version + build provenance (Phase 6 §8, Phase 8 §2).

Precedence for **version**: ``VIRA_VERSION`` env → ``version.json`` next to the
running app (written by the installer/updater) → installed distribution
metadata (``pyproject.toml`` in dev checkouts) → ``"0.0.0-unknown"``.

Precedence for **commit**: ``VIRA_GIT_COMMIT`` env → ``version.json:commit`` →
``git rev-parse --short HEAD`` (dev checkout only) → ``"unknown"``.

The installed payload has neither distribution metadata (the backend is copied,
not pip-installed) nor a ``.git`` directory, which is why v1.0.4 showed
«نسخه: 0.0.0-unknown / کامیت: unknown» — the JSON stamp shipped with the app is
the authoritative source there (v1.0.5 fix).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

UNKNOWN_VERSION = "0.0.0-unknown"
UNKNOWN_COMMIT = "unknown"


def _app_roots() -> list[Path]:
    """Candidate directories that may hold the shipped ``version.json``."""
    roots: list[Path] = []
    env_dir = os.environ.get("VIRA_APP_DIR")
    if env_dir:
        roots.append(Path(env_dir))
    # installed payload: {app}/python/python.exe  ->  {app}/version.json
    roots.append(Path(sys.executable).resolve().parent.parent)
    roots.append(Path(sys.executable).resolve().parent)
    # dev checkout: backend/app/version.py -> <repo>/version.json
    roots.append(Path(__file__).resolve().parents[2])
    roots.append(Path.cwd())
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        if root not in seen:
            seen.add(root)
            unique.append(root)
    return unique


@lru_cache(maxsize=1)
def _stamp() -> dict[str, str]:
    """Read the build stamp (``version.json``) shipped with the application."""
    for root in _app_roots():
        candidate = root / "version.json"
        try:
            if not candidate.is_file():
                continue
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken stamp must never crash startup
            continue
        if isinstance(data, dict):
            return {
                "version": str(data.get("version") or ""),
                "commit": str(data.get("commit") or ""),
                "built_at": str(data.get("built_at") or ""),
            }
    return {"version": "", "commit": "", "built_at": ""}


def _metadata_version() -> str:
    """Read the installed project version (sourced from pyproject.toml)."""
    try:
        from importlib.metadata import version

        return version("vira-accounting")
    except Exception:  # noqa: BLE001 - any failure falls back below
        return ""


__version__ = _metadata_version() or _stamp()["version"] or UNKNOWN_VERSION


def _git_commit() -> str:
    try:
        return subprocess.check_output(  # noqa: S603 - fixed argv, no shell
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
        ).strip()
    except Exception:  # noqa: BLE001 - any failure => unknown build
        return ""


@lru_cache(maxsize=1)
def version_info() -> dict[str, str]:
    stamp = _stamp()
    version = os.environ.get("VIRA_VERSION") or stamp["version"] or __version__
    commit = (
        os.environ.get("VIRA_GIT_COMMIT")
        or stamp["commit"]
        or _git_commit()
        or UNKNOWN_COMMIT
    )
    built_at = os.environ.get("VIRA_BUILT_AT") or stamp["built_at"]
    return {"version": version, "commit": commit, "built_at": built_at}
