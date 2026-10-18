"""Bounded local-target source adapters: hash pinning, safety and explicit edits."""
from __future__ import annotations

import hashlib
import importlib
import json
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    return importlib.import_module("prepare_pdf_local_sources")


def pin(tool, recipe):
    return {"port_sha256": tool.sha(recipe.replace("\r\n", "\n").encode()),
            "archived_port_sha256": tool.sha(recipe.encode()),
            "roots": ["v1.clean"], "acquisition_calls": len(list(tool.calls(recipe)))}


def test_only_source_acquisitions_replaced_not_build_tools_or_patches(tool):
    recipe = '''vcpkg_download_distfile(ARCHIVE URLS "https://original/source")
vcpkg_extract_source_archive(SOURCE_PATH ARCHIVE "${ARCHIVE}" PATCHES first.patch)
vcpkg_find_acquire_program(PYTHON3)
vcpkg_configure_meson(SOURCE_PATH "${SOURCE_PATH}")
'''
    result = tool.transformed_port("pango", recipe, pin(tool, recipe))
    assert "vcpkg_download_distfile(" not in result
    assert "vcpkg_extract_source_archive(" not in result
    assert "PATCHES first.patch" not in result  # Already applied in preferred tree.
    assert "vcpkg_find_acquire_program(PYTHON3)" in result
    assert 'vcpkg_configure_meson(SOURCE_PATH "${SOURCE_PATH}")' in result


def test_pcre_merged_sljit_never_deleted_or_patched_twice(tool):
    recipe = '''vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH REPO PCRE2/pcre2)
vcpkg_from_github(OUT_SOURCE_PATH SLJIT_SOURCE_PATH REPO zherczeg/sljit)
''' + tool.PCRE_MERGE
    result = tool.transformed_port("pcre2", recipe, pin(tool, recipe))
    assert "file(REMOVE_RECURSE" not in result
    assert "file(RENAME" not in result
    assert "already integrated" in result
    changed = recipe.replace('file(RENAME', 'file( RENAME')
    with pytest.raises(ValueError, match="merge changed"):
        tool.transformed_port("pcre2", changed, pin(tool, changed))


@pytest.mark.parametrize("change", ["# comment\n", "\nmessage(FATAL_ERROR bad)\n"])
def test_even_small_upstream_port_edits_fail_hash_pin(tool, change):
    recipe = 'vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH REPO a/b)\n'
    with pytest.raises(ValueError, match="recipe changed"):
        tool.transformed_port("pango", recipe + change, pin(tool, recipe))


@pytest.mark.parametrize("recipe", [
    'vcpkg_extract_source_archive(OTHER ARCHIVE a)',
    'vcpkg_from_github(OUT_SOURCE_PATH OTHER REPO a/b)',
    'message(STATUS "no source acquisition")',
    'vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH)\nvcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH)',
])
def test_bounded_acquisition_grammar_is_fail_closed(tool, recipe):
    with pytest.raises(ValueError):
        tool.transformed_port("pango", recipe, pin(tool, recipe))


def test_parser_handles_parentheses_strings_and_comments(tool):
    text = '''vcpkg_from_github(
OUT_SOURCE_PATH SOURCE_PATH # comment with )
REPO "a/(b)" OPTIONS (nested)
)'''
    assert len(list(tool.calls(text))) == 1
    assert "vcpkg_from_github(" not in tool.transformed_port("pango", text, pin(tool, text))
    with pytest.raises(ValueError, match="Unbalanced"):
        list(tool.calls("vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH"))


def test_crlf_pinned_recipe_is_portable(tool):
    text = "vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH)\r\n"
    assert tool.transformed_port("pango", text, pin(tool, text)) == tool.transformed_port("pango", text.replace("\r\n", "\n"), pin(tool, text))


def test_target_only_wrapper_preserves_host_recipe_and_rejects_unavailable_apng(tool, tmp_path):
    text = tool.wrapper("libpng", tmp_path / "root.clean", "root.clean")
    assert text.index('if(NOT TARGET_TRIPLET STREQUAL "x64-vira-pdf")') < text.index('file(REMOVE_RECURSE')
    assert 'include("${CMAKE_CURRENT_LIST_DIR}/upstream-portfile.cmake")\n    return()' in text
    assert 'if("apng" IN_LIST FEATURES)' in text
    assert 'file(COPY "' in text
    assert 'file(REMOVE_RECURSE "${CURRENT_BUILDTREES_DIR}/src")' in text
    assert "vcpkg_download_distfile" not in text
    assert "file(COPY" not in tool.wrapper("pthread", None, None)


@pytest.mark.parametrize("char", ['"', ";", "$", "[", "]", "\n", "\r"])
def test_cmake_injection_paths_rejected(tool, tmp_path, char):
    with pytest.raises(ValueError, match="metacharacters"):
        tool.cmake_path(tmp_path / ("unsafe" + char))


def test_real_tree_digest_matches_captured_inventory_algorithm(tool, tmp_path):
    (tmp_path / "a").write_bytes(b"actual")
    expected = hashlib.sha256(b"a\0file\0" + hashlib.sha256(b"actual").hexdigest().encode() + b"\n").hexdigest()
    assert tool.tree_record(tmp_path) == {"patched_source_files": 1, "patched_source_tree_sha256": expected, "patched_source_symlinks": {}}


