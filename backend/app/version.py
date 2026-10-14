"""Application version + build provenance (Phase 6 §8).

`VIRA_VERSION` / `VIRA_GIT_COMMIT` are injected at build/release time;
falls back to the git checkout (dev machines) and then "unknown".
"""

from __future__ import annotations

import os
import subprocess
from functools import lru_cache

__version__ = "0.1.0"


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
