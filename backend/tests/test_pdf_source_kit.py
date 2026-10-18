"""Synthetic archive security/contracts; real source kit is verified separately in CI."""
from __future__ import annotations

import hashlib
import importlib
import io
import json
import stat
import zipfile
from pathlib import Path

import pytest


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("pdf_source_kit")


def archive(items):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        for name, content, link in items:
            info = zipfile.ZipInfo(name)
            info.create_system = 3
            info.external_attr = ((stat.S_IFLNK if link else stat.S_IFREG) | 0o755) << 16
            z.writestr(info, content)
    stream.seek(0)
    return zipfile.ZipFile(stream)


@pytest.mark.parametrize("name", ["/absolute", "../escape", "a/../b", "a//b", "a/./b", r"a\b", "C:escape", "a\0b", ""])
def test_unsafe_paths_rejected(tool, name):
    with pytest.raises(ValueError, match="Unsafe"):
        tool.relative(name)


@pytest.mark.parametrize("items,error", [
    ([("sources/a/file", "x", False), ("sources/a/FILE", "y", False)], "colliding"),
    ([("sources/a/link", "../../outside", True)], "escapes"),
    ([("sources/a/link", "/outside", True)], "Unsafe symlink"),
    ([("sources/a/link", "C:outside", True)], "Unsafe symlink"),
    ([("sources/a/link", "missing", True)], "Dangling"),
    ([("sources/a/a", "b", True), ("sources/a/b", "a", True)], "Cyclic"),
    ([("sources/a/link", "dir", True), ("sources/a/link/file", "x", False)], "symlink ancestor"),
    ([("sources/a/file", "x", False), ("sources/a/file/sub", "y", False)], "ancestor collision"),
    ([("sources/a/NUL.txt", "x", False)], "Nonportable"),
    ([("sources/a/file.", "x", False)], "Nonportable"),
])
def test_unsafe_archive_rejected_before_extraction(tool, items, error):
    with archive(items) as z, pytest.raises(ValueError, match=error):
        tool.source_entries(z)


def test_safe_relative_links_kept_as_links(tool):
    with archive([("sources/a/COPYING", "LICENSES/L.txt", True),
                  ("sources/a/LICENSES/L.txt", "license", False)]) as z:
        entries, links = tool.source_entries(z)
        assert len(entries) == 2
        assert links == {"sources/a/COPYING": "LICENSES/L.txt"}


def test_wrong_original_archive_never_creates_output(tool, tmp_path):
    source = tmp_path / "bad.zip"
    source.write_bytes(b"not pinned")
    with pytest.raises(ValueError, match="pinned"):
        tool.verify_sources(source, {"source_archive": {"sha256": "0" * 64}})


def test_external_hash_checked_before_loading_envelope_code(tool, tmp_path):
    (tmp_path / "kit-manifest.json").write_text("{}")
    with pytest.raises(ValueError, match="External manifest hash"):
        tool.verify(tmp_path, "0" * 64)


def test_unmanifested_payload_rejected(tool, tmp_path):
    (tmp_path / "kit-manifest.json").write_text(json.dumps({"schema": 1, "distribution_status": tool.BLOCKED,
        "status": "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY", "files": {}}))
    (tmp_path / "unexpected.dll").write_bytes(b"MZ")
    with pytest.raises(ValueError, match="unmanifested"):
        tool.verify(tmp_path)


def test_tampered_file_rejected_before_loading_scope_checker(tool, tmp_path):
    (tmp_path / "README.txt").write_bytes(b"changed")
    (tmp_path / "kit-manifest.json").write_text(json.dumps({"schema": 1, "distribution_status": tool.BLOCKED,
        "status": "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY", "files": {"README.txt": {
            "sha256": hashlib.sha256(b"original").hexdigest(), "size": 8}}}))
    with pytest.raises(ValueError, match="hash/size"):
        tool.verify(tmp_path)