def test_local_input_mutation_detected_after_compilation(tool, tmp_path):
    file = tmp_path / "test.c"
    file.write_bytes(b"before")
    receipt = {"packages": {"pango": {**tool.tree_record(tmp_path), "source_path": str(tmp_path)}}}
    tool.check_inputs(receipt)
    file.write_bytes(b"after")
    with pytest.raises(ValueError, match="mutated during compilation"):
        tool.check_inputs(receipt)


@pytest.mark.skipif(__import__("sys").platform == "win32", reason="Synthetic links tested on Linux; native workflow requires real links")
def test_external_and_dangling_source_links_fail_closed(tool, tmp_path):
    base = tmp_path / "source"
    base.mkdir()
    (base / "link").symlink_to("../external")
    with pytest.raises(ValueError, match="External"):
        tool.tree_record(base)
    (base / "link").unlink()
    (base / "link").symlink_to("missing")
    with pytest.raises(ValueError, match="Dangling"):
        tool.tree_record(base)


@pytest.fixture()
def synthetic(tool, tmp_path, monkeypatch):
    kit = tmp_path / "kit"
    kit.mkdir()
    sources = tmp_path / "preferred"
    root = sources / "sources/pango/v1.clean"
    root.mkdir(parents=True)
    (root / "test.c").write_bytes(b"original")
    recipe = "vcpkg_from_github(OUT_SOURCE_PATH SOURCE_PATH REPO a/b)\n"
    pins = {"vcpkg_commit": "pinned", "source_archive_sha256": "original-archive", "packages": {"pango": pin(tool, recipe)}}
    repo = tmp_path / "trusted-repo"
    (repo / "docs/dependencies").mkdir(parents=True)
    (repo / tool.PIN_FILE).write_text(json.dumps(pins))
    evidence = kit / "evidence"
    evidence.mkdir()
    inv = {"vcpkg_commit": "pinned", "source_archive": {"sha256": "original-archive"},
           "source_packages": {"pango": tool.tree_record(root.parent)}}
    (evidence / "pdf-runtime-win64-source-inventory.json").write_text(json.dumps(inv))
    with zipfile.ZipFile(kit / "corresponding-source.zip", "w") as z:
        z.writestr("vcpkg/ports/pango/portfile.cmake", recipe)
        z.writestr("vcpkg/ports/pango/vcpkg.json", '{"name":"pango"}')
        z.writestr("vcpkg/LICENSE.txt", "upstream license retained")
    seen = []
    def verify(path, digest):
        seen.append((path, digest))
        return {"kit_manifest_sha256": digest}
    monkeypatch.setattr(tool, "ROOT", repo)
    monkeypatch.setattr(tool, "own_kit_tool", lambda: SimpleNamespace(verify=verify, relative=lambda p: p))
    return kit, sources, tmp_path / "overlay", root, seen


def test_full_preparation_retains_original_recipes_and_separates_reference_provenance(tool, synthetic):
    kit, sources, dest, root, seen = synthetic
    before = (root / "test.c").read_bytes()
    result = tool.prepare(kit, sources, dest, "external-digest")
    assert seen == [(kit, "external-digest")]
    assert result["changed_packages"] == []
    assert result["distribution_status"] == tool.BLOCKED
    assert result["offline_sdk"] is False
    assert (root / "test.c").read_bytes() == before
    assert "vcpkg_from_github(" in (dest / "pango/upstream-portfile.cmake").read_text()
    assert "vcpkg_from_github(" not in (dest / "pango/local-portfile.cmake").read_text()
    assert (dest / "UPSTREAM-VCPKG-LICENSE.txt").read_text() == "upstream license retained"
    ref = json.loads((dest / "local-source-reference.json").read_text())
    assert ref["source_archive"] is None
    assert ref["original_source_archive"]["sha256"] == "original-archive"
    assert ref["new_corresponding_source_archive_prepared"] is False
    tool.check_inputs(result)
    with pytest.raises(FileExistsError):
        tool.prepare(kit, sources, dest, "external-digest")


def test_modified_preferred_source_requires_explicit_permission(tool, synthetic):
    kit, sources, dest, root, _ = synthetic
    (root / "test.c").write_bytes(b"explicit LGPL modification")
    with pytest.raises(ValueError, match="explicit --allow-modified"):
        tool.prepare(kit, sources, dest, "external-digest")
    assert not dest.exists()
    result = tool.prepare(kit, sources, dest, "external-digest", allow_modified=True)
    assert result["changed_packages"] == ["pango"]
    assert result["packages"]["pango"]["original_tree_sha256"] != result["packages"]["pango"]["patched_source_tree_sha256"]


def test_unsupported_multiple_source_roots_rejected_even_with_edits_allowed(tool, synthetic):
    kit, sources, dest, _, _ = synthetic
    (sources / "sources/pango/second.clean").mkdir()
    with pytest.raises(ValueError, match="root layout"):
        tool.prepare(kit, sources, dest, "external-digest", allow_modified=True)
    assert not dest.exists()


def test_port_pins_cover_all_original_packages_and_baseline():
    pins = json.loads((ROOT / "docs/dependencies/pdf-local-source-port-pins.json").read_text())
    inv = json.loads((ROOT / "docs/dependencies/pdf-runtime-win64-source-inventory.json").read_text())
    assert pins["vcpkg_commit"] == inv["vcpkg_commit"]
    assert pins["source_archive_sha256"] == inv["source_archive"]["sha256"]
    assert set(pins["packages"]) == set(inv["source_packages"])
    assert len(pins["packages"]) == 20
    assert pins["packages"]["pthread"]["roots"] == []
    assert all(len(p["roots"]) == 1 for n, p in pins["packages"].items() if n != "pthread")
