"""Application version + build provenance (Phase 6 §8, Phase 8 §2).

Single source of truth: the ``version`` field of the root ``pyproject.toml``.
`VIRA_VERSION` / `VIRA_GIT_COMMIT` are injected at build/release time and win
over the installed metadata; the git checkout is used as a last resort for
commit provenance (dev machines) and then "unknown".
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache


def _base_version() -> str:
    """Read the installed project version (sourced from pyproject.toml)."""
    try:
        from importlib.metadata import version

        return version("vira-accounting")
    except Exception:  # noqa: BLE001 - any failure falls back below
        return "0.0.0-unknown"


__version__ = _base_version()


@lru_cache(maxsize=1)
def version_info() -> dict[str, str]:
    version = os.environ.get("VIRA_VERSION", __version__)
    commit = os.environ.get("VIRA_GIT_COMMIT", "")
    if not commit:
        try:
            commit = subprocess.check_output(  # noqa: S603 - fixed argv, no shell
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                stderr=subprocess.DEVNULL,
                text=True,
            ).strip()
        except Exception:  # noqa: BLE001 - any failure => unknown build
            commit = "unknown"
    return {"version": version, "commit": commit}
