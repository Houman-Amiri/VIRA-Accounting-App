"""Native log rotation (Phase 6 §9).

Writes to ``<data_dir>/logs/vira.log`` with size-based rotation — no Docker
log drivers, no external collectors. Secrets/PII never reach the handler:
structlog's redaction processor (``security/redact.py``) scrubs event data,
and stdlib logging is kept to operational messages only.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

MAX_BYTES = 2 * 1024 * 1024  # 2 MB per file
BACKUP_COUNT = 5  # ~10 MB retained


def install_file_logging(data_dir: Path) -> Path | None:
    logs_dir = Path(data_dir) / "logs"
    try:
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            logs_dir / "vira.log", maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:  # pragma: no cover - read-only media
        return None
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    if root.level == logging.WARNING:  # default — lift to INFO for the file trail
        root.setLevel(logging.INFO)
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    return logs_dir / "vira.log"
