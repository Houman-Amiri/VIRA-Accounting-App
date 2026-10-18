"""Contracts/evidence parsing; real isolated Windows compilation is a separate CI gate."""
from __future__ import annotations

import importlib
import json
import random
from pathlib import Path

import pytest


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("audit_pdf_native_rebuild")


def compiler_log(tmp_path):
    path = tmp_path / "toolchains/detect_compiler/stdout-x64.log"
    path.parent.mkdir(parents=True)
    path.write_text("The C compiler identification is MSVC 19.51.1\nCompiler: C:/VS/cl.exe\n", encoding="utf-8")
    return path


def test_original_compiler_records_are_not_inferred_from_python(tool, tmp_path):
    (tmp_path / "python.txt").write_text("Python 3.11 MSC 1944", encoding="utf-8")
    with pytest.raises(ValueError, match="actual compiler"):
        tool.compiler_evidence(tmp_path, {})


def test_records_include_original_bytes_and_explicitly_pending_terms(tool, tmp_path):
    file = compiler_log(tmp_path)
    result = tool.compiler_evidence(tmp_path, {"installations": [], "license_files": []})
    assert result["distribution_status"] == tool.BLOCKED
    assert result["compiler_detection_records"][0]["sha256"] == tool.sha(file.read_bytes())
    assert "19.51.1" in json.dumps(result)
    assert result["no_installed_license_candidates"] is True
    assert result["compiler_crt_terms_review_status"].startswith("PENDING")


def test_finding_some_license_is_never_automatic_crt_permission(tool, tmp_path):
    compiler_log(tmp_path)
    file = tmp_path / "license.rtf"
    file.write_bytes(b"{\\rtf1 MICROSOFT license candidate}" + b"x" * 20000)
    result = tool.compiler_evidence(tmp_path, {"license_files": [str(file)]})
    assert result["installed_license_evidence"][0]["preview_truncated"] is True
    assert result["installed_license_evidence"][0]["sha256"] == tool.sha(file.read_bytes())
    assert result["compiler_crt_terms_review_status"].startswith("PENDING")
    assert result["legal_status"] == "EVIDENCE_ONLY_NOT_PERMISSION_OR_LEGAL_APPROVAL"


def test_truncated_compiler_lines_are_marked_not_silent(tool, tmp_path):
    path = compiler_log(tmp_path)
    path.write_text("MSVC compiler version\n" * 40, encoding="utf-8")
    record = tool.compiler_evidence(tmp_path, {})["compiler_detection_records"][0]
    assert record["matching_line_count"] == 40
    assert record["lines_truncated"] is True
    assert len(record["lines"]) == 30


@pytest.mark.parametrize("name", ["backend", "frontend", "pyproject.toml", "uv.lock", ".git"])
def test_application_presence_invalidates_independence(tool, tmp_path, name):
    (tmp_path / name).touch()
    with pytest.raises(ValueError, match="isolated native-only"):
        tool.audit_build(tmp_path, tmp_path / "work", {})


def test_emit_is_bounded_and_overflow_not_truncated(tool, tmp_path, capsys):
    path = tmp_path / "proof.json"
    path.write_text('{"evidence":"small"}', encoding="utf-8")
    tool.emit(path, 0)
    assert len(capsys.readouterr().out.splitlines()) == 1
    tool.emit(path, 1)
    assert capsys.readouterr().out == ""
    path.write_text(random.Random(0).randbytes(200000).hex(), encoding="utf-8")
    with pytest.raises(ValueError, match="refusing truncation"):
        tool.emit(path, 0)


@pytest.mark.parametrize("group", [-1, 4])
def test_invalid_groups_fail(tool, tmp_path, group):
    with pytest.raises(ValueError, match="Invalid evidence"):
        tool.emit(tmp_path / "missing", group)


def test_native_entry_point_is_not_the_app_staging_wrapper():
    path = Path(__file__).resolve().parents[2] / "scripts/rebuild_pdf_native.ps1"
    text = path.read_text(encoding="utf-8")
    for forbidden in ["stage_app_payload", "pdf_payload_smoke", "uv run", "pnpm", "GITHUB_ACTIONS"]:
        assert forbidden not in text
    for required in ["--binarysource=clear", "--host-triplet", "-PlanOnly", "refusing to overwrite", "OverlayPorts"]:
        # Switch is declared as $PlanOnly; invocation spelling is tested by CI.
        assert required.replace("-PlanOnly", "$PlanOnly") in text
