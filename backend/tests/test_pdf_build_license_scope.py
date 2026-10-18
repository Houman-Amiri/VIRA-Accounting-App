"""Owner consent for native build files must never relicense the application."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("check_pdf_build_license")


@pytest.fixture()
def scope(tool):
    return json.loads((ROOT / tool.SCOPE_PATH).read_text(encoding="utf-8"))


@pytest.fixture()
def workspace(tool, scope, tmp_path):
    for name in [*scope["files"], tool.LICENSE_PATH, tool.SCOPE_PATH]:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / name).read_bytes())
    return tmp_path


def test_actual_grant_is_narrow_and_runtime_remains_blocked(tool, scope):
    result = tool.verify(ROOT, scope)
    assert result["license_id"] == "MIT"
    assert result["licensed_file_count"] == 14
    assert result["application_license_changed"] is False
    assert result["release_authorized"] is False
    assert result["runtime_distribution_status"] == tool.BLOCKED
    assert result["standalone_recipe_completeness"] == "NOT_PROVEN_BY_LICENSE_GRANT"
    assert len(tool.ARCHIVED_MEMBERS) == 7
    assert not any(name.startswith(("backend/", "frontend/", "installer/")) for name in scope["files"])


@pytest.mark.parametrize("path", ["backend/app/main.py", "frontend/src/main.tsx", "native/**", "../outside.py"])
def test_grant_cannot_expand_to_application_or_wildcards(tool, scope, path):
    scope["files"][path] = {"sha256_lf": "0" * 64}
    with pytest.raises(ValueError, match="allowlist"):
        tool.verify(ROOT, scope)


def test_every_approved_file_is_explicitly_accounted_for(tool, scope):
    scope["files"].pop("scripts/pdf_runtime_inventory.py")
    with pytest.raises(ValueError, match="allowlist"):
        tool.verify(ROOT, scope)


@pytest.mark.parametrize("field", ["application_license_changed", "release_authorized"])
def test_owner_yes_cannot_be_reinterpreted_as_broader_authorization(tool, scope, field):
    scope["owner_authorization"][field] = True
    with pytest.raises(ValueError, match="Owner consent"):
        tool.verify(ROOT, scope)


@pytest.mark.parametrize("field,value,error", [
    ("license_id", "GPL-3.0", "license"),
    ("license_file", "LICENSE", "license"),
    ("hash_format", "ARBITRARY_NORMALIZATION", "hash format"),
    ("runtime_distribution_status", "APPROVED", "blocked"),
    ("source_archive_sha256", "0" * 64, "archive reference"),
])
def test_grant_metadata_is_fail_closed(tool, scope, field, value, error):
    scope[field] = value
    with pytest.raises(ValueError, match=error):
        tool.verify(ROOT, scope)


@pytest.mark.parametrize("field,value,error", [
    ("corresponding_source_member", "sources/glib/LICENSE", "scope binding"),
    ("source_build_reference_commit", "0" * 40, "source commit"),
])
def test_archived_wrapper_grant_cannot_relicense_upstream_sources(tool, scope, field, value, error):
    scope["files"]["scripts/source_pdf_inventory.py"][field] = value
    with pytest.raises(ValueError, match=error):
        tool.verify(ROOT, scope)


def test_reference_file_edits_need_explicit_scope_update(tool, scope, workspace):
    path = workspace / "scripts/source_pdf_inventory.py"
    path.write_bytes(path.read_bytes() + b"\n# changed\n")
    with pytest.raises(ValueError, match="content changed"):
        tool.verify(workspace, scope)


def test_windows_checkout_crlf_does_not_change_the_grant(tool, scope, workspace):
    for name in [*scope["files"], tool.LICENSE_PATH]:
        path = workspace / name
        path.write_bytes(tool.canonical(path.read_bytes()).replace(b"\n", b"\r\n"))
    assert tool.verify(workspace, scope) == tool.verify(ROOT, scope)


def test_canonical_hash_does_not_hide_unicode_or_other_source_edits(tool):
    assert tool.digest("# ©\r\n".encode()) == tool.digest("# ©\n".encode())
    assert tool.digest("# ©\n".encode()) != tool.digest("# Â©\n".encode())
    with pytest.raises(UnicodeDecodeError):
        tool.canonical(b"\xff")


def test_mit_text_cannot_be_omitted_or_changed(tool, scope, workspace):
    license_path = workspace / tool.LICENSE_PATH
    license_path.write_text("MIT License\n", encoding="utf-8")
    with pytest.raises(ValueError, match="license bytes"):
        tool.verify(workspace, scope)
    modified = copy.deepcopy(scope)
    modified["license_sha256_lf"] = tool.digest(license_path.read_bytes())
    with pytest.raises(ValueError, match="Incomplete MIT"):
        tool.verify(workspace, modified)


def test_symlinked_reference_is_rejected_without_requiring_os_privileges(tool, scope, workspace, monkeypatch):
    target = workspace / "scripts/source_pdf_inventory.py"
    original = Path.is_symlink
    monkeypatch.setattr(Path, "is_symlink", lambda self: self == target or original(self))
    with pytest.raises(ValueError, match="symlinked"):
        tool.verify(workspace, scope)


def test_cli_writes_explicit_review_status_not_distribution_approval(tool, scope, workspace, monkeypatch, capsys):
    out = workspace / "report/result.json"
    monkeypatch.setattr(tool, "ROOT", workspace)
    monkeypatch.setattr("sys.argv", ["check_pdf_build_license.py", "--out", str(out)])
    tool.main()
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result == json.loads(capsys.readouterr().out)
    assert result["runtime_distribution_status"] == tool.BLOCKED
    assert b"\r\n" not in out.read_bytes()


def test_sidecar_contains_only_licensed_sources_and_grant(tool, scope, workspace, tmp_path):
    target = tmp_path / "licensed-sidecar"
    tool.write_sidecar(workspace, scope, target)
    expected = {*tool.ALLOWED_FILES, tool.LICENSE_PATH, tool.SCOPE_PATH, "README.txt"}
    actual = {p.relative_to(target).as_posix() for p in target.rglob("*") if p.is_file()}
    assert actual == expected
    for name in expected - {"README.txt"}:
        assert (target / name).read_bytes() == (workspace / name).read_bytes()
    assert tool.verify(target, scope)["runtime_distribution_status"] == tool.BLOCKED
    assert "NOT the whole application" in (target / "README.txt").read_text(encoding="utf-8")
    assert not any(p.suffix.lower() in {".dll", ".exe", ".sqlite3"} for p in target.rglob("*"))


def test_invalid_grant_never_creates_sidecar(tool, scope, workspace, tmp_path):
    scope["files"]["backend/app/main.py"] = {"sha256_lf": "0" * 64}
    target = tmp_path / "rejected-sidecar"
    with pytest.raises(ValueError, match="allowlist"):
        tool.write_sidecar(workspace, scope, target)
    assert not target.exists()


def test_sidecar_never_overwrites_existing_data(tool, scope, workspace, tmp_path):
    target = tmp_path / "existing"
    target.mkdir()
    sentinel = target / "user-data.txt"
    sentinel.write_bytes(b"untouched")
    with pytest.raises(FileExistsError):
        tool.write_sidecar(workspace, scope, target)
    assert list(target.iterdir()) == [sentinel]
    assert sentinel.read_bytes() == b"untouched"