def test_scope_loader_never_pollutes_read_only_envelope_with_pyc(tool, tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/check_pdf_build_license.py").write_text("VALUE = 1\n")
    assert tool.checker(tmp_path).VALUE == 1
    assert not list(tmp_path.rglob("__pycache__"))


def test_existing_extraction_directory_is_never_overwritten(tool, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    with archive([("sources/a/file", "original", False)]) as z:
        (kit / "corresponding-source.zip").write_bytes(z.fp.getvalue())
    monkeypatch.setattr(tool, "verify", lambda *a: {})
    dest = tmp_path / "existing"
    dest.mkdir()
    sentinel = dest / "database.sqlite3"
    sentinel.write_bytes(b"user data")
    with pytest.raises(FileExistsError):
        tool.extract_sources(kit, dest)
    assert sentinel.read_bytes() == b"user data"


def test_real_extraction_preserves_links_and_scripts(tool, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    with archive([("sources/a/sub/script.sh", "#!/bin/sh\n", False),
                  ("sources/a/link", "sub/script.sh", True)]) as z:
        (kit / "corresponding-source.zip").write_bytes(z.fp.getvalue())
    monkeypatch.setattr(tool, "verify", lambda *a: {})
    dest = tmp_path / "new-sources"
    try:
        tool.extract_sources(kit, dest)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            # Explicitly test the documented refusal, not silent flattening.
            assert not (dest / "sources/a/link").exists()
            assert (dest / "sources/a/sub/script.sh").is_file()
            return
        raise
    assert (dest / "sources/a/link").is_symlink()
    assert (dest / "sources/a/link").read_bytes() == b"#!/bin/sh\n"


def test_inspection_never_executes_checker_from_target_kit(tool, tmp_path):
    injected = tmp_path / "licensed-build-files/scripts/check_pdf_build_license.py"
    injected.parent.mkdir(parents=True)
    injected.write_text("raise RuntimeError('UNTRUSTED CODE EXECUTED')\n")
    name = injected.relative_to(tmp_path).as_posix()
    (tmp_path / "kit-manifest.json").write_text(json.dumps({"schema": 1, "distribution_status": tool.BLOCKED,
        "status": "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY", "files": {
            name: {"sha256": tool.sha_file(injected), "size": injected.stat().st_size}}}))
    with pytest.raises(FileNotFoundError):
        tool.verify(tmp_path)


@pytest.mark.parametrize("escape_kind", ["symlink", "junction"])
def test_envelope_rejects_external_entries_without_platform_privileges(tool, tmp_path, monkeypatch, escape_kind):
    (tmp_path / "kit-manifest.json").write_text(json.dumps({"schema": 1, "distribution_status": tool.BLOCKED,
        "status": "PRIVATE_REVIEW_KIT_NOT_RECIPIENT_DELIVERY", "files": {}}))
    target = tmp_path / "unsafe"
    target.write_bytes(b"x")
    if escape_kind == "symlink":
        original = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda p: p == target or original(p))
    else:
        original = Path.resolve
        monkeypatch.setattr(Path, "resolve", lambda p, **kw: tmp_path.parent / "outside" if p == target else original(p, **kw))
    with pytest.raises(ValueError, match="external/junction"):
        tool.verify(tmp_path)


def test_windows_nested_symlink_targets_use_native_separators(tool, monkeypatch, tmp_path):
    kit = tmp_path / "kit"
    kit.mkdir()
    with archive([("sources/a/sub/file", "actual", False),
                  ("sources/a/link", "sub/file", True)]) as z:
        (kit / "corresponding-source.zip").write_bytes(z.fp.getvalue())
    monkeypatch.setattr(tool, "verify", lambda *a: {})
    seen = []
    monkeypatch.setattr(tool.os, "sep", "\\")
    monkeypatch.setattr(tool.os, "symlink", lambda target, path, **kw: seen.append((target, kw)))
    tool.extract_sources(kit, tmp_path / "new-sources")
    assert seen == [("sub\\file", {"target_is_directory": False})]
