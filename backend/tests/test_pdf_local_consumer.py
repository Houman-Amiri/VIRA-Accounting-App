"""Private source-build -> real app handoff; no shipping permission or installed acceptance."""
from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("prepare_pdf_consumer_candidate")


@pytest.fixture()
def sample(tool, tmp_path, monkeypatch):
    work = tmp_path / "work"
    native = work / "installed" / tool.TRIPLET / "bin"
    native.mkdir(parents=True)
    files = {f"part-{i}.dll": f"fake-{i}".encode() for i in range(21)}
    for name, data in files.items():
        (native / name).write_bytes(data)
    closure = {n: {"sha256": hashlib.sha256(d).hexdigest(), "imports": [], "machine": "AMD64"} for n, d in files.items()}
    monkeypatch.setattr(tool, "dependency_closure", lambda files, **kw: json.loads(json.dumps(closure)))
    reference = {"vcpkg_commit": tool.BASELINE, "distribution_status": tool.BLOCKED,
                 "source_archive": None, "original_source_archive": {"sha256": "original"},
                 "new_corresponding_source_archive_prepared": False,
                 "source_packages": {f"pkg{i}": {"patched_source_files": 1, "patched_source_tree_sha256": str(i)} for i in range(20)},
                 "dlls": {n: {"source_package": "pango"} for n in files},
                 "roots": list(files), "preload_dlls": ["part-0.dll"]}
    proof = {"distribution_status": tool.BLOCKED, "native_compilation": "SUCCESS",
             "local_preferred_source_replay": "SUCCESS", "changed_packages": ["pango"],
             "actual_pango_version_string": tool.EXPECTED_VERSION,
             "input_source_trees_unchanged_during_compilation": True, "dll_count": 21,
             "dlls": {n: {"sha256": hashlib.sha256(d).hexdigest(), "source_package": "pango", "loaded_path": str(native / n)} for n, d in files.items()},
             "preferred_source_trees": {n: {"source_entries": 1, "tree_sha256": p["patched_source_tree_sha256"]} for n, p in reference["source_packages"].items()}}
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    ref = evidence / "reference.json"
    audit = evidence / "audit.json"
    ref.write_text(json.dumps(reference))
    audit.write_text(json.dumps(proof))
    return work, ref, audit, tmp_path / "candidate", reference, proof


def test_candidate_contains_only_audited_closure_with_modified_source_provenance(tool, sample):
    work, ref, audit, out, _, _ = sample
    result = tool.prepare(work, ref, audit, out)
    assert len(result["dlls"]) == 21
    assert len(list((out / "bin").iterdir())) == 21
    assert result["source_archive"] is None
    assert result["original_source_archive"] == {"sha256": "original"}
    assert result["private_consumption_only"] is True
    assert result["modified_build_is_distribution_candidate"] is False
    assert result["expected_pango_version_string"] == tool.EXPECTED_VERSION
    assert result["distribution_status"] == tool.BLOCKED
    assert result["native_audit_sha256"] == hashlib.sha256(audit.read_bytes()).hexdigest()
    assert (out / "DO_NOT_DISTRIBUTE.txt").read_text().strip() == tool.BLOCKED
    with pytest.raises(FileExistsError):
        tool.prepare(work, ref, audit, out)


@pytest.mark.parametrize("field,value", [
    ("distribution_status", "APPROVED"), ("native_compilation", "FAILURE"),
    ("local_preferred_source_replay", "PENDING"), ("changed_packages", []),
    ("actual_pango_version_string", "1.58.0"), ("input_source_trees_unchanged_during_compilation", False),
    ("dll_count", 27),
])
def test_unproven_or_old_sdk_handoff_rejected_before_creating_output(tool, sample, field, value):
    work, ref, audit, out, _, proof = sample
    proof[field] = value
    audit.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="evidence/reference required"):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


@pytest.mark.parametrize("field,value", [("source_archive", {"sha256": "old"}),
                                        ("new_corresponding_source_archive_prepared", True),
                                        ("vcpkg_commit", "different")])
def test_original_zip_cannot_be_relabelled_as_changed_binary_correspondence(tool, sample, field, value):
    work, ref, audit, out, reference, _ = sample
    reference[field] = value
    ref.write_text(json.dumps(reference))
    with pytest.raises(ValueError):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


@pytest.mark.parametrize("field,value", [("sha256", "wrong"), ("source_package", "unknown"), ("loaded_path", "foreign.dll")])
def test_each_dll_must_match_actual_audit_hash_origin_and_owner(tool, sample, field, value):
    work, ref, audit, out, _, proof = sample
    proof["dlls"]["part-0.dll"][field] = value
    audit.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match="hash/origin/owner"):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


