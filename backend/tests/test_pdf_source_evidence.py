"""Verify immutable producer identity and source evidence without executing DLLs."""
from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("pdf_source_evidence")


@pytest.mark.parametrize("field,value", [("id", 2), ("head_sha", "b" * 40), ("path", "other.yml"), ("conclusion", "failure")])
def test_rejects_other_or_failed_producer(tool, field, value):
    expected = {"run_id": 1, "head_sha": "a" * 40, "workflow_path": "source.yml"}
    actual = {"id": 1, "head_sha": "a" * 40, "path": "source.yml", "conclusion": "success"}
    actual[field] = value
    with pytest.raises(ValueError, match="exact successful"):
        tool.validate_run(actual, expected)


def test_exact_producer_accepted(tool):
    tool.validate_run({"id": 1, "head_sha": "a", "path": "source.yml", "conclusion": "success"},
                      {"run_id": 1, "head_sha": "a", "workflow_path": "source.yml"})


def test_worker_origin_uses_windows_path_semantics_even_on_linux(tool):
    worker = {"isolated": 1, "development_dependencies_absent": True, "ctypes_callbacks_verified": True,
              "distribution_status": tool.BLOCKED, "python": "D:/VIRA چاپ/python/python.exe",
              "loaded_dlls": {"one.dll": "d:/vira چاپ/native/pdf/bin/one.dll"}}
    inventory = {"roots": ["one.dll"], "dlls": {"one.dll": {}}}
    tool.verify_worker(worker, inventory)
    worker["loaded_dlls"]["one.dll"] = "C:/Windows/one.dll"
    with pytest.raises(ValueError, match="Foreign native"):
        tool.verify_worker(worker, inventory)


def test_material_reverification_checks_actual_source_and_copyright_bytes(tool, tmp_path):
    import hashlib

    source, copyright_bytes = b"/* preferred source */", b"upstream license"
    spdx = json.dumps({"packages": [{"name": "pkg"}]}).encode()
    tree_hash = hashlib.sha256(b"root/a.c\0file\0" + tool.sha(source).encode() + b"\n").hexdigest()
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("sources/pkg/root/a.c", source)
        bundle.writestr("installed-notices/pkg/copyright", copyright_bytes)
        bundle.writestr("installed-notices/pkg/vcpkg.spdx.json", spdx)
    inventory = {
        "origin": "LOCAL_PINNED_VCPKG_SOURCE_BUILD", "distribution_status": tool.BLOCKED,
        "source_tree_hash_format": tool.HASH_FORMAT,
        "source_archive": {"sha256": tool.sha(archive.read_bytes()), "size": archive.stat().st_size},
        "dlls": {"one.dll": {"source_package": "pkg"}},
        "source_packages": {"pkg": {
            "patched_source_files": 1, "patched_source_tree_sha256": tree_hash,
            "patched_source_symlinks": {}, "copyright_sha256": tool.sha(copyright_bytes),
            "copyright_text": copyright_bytes.decode(), "copyright_text_utf8_lossless": True,
            "spdx_sha256": tool.sha(spdx), "spdx_packages": [{"name": "pkg"}],
            "source_status": "PATCHED_TREE_CAPTURED", "selected_dlls": ["one.dll"],
        }},
    }
    assert tool.verify_sources(inventory, archive) == {"packages": 1, "source_files": 1, "source_symlinks": 0}
    inventory["source_packages"]["pkg"]["copyright_text"] = "forged notice"
    with pytest.raises(ValueError, match="Copyright bytes"):
        tool.verify_sources(inventory, archive)


def test_metadata_chunks_never_silently_exceed_step_budget(tool, capsys):
    tool.emit_chunks({"evidence": "small"}, 0)
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert '"part": 0' in lines[0]
    tool.emit_chunks({"evidence": "small"}, 1)
    assert capsys.readouterr().out == ""
