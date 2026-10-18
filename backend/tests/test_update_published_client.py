"""Fast checks for the release gate; not a substitute for the Windows journey."""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    return importlib.import_module("scripts.update_native_smoke")


def payload(root: Path, name: str = "app/main.py") -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"immutable client bytes")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "path": name,
                        "size": file.stat().st_size,
                        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    }
                ]
            }
        )
    )
    return file


def test_shipped_payload_verified_without_rebuilding(tmp_path, harness):
    file = payload(tmp_path)
    harness.verify_payload(tmp_path)
    file.write_bytes(b"changed client")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path)


@pytest.mark.parametrize(
    "relative",
    ["../outside.py", "/outside.py", r"C:\outside.py", "C:outside.py", r"app\..\outside.py"],
)
def test_manifest_escape_rejected(tmp_path, harness, relative):
    (tmp_path / "install_manifest.json").write_text(json.dumps({"files": [{"path": relative}]}))
    with pytest.raises(ValueError, match="unsafe"):
        harness.verify_payload(tmp_path)


def test_runtime_cache_exception_is_not_a_source_file_exception(tmp_path, harness):
    cached = payload(tmp_path, "app/__pycache__/module.pyc")
    cached.write_bytes(b"regenerated after boot")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path)
    harness.verify_payload(tmp_path, runtime=True)
    source = payload(tmp_path, "app/main.py")
    source.write_bytes(b"bad source after boot")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path, runtime=True)


def test_public_asset_digest_cannot_be_substituted(tmp_path, harness):
    base = tmp_path / "base-1.0.9"
    base.mkdir()
    (tmp_path / "base-1.0.9.zip").write_bytes(b"not the public payload")
    with pytest.raises(ValueError, match="ZIP digest mismatch"):
        harness.PublishedUpgrade(base, tmp_path / "packages").validate()


def test_failure_diagnostics_survive_windows_code_page(tmp_path, harness, monkeypatch):
    import io

    file = tmp_path / "server.log"
    file.write_bytes("خطای راه‌اندازی — 100%\r\nnext".encode("utf-8"))
    buffer = io.BytesIO()
    stdout = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(harness.sys, "stdout", stdout)
    harness.emit_diagnostic(file)
    text = buffer.getvalue().decode("ascii")
    assert "::error title=phase8 server.log::" in text
    assert r"\u062e" in text
    assert r"\u2014" in text
    assert "100%25%0Anext" in text
