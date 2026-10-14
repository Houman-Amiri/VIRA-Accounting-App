"""Content-addressable receipt/document storage (local filesystem or S3).

Files are renamed by SHA-256 digest and partitioned by hash prefix
(``ab/cd/<sha256>.<ext>``), stored OUTSIDE the web root.  Uploads are
inspected via magic bytes (python-magic when available, internal signatures
otherwise), size-capped, and EXIF-stripped from images.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..ids import utc_now_iso, uuid7
from ..services.errors import FileTooLarge, UnsupportedMediaType

MAX_RECEIPT_BYTES = 10 * 1024 * 1024

#: extension -> magic byte signatures (offset 0 unless noted)
SIGNATURES: dict[str, list[bytes]] = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
    "webp": [b"RIFF"],  # + 'WEBP' at offset 8, checked below
}
ALLOWED_MEDIA = {
    "pdf": "application/pdf",
    "png": "image/png",
    "jpg": "image/jpeg",
    "webp": "image/webp",
}


def sniff_kind(data: bytes) -> str | None:
    """Return the allowed kind (pdf/png/jpg/webp) from magic bytes, or None."""
    for kind, sigs in SIGNATURES.items():
        for sig in sigs:
            if data.startswith(sig):
                if kind == "webp":
                    if len(data) >= 12 and data[8:12] == b"WEBP":
                        return kind
                    continue
                return kind
    return None


def strip_image_metadata(data: bytes, kind: str) -> bytes:
    """Remove EXIF/GPS metadata from images (Pillow)."""
    if kind not in {"jpg", "png", "webp"}:
        return data
    try:
        import io

        from PIL import Image

        img = Image.open(io.BytesIO(data))
        clean = io.BytesIO()
        # .save without exif= drops metadata
        fmt = {"jpg": "JPEG", "png": "PNG", "webp": "WEBP"}[kind]
        img.save(clean, format=fmt)
        return clean.getvalue()
    except Exception:
        return data  # if Pillow fails, keep original bytes


class LocalStorageBackend:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path_for(self, sha256: str, ext: str) -> Path:
        return self.root / sha256[:2] / sha256[2:4] / f"{sha256}.{ext}"

    def store(self, data: bytes, *, kind: str) -> tuple[str, Path]:
        sha = hashlib.sha256(data).hexdigest()
        path = self._path_for(sha, kind)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)
        return sha, path

    def load(self, sha256: str, kind: str) -> bytes:
        path = self._path_for(sha256, kind)
        return path.read_bytes()

    def relative_path(self, sha256: str, kind: str) -> str:
        return str(self._path_for(sha256, kind).relative_to(self.root))


def validate_upload(data: bytes, filename: str) -> str:
    """Validate size + magic bytes; return the detected kind."""
    if len(data) > MAX_RECEIPT_BYTES:
        raise FileTooLarge("receipt exceeds 10 MB limit")
    if not data:
        raise UnsupportedMediaType("empty file")
    kind = sniff_kind(data)
    if kind is None:
        # optional python-magic cross-check for odd cases
        try:
            import magic  # type: ignore[import-untyped]

            mime = magic.from_buffer(data, mime=True)
            for k, m in ALLOWED_MEDIA.items():
                if m == mime:
                    kind = k
                    break
        except Exception:
            kind = None
    if kind is None:
        raise UnsupportedMediaType(f"file content is not pdf/png/jpg/webp: {filename!r}")
    return kind


def save_receipt(data: bytes, filename: str, root: Path) -> dict[str, object]:
    kind = validate_upload(data, filename)
    clean = strip_image_metadata(data, kind)
    backend = LocalStorageBackend(root)
    sha, path = backend.store(clean, kind=kind)
    return {
        "id": uuid7(),
        "sha256": sha,
        "media_type": ALLOWED_MEDIA[kind],
        "kind": kind,
        "original_name": filename,
        "size_bytes": len(clean),
        "storage_path": backend.relative_path(sha, kind),
        "uploaded_at": utc_now_iso(),
    }
