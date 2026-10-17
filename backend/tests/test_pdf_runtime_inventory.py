"""Fail-closed native closure audit; mock import graphs are not rendering evidence."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture()
def tool():
    spec = importlib.util.spec_from_file_location(
        "pdf_runtime_inventory", Path(__file__).resolve().parents[2] / "scripts/pdf_runtime_inventory.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def metadata(raw):
    return {"imports": json.loads(raw), "machine": "AMD64", "version_resource": {}}


def test_transitive_closure_cycles_case_and_minimality(tool):
    files = {"A.dll": b'["B.dll", "KERNEL32.dll"]', "b.dll": b'["a.dll"]', "unused.dll": b"[]"}
    result = tool.dependency_closure(files, roots=("a.dll",), inspector=metadata)
    assert list(result) == ["a.dll", "b.dll"]
    assert result["a.dll"]["bundled_imports"] == ["b.dll"]
    assert result["a.dll"]["system_imports"] == ["kernel32.dll"]
    assert result["b.dll"]["sha256"] == hashlib.sha256(files["b.dll"]).hexdigest()
    assert all(entry["license_and_source_status"] == "UNREVIEWED" for entry in result.values())


@pytest.mark.parametrize("dependency", ["msvcp140.dll", "vcruntime140.dll", "libgcc_s_seh-1.dll", "libstdc++-6.dll", "missing.dll"])
def test_never_borrows_non_system_runtime_from_runner(tool, dependency):
    with pytest.raises(ValueError, match="Unresolved non-system"):
        tool.dependency_closure({"root.dll": json.dumps([dependency]).encode()}, roots=("root.dll",), inspector=metadata)


@pytest.mark.parametrize("name", ["../a.dll", "C:\\a.dll", "a/b.dll", "evil.exe", "a.dll?query", "\\\\server\\a.dll"])
def test_rejects_paths_or_non_dll_imports(tool, name):
    with pytest.raises(ValueError, match="Unsafe"):
        tool.dll_name(name)


def test_rejects_case_collision_and_python_abi(tool):
    with pytest.raises(ValueError, match="Case-colliding"):
        tool.dependency_closure({"a.dll": b"[]", "A.DLL": b"[]"}, roots=("a.dll",), inspector=metadata)
    with pytest.raises(ValueError, match="Python ABI"):
        tool.dependency_closure({"python314.dll": b"[]"}, roots=("python314.dll",), inspector=metadata)


@pytest.mark.parametrize("name", ["KERNEL32.DLL", "api-ms-win-crt-runtime-l1-1-0.dll", "ext-ms-win-ntuser-window-l1-1-0.dll"])
def test_explicit_windows_inbox_dependencies(tool, name):
    assert tool.is_system(name)


def test_invalid_pe_and_wrong_architecture_rejected(tool, monkeypatch):
    with pytest.raises(tool.pefile.PEFormatError):
        tool.inspect_pe(b"not a PE image")

    class PE:
        FILE_HEADER = SimpleNamespace(Machine=0x14c, Characteristics=0x2000)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(tool.pefile, "PE", lambda **kwargs: PE())
    with pytest.raises(ValueError, match="x64"):
        tool.inspect_pe(b"mock x86")


def test_archive_hash_checked_before_output(tool, tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(b"not the pinned archive")
    with pytest.raises(ValueError, match="SHA256"):
        tool.build_candidate(archive, tmp_path / "candidate")
    assert not (tmp_path / "candidate").exists()


def test_sdk_candidate_is_minimal_and_always_unapproved(tool, tmp_path, monkeypatch):
    archive = tmp_path / "fixture.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in tool.ROOTS:
            z.writestr("onedir/_internal/" + name, b"[]")
        z.writestr("onedir/_internal/python314.dll", b"[]")
        z.writestr("onedir/_internal/unused.dll", b"[]")
        z.writestr("onedir/weasyprint.exe", b"not copied")
    monkeypatch.setattr(tool, "SDK_SHA256", hashlib.sha256(archive.read_bytes()).hexdigest())
    monkeypatch.setattr(tool, "inspect_pe", metadata)
    # Explicit wrapper keeps the test's fake PE reader separate from rendering.
    real_closure = tool.dependency_closure
    monkeypatch.setattr(tool, "dependency_closure", lambda files: real_closure(files, inspector=metadata))
    output = tmp_path / "candidate"
    result = tool.build_candidate(archive, output)
    assert result["distribution_status"] == tool.BLOCKED
    assert result["excluded_upstream_dll_count"] == 2
    assert sorted(p.name for p in (output / "bin").iterdir()) == sorted(tool.ROOTS)
    assert (output / "DO_NOT_DISTRIBUTE.txt").is_file()
    assert json.loads((output / "runtime-inventory.json").read_text()) == result
    with pytest.raises(ValueError, match="already exist"):
        tool.build_candidate(archive, output)