def test_modified_source_reference_must_match_actual_build_tree(tool, sample):
    work, ref, audit, out, reference, _ = sample
    reference["source_packages"]["pkg0"]["patched_source_tree_sha256"] = "changed after audit"
    ref.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match="Source reference differs"):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


@pytest.mark.parametrize("where", ["work", "evidence"])
def test_outputs_cannot_mutate_native_or_proof_inputs(tool, sample, where):
    work, ref, audit, _, _, _ = sample
    out = (work if where == "work" else ref.parent) / "nested"
    with pytest.raises(ValueError, match="outside"):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


def test_consumer_stays_outside_native_build_mit_scope():
    scope = json.loads((ROOT / "docs/dependencies/pdf-build-script-license-scope.json").read_text())
    assert len(scope["files"]) == 14
    assert "scripts/prepare_pdf_consumer_candidate.py" not in scope["files"]
    assert "scripts/pdf_local_consumer_smoke.ps1" not in scope["files"]


def test_missing_preload_is_not_silently_borrowed_from_python_or_system(tool, sample):
    work, ref, audit, out, reference, _ = sample
    reference['preload_dlls'] = ['foreign-ffi.dll']
    ref.write_text(json.dumps(reference))
    with pytest.raises(ValueError, match='preload'):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


def test_unexpected_consumer_closure_is_rejected(tool, sample, monkeypatch):
    work, ref, audit, out, _, _ = sample
    monkeypatch.setattr(tool, 'dependency_closure', lambda *a, **kw: {})
    with pytest.raises(ValueError, match='closure differs'):
        tool.prepare(work, ref, audit, out)
    assert not out.exists()


@pytest.fixture()
def verifier_case(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    verifier = importlib.import_module('pdf_payload_verify')
    root = tmp_path / 'app'
    reports = tmp_path / 'reports'
    native = root / 'native/pdf/bin'
    native.mkdir(parents=True)
    reports.mkdir()
    (native / 'pango.dll').write_bytes(b'dll')
    (root / 'untouched.txt').write_bytes(b'production')
    (root / 'install_manifest.json').write_text(json.dumps({'files': [
        {'path': 'untouched.txt', 'sha256': hashlib.sha256(b'production').hexdigest()}]}))
    inventory = {'dlls': {'pango.dll': {'sha256': hashlib.sha256(b'dll').hexdigest()}},
                 'expected_pango_version_string': '1.58.0-vira-local-source',
                 'private_consumption_only': True, 'modified_build_is_distribution_candidate': False,
                 'source_archive': None}
    worker = {'isolated': 1, 'development_dependencies_absent': True, 'ctypes_callbacks_verified': True,
              'distribution_status': verifier.BLOCKED, 'pango_version_string': '1.58.0-vira-local-source',
              'expected_pango_version_string': '1.58.0-vira-local-source'}
    (root / 'native/pdf/runtime-inventory.json').write_text(json.dumps(inventory))
    (reports / 'worker-proof.json').write_text(json.dumps(worker))
    for name in ['single-page', 'multi-page']:
        (reports / (name + '.pdf')).write_bytes(name.encode())
    monkeypatch.setattr(verifier, 'inspect_pdf', lambda data, **kw: {'pages': 1 if data == b'single-page' else 4})
    return verifier, root, reports, worker, inventory


def test_post_render_checks_keep_production_manifest_and_modified_pango_contract(verifier_case):
    verifier, root, reports, _, _ = verifier_case
    result = verifier.verify(root, reports)
    assert result['documents']['single-page']['pages'] == 1
    assert result['documents']['multi-page']['pages'] == 4
    assert result['worker']['pango_version_string'] == '1.58.0-vira-local-source'
    (root / 'untouched.txt').write_bytes(b'accidental production mutation')
    with pytest.raises(ValueError, match='Original staged payload changed'):
        verifier.verify(root, reports)


@pytest.mark.parametrize('side,field,value', [
    ('worker', 'pango_version_string', '1.58.0'),
    ('worker', 'expected_pango_version_string', None),
    ('inventory', 'private_consumption_only', False),
    ('inventory', 'modified_build_is_distribution_candidate', True),
    ('inventory', 'source_archive', {'sha256': 'old-unmodified-archive'}),
])
def test_rendered_consumer_cannot_lose_its_modified_source_and_private_status(verifier_case, side, field, value):
    verifier, root, reports, worker, inventory = verifier_case
    if side == 'worker':
        worker[field] = value
        (reports / 'worker-proof.json').write_text(json.dumps(worker))
    else:
        inventory[field] = value
        (root / 'native/pdf/runtime-inventory.json').write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match='executed modified Pango and remain private'):
        verifier.verify(root, reports)
