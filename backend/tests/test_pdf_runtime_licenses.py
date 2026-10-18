"""Notices cannot promote a private source proof into distribution approval."""
from __future__ import annotations

import copy
import importlib
import json
import random
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("pdf_runtime_licenses")


@pytest.fixture()
def inputs(tool):
    deps = ROOT / "docs/dependencies"
    inv = json.loads((deps / "pdf-runtime-win64-source-inventory.json").read_text())
    policy = json.loads((deps / "pdf-runtime-license-policy.json").read_text())
    files = {}
    for key, required in policy["supplements"].items():
        text = "\n".join(required["required_text"]) + "\n" + "x" * required["minimum_bytes"]
        files[key] = {"archive_path": f"sources/{required['package']}/root/{required['relative_path']}",
                      "sha256": tool.sha(text.encode()), "text": text}
    materials = {"schema": 1, "source_archive": copy.deepcopy(inv["source_archive"]),
                 "verified_source_materials": {"packages": 20}, "files": files}
    return inv, policy, materials


def test_all_native_owners_and_alias_are_explicitly_covered(tool, inputs):
    inv, policy, materials = inputs
    tool.validate_materials(inv, policy, materials)
    assert len(policy["packages"]) == 20
    assert len(inv["dlls"]) == 21
    assert policy["packages"]["freetype"]["selected_license"] == "FTL"
    assert "PCRE2-exception" in policy["packages"]["pcre2"]["selected_license"]
    assert policy["packages"]["libiconv"]["expected_declared_license"] is None


@pytest.mark.parametrize("mutation,error", [
    (lambda i, p: i["source_packages"].pop("brotli"), "coverage"),
    (lambda i, p: i["source_packages"]["glib"].update(declared_port_license="MIT"), "declaration"),
    (lambda i, p: i["source_packages"]["pthread"].update(delegated_license_packages=[]), "alias"),
    (lambda i, p: i.update(distribution_status="APPROVED"), "blocked"),
    (lambda i, p: p.update(distribution_status="APPROVED"), "blocked"),
    (lambda i, p: i["source_archive"].update(sha256="0" * 64), "Pinned"),
    (lambda i, p: p["packages"]["freetype"].update(selected_license=""), "selection"),
    (lambda i, p: i["source_packages"]["libiconv"].update(copyright_text="forged"), "copyright"),
    (lambda i, p: i.update(vcpkg_commit="0" * 40), "Pinned"),
])
def test_policy_drift_is_fail_closed(tool, inputs, mutation, error):
    inv, policy, _ = inputs
    mutation(inv, policy)
    with pytest.raises(ValueError, match=error):
        tool.validate_policy(inv, policy)


@pytest.mark.parametrize("mutation,error", [
    (lambda m: m["files"].pop("pcre2-sljit-license"), "coverage"),
    (lambda m: m["source_archive"].update(sha256="0" * 64), "archive"),
    (lambda m: m["files"]["pcre2-full-license"].update(text="forged"), "bytes"),
    (lambda m: m["files"]["pcre2-full-license"].update(archive_path="sources/pcre2/root/../LICENCE.md"), "source path"),
    (lambda m: m["files"]["pcre2-full-license"].update(archive_path="sources/other/root/LICENCE.md"), "source path"),
])
def test_supplement_coverage_and_bytes_are_bound(tool, inputs, mutation, error):
    inv, policy, materials = inputs
    mutation(materials)
    with pytest.raises(ValueError, match=error):
        tool.validate_materials(inv, policy, materials)


@pytest.mark.parametrize("text", ["See LICENCE", "x" * 5000])
def test_forwarding_stub_or_missing_conditions_never_count_as_pcre2_license(tool, inputs, text):
    inv, policy, materials = inputs
    materials["files"]["pcre2-full-license"].update(text=text, sha256=tool.sha(text.encode()))
    with pytest.raises(ValueError, match="bytes|license text"):
        tool.validate_materials(inv, policy, materials)


def test_render_is_deterministic_and_never_grants_approval(tool, inputs):
    inv, policy, materials = inputs
    text, review = tool.render(inv, policy, materials)
    assert (text, review) == tool.render(inv, policy, materials)
    assert review["distribution_status"] == tool.BLOCKED
    assert review["materials_status"] == "PREPARED_FOR_REVIEW_NOT_APPROVED"
    assert review["notices_sha256"] == tool.sha(text.encode())
    assert "1996-2026 The FreeType Project" in text
    assert "reverse engineer" in text
    assert len(review["open_gates"]) == 6
    assert "BSD-2-Clause" in text


def test_collection_refuses_unverified_source_even_if_supplements_look_valid(tool, inputs, monkeypatch, tmp_path):
    inv, policy, _ = inputs
    verifier = importlib.import_module("pdf_source_evidence")

    def fail(*args):
        raise ValueError("Source archive hash/size mismatch")

    monkeypatch.setattr(verifier, "verify_sources", fail)
    with pytest.raises(ValueError, match="archive hash"):
        tool.collect_materials(inv, policy, tmp_path / "missing.zip")


def test_collection_requires_unique_real_source_file(tool, inputs, monkeypatch, tmp_path):
    inv, policy, materials = inputs
    verifier = importlib.import_module("pdf_source_evidence")
    monkeypatch.setattr(verifier, "verify_sources", lambda *_: {"packages": 20})
    archive = tmp_path / "source.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for item in materials["files"].values():
            bundle.writestr(item["archive_path"], item["text"])
    assert tool.collect_materials(inv, policy, archive)["files"] == materials["files"]
    with zipfile.ZipFile(archive, "a") as bundle:
        bundle.writestr("sources/pcre2/second-root/LICENCE.md", "extra")
    with pytest.raises(ValueError, match="exactly one"):
        tool.collect_materials(inv, policy, archive)


def test_bounded_annotations_are_not_silently_truncated(tool, capsys):
    tool.emit({"small": "evidence"}, 0)
    assert len(capsys.readouterr().out.splitlines()) == 1
    tool.emit({"small": "evidence"}, 1)
    assert capsys.readouterr().out == ""
    with pytest.raises(ValueError, match="truncated"):
        tool.emit({"large": random.Random(0).randbytes(400000).hex()}, 0)


@pytest.mark.parametrize("group", [-1, 8])
def test_invalid_annotation_groups_fail(tool, group):
    with pytest.raises(ValueError, match="annotation group"):
        tool.emit({}, group)


def test_mandatory_gates_and_full_inventory_binding(tool, inputs):
    inv, policy, _ = inputs
    policy["open_gates"] = []
    with pytest.raises(ValueError, match="gates"):
        tool.validate_policy(inv, policy)
    policy["open_gates"] = [{"id": key} for key in tool.REQUIRED_GATES]
    inv["dlls"][next(iter(inv["dlls"]))]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="fingerprint"):
        tool.validate_policy(inv, policy)
