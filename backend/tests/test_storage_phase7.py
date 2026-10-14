"""Phase 7 §2 — pluggable storage: local + S3 (mocked boto3), content-addressable
hashing, EXIF stripping, presigned delivery."""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pytest

from app.services.errors import UnsupportedMediaType
from app.services.storage import (
    LocalStorageBackend,
    S3StorageBackend,
    get_storage,
    save_receipt_with,
    strip_image_metadata,
    validate_upload,
)


def _png_with_exif() -> bytes:
    from PIL import Image

    img = Image.new("RGB", (4, 4), color=(200, 30, 30))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_local_backend_content_addressable_layout(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    data = _png_with_exif()
    sha, path = backend.store(data, kind="png")
    assert sha == hashlib.sha256(data).hexdigest()
    # ab/cd/<sha256>.png partitioning
    assert path == tmp_path / sha[:2] / sha[2:4] / f"{sha}.png"
    assert path.exists()
    # identical upload deduplicates to the same object
    sha2, path2 = backend.store(data, kind="png")
    assert (sha2, path2) == (sha, path)
    assert backend.load(sha, "png") == data
    assert backend.url_for(sha, "png") is None


def test_exif_metadata_stripped_on_save(tmp_path: Path) -> None:
    from PIL import Image

    img = Image.new("RGB", (8, 8), color=(1, 2, 3))
    exif = img.getexif()
    exif[271] = "VIRA-Camera"  # Make
    raw = io.BytesIO()
    img.save(raw, format="JPEG", exif=exif)
    data = raw.getvalue()
    assert b"VIRA-Camera" in data  # metadata present before save
    from app.services.storage import ALLOWED_MEDIA

    kind = validate_upload(data, "photo.jpg")
    assert kind == "jpg"
    clean = strip_image_metadata(data, kind)
    assert b"VIRA-Camera" not in clean
    # re-openable image
    img2 = Image.open(io.BytesIO(clean))
    assert img2.size == (8, 8)
    del ALLOWED_MEDIA


class _FakeS3Client:
    def __init__(self) -> None:
        self.puts: list[dict] = []
        self.objects: dict[str, bytes] = {}

    def put_object(self, **kw) -> dict:
        self.puts.append(kw)
        self.objects[kw["Key"]] = kw["Body"]
        return {}

    def get_object(self, *, Bucket: str, Key: str) -> dict:
        from io import BytesIO

        return {"Body": BytesIO(self.objects[Key])}

    def generate_presigned_url(self, op: str, *, Params: dict, ExpiresIn: int) -> str:
        return f"https://bucket.example/{Params['Key']}?op={op}&exp={ExpiresIn}"


def test_s3_backend_sse_presigned_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeS3Client()

    class _Boto3:
        @staticmethod
        def client(service: str, **kw):
            assert service == "s3"
            return fake

    monkeypatch.setitem(__import__("sys").modules, "boto3", _Boto3)
    backend = S3StorageBackend("vira-bucket", endpoint_url="http://minio:9000", sse="AES256")
    data = _png_with_exif()
    sha, key = backend.store(data, kind="png")
    assert key == f"{sha[:2]}/{sha[2:4]}/{sha}.png"
    # server-side encryption enforced on write
    assert fake.puts[0]["ServerSideEncryption"] == "AES256"
    assert fake.puts[0]["Bucket"] == "vira-bucket"
    assert backend.load(sha, "png") == data
    url = backend.url_for(sha, "png", expires_seconds=60)
    assert url is not None and url.startswith("https://bucket.example/")
    assert "exp=60" in url


def test_get_storage_switch(tmp_path: Path) -> None:
    class S:
        storage_provider = "local"
        receipt_dir = tmp_path

    assert isinstance(get_storage(S), LocalStorageBackend)

    class S3:
        storage_provider = "s3"
        receipt_dir = tmp_path
        s3_bucket = "b"
        s3_endpoint_url = ""
        s3_region = ""
        s3_sse = "AES256"

    assert isinstance(get_storage(S3), S3StorageBackend)

    class NoBucket:
        storage_provider = "s3"
        receipt_dir = tmp_path
        s3_bucket = ""

    with pytest.raises(UnsupportedMediaType):
        get_storage(NoBucket)


def test_save_receipt_with_local(tmp_path: Path) -> None:
    backend = LocalStorageBackend(tmp_path)
    meta = save_receipt_with(backend, _png_with_exif(), "scan.png")
    assert meta["sha256"]
    assert meta["media_type"] == "image/png"
    assert str(meta["storage_path"]).endswith(".png")
