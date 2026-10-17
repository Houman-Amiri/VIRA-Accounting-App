"""Source receipt/closure guards; mocks are not Windows compilation evidence."""
from __future__ import annotations

import importlib
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture()
def tool(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "scripts"))
    return importlib.import_module("source_pdf_inventory")


@pytest.fixture()
def workspace(tmp_path):
    vcpkg, installed, profile = (tmp_path / name for name in ("vcpkg", "installed", "profile"))
    for directory in (vcpkg, installed, profile):
        directory.mkdir()
    (profile / "vcpkg.json").write_text(json.dumps({"builtin-baseline": "a" * 40}))
    (vcpkg / "LICENSE.txt").write_text("vcpkg license")
    return vcpkg, installed, profile


def package(tool, workspace, name, *, native=True, sources=True, copyright=True, spdx=True):
    vcpkg, installed, _ = workspace
    share = installed / tool.TRIPLET / "share" / name
    share.mkdir(parents=True)
    if copyright:
        (share / "copyright").write_text("Upstream license and notices")
    if spdx:
        (share / "vcpkg.spdx.json").write_text(json.dumps({"packages": [{"name": name, "licenseDeclared": "MIT"}]}))
    if sources:
        source = vcpkg / "buildtrees" / name / "src" / "patched-123.clean"
        source.mkdir(parents=True)
        (source / "main.c").write_text("/* preferred source */")
        (source / "LICENSE").write_text("Upstream license and notices")
    path = f"{tool.TRIPLET}/bin/{name}.dll" if native else f"{tool.TRIPLET}/share/{name}/copyright"
    info = installed / "vcpkg/info"
    info.mkdir(parents=True, exist_ok=True)
    (info / f"{name}_1.0_{tool.TRIPLET}.list").write_text(path + "\n")


@pytest.mark.parametrize("aliases", [("missing.dll",), ("one.dll", "two.dll")])
def test_rejects_missing_or_ambiguous_native_implementation(tool, aliases):
    with pytest.raises(ValueError, match="Exactly one"):
        tool.choose({"one.dll": b"", "two.dll": b""}, aliases)


def test_unique_native_implementation(tool):
    assert tool.choose({"two.dll": b""}, ("one.dll", "two.dll")) == "two.dll"


def test_missing_installed_receipts_fail_closed(tool, workspace):
    with pytest.raises(ValueError, match="No installed"):
        tool.package_records(workspace[1])


def test_receipt_ownership_is_case_insensitive_and_duplicate_rejected(tool, workspace):
    package(tool, workspace, "lib-a")
    installed = workspace[1]
    packages, owners = tool.package_records(installed)
    assert owners[f"{tool.TRIPLET}/bin/lib-a.dll"] == "lib-a"
    duplicate = installed / "vcpkg/info" / f"lib-b_1.0_{tool.TRIPLET}.list"
    duplicate.write_text(f"{tool.TRIPLET.upper()}/BIN/LIB-A.DLL\n")
    with pytest.raises(ValueError, match="Duplicate package owner"):
        tool.package_records(installed)
    assert set(packages) == {"lib-a"}


@pytest.mark.parametrize("missing", ["copyright", "spdx", "sources"])
def test_native_packages_need_sources_and_license_receipts(tool, workspace, tmp_path, missing):
    package(tool, workspace, "lib-a", **{missing: False})
    vcpkg, installed, profile = workspace
    packages, _ = tool.package_records(installed)
    with pytest.raises(ValueError, match="Missing copyright/SPDX|no captured source"):
        tool.capture_sources(vcpkg, installed, packages, tmp_path / "source.zip", profile)


def test_capture_includes_static_dependencies_and_full_patched_tree(tool, workspace, tmp_path):
    package(tool, workspace, "dynamic")
    package(tool, workspace, "static")
    vcpkg, installed, profile = workspace
    receipt = installed / "vcpkg/info" / f"static_1.0_{tool.TRIPLET}.list"
    receipt.write_text(f"{tool.TRIPLET}/lib/static.lib\n")
    source = vcpkg / "buildtrees/static/src/patched-123.clean"
    (source / "unusual.preferred-source").write_text("Do not filter source by extension")
    (vcpkg / "vcpkg.exe").write_bytes(b"BUILD TOOL MUST NOT BE COPIED")
    (vcpkg / "buildtrees/static/output.dll").write_bytes(b"OUTPUT MUST NOT BE COPIED")
    packages, _ = tool.package_records(installed)
    archive = tmp_path / "source.zip"
    evidence = tool.capture_sources(vcpkg, installed, packages, archive, profile)
    assert evidence["static"]["native_code"]
    assert evidence["static"]["patched_source_files"] == 3
    assert evidence["dynamic"]["source_status"] == "PATCHED_TREE_CAPTURED"
    with zipfile.ZipFile(archive) as bundle:
        assert "sources/static/patched-123.clean/unusual.preferred-source" in bundle.namelist()
        assert "installed-notices/static/copyright" in bundle.namelist()
        assert "vcpkg/LICENSE.txt" in bundle.namelist()
        assert not any(name.endswith(("vcpkg.exe", "output.dll")) for name in bundle.namelist())
    (source / "main.c").write_text("modified source")
    other = tool.capture_sources(vcpkg, installed, packages, tmp_path / "other.zip", profile)
    assert other["static"]["patched_source_tree_sha256"] != evidence["static"]["patched_source_tree_sha256"]


def test_recipe_only_config_package_not_misrepresented_as_compiled_source(tool, workspace, tmp_path):
    package(tool, workspace, "config", native=False, sources=False)
    vcpkg, installed, profile = workspace
    packages, _ = tool.package_records(installed)
    evidence = tool.capture_sources(vcpkg, installed, packages, tmp_path / "source.zip", profile)
    assert evidence["config"]["source_status"] == "RECIPE_ONLY_NO_NATIVE_CODE"


def test_capture_rejects_symlink_in_source(tool, tmp_path):
    source = tmp_path / "sources"
    source.mkdir()
    (source / "link").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="Escaping source symlink"):
        list(tool.tree_entries(source))


def test_profile_keeps_replaceable_libraries_and_immutable_baseline(tool):
    root = Path(__file__).resolve().parents[2]
    profile = root / "native/pdf-source"
    manifest = json.loads((profile / "vcpkg.json").read_text())
    assert len(bytes.fromhex(manifest["builtin-baseline"])) == 20
    triplet = (profile / "triplets/x64-vira-pdf.cmake").read_text()
    assert "set(VCPKG_LIBRARY_LINKAGE dynamic)" in triplet
    assert "set(VCPKG_BUILD_TYPE release)" in triplet
    script = (root / "scripts/source_pdf_build.ps1").read_text()
    assert '--binarysource=clear' in script
    assert '$env:VCPKG_BINARY_SOURCES = "clear"' in script
    assert 'git -C $vcpkg rev-parse HEAD' in script
    assert "--host-triplet x64-vira-pdf-host" in script
    host = (profile / "triplets/x64-vira-pdf-host.cmake").read_text()
    assert "set(VCPKG_CRT_LINKAGE dynamic)" in host
    assert "set(VCPKG_BUILD_TYPE release)" in host


def test_empty_alias_can_delegate_only_metadata_to_real_installed_dependency(tool, workspace, tmp_path):
    package(tool, workspace, "real")
    package(tool, workspace, "alias", native=False, sources=False, copyright=False)
    vcpkg, installed, profile = workspace
    port = vcpkg / "ports/alias"
    port.mkdir(parents=True)
    (port / "vcpkg.json").write_text(json.dumps({"dependencies": ["real"]}))
    (port / "portfile.cmake").write_text("set(VCPKG_POLICY_EMPTY_PACKAGE enabled)\n")
    receipt = installed / "vcpkg/info" / f"alias_1.0_{tool.TRIPLET}.list"
    receipt.write_text(f"{tool.TRIPLET}/share/alias/vcpkg.spdx.json\n")
    packages, _ = tool.package_records(installed)
    result = tool.capture_sources(vcpkg, installed, packages, tmp_path / "source.zip", profile)
    assert result["alias"]["source_status"] == "EMPTY_DEPENDENCY_ALIAS_NO_RUNTIME_FILES"
    assert result["alias"]["copyright_sha256"] is None
    assert result["alias"]["delegated_license_packages"] == ["real"]
    assert result["real"]["copyright_sha256"]
    # A fake alias cannot hide an installed library or other runtime content.
    receipt.write_text(receipt.read_text() + f"{tool.TRIPLET}/bin/hidden.dll\n")
    packages, _ = tool.package_records(installed)
    with pytest.raises(ValueError, match="Missing copyright/SPDX"):
        tool.capture_sources(vcpkg, installed, packages, tmp_path / "invalid.zip", profile)


def test_header_only_native_code_still_requires_preferred_source(tool, workspace, tmp_path):
    package(tool, workspace, "headers", native=False, sources=False)
    vcpkg, installed, profile = workspace
    (installed / "vcpkg/info" / f"headers_1.0_{tool.TRIPLET}.list").write_text(f"{tool.TRIPLET}/include/headers.hpp\n")
    packages, _ = tool.package_records(installed)
    with pytest.raises(ValueError, match="no captured source"):
        tool.capture_sources(vcpkg, installed, packages, tmp_path / "source.zip", profile)


def test_empty_spdx_document_not_accepted_as_license_evidence(tool, workspace, tmp_path):
    package(tool, workspace, "real")
    vcpkg, installed, profile = workspace
    (installed / tool.TRIPLET / "share/real/vcpkg.spdx.json").write_text("{}")
    packages, _ = tool.package_records(installed)
    with pytest.raises(ValueError, match="Missing SPDX package records"):
        tool.capture_sources(vcpkg, installed, packages, tmp_path / "source.zip", profile)


def test_safe_relative_links_preserved_without_dereferencing_dangling_fixture(tool, workspace, tmp_path):
    import stat

    package(tool, workspace, "linked")
    vcpkg, installed, profile = workspace
    source = vcpkg / "buildtrees/linked/src/patched-123.clean"
    (source / "README.md").symlink_to("main.c")
    (source / "dangling").symlink_to("not-created-test-fixture")
    (source / "cycle-a").symlink_to("cycle-b")
    (source / "cycle-b").symlink_to("cycle-a")
    packages, _ = tool.package_records(installed)
    archive = tmp_path / "sources.zip"
    result = tool.capture_sources(vcpkg, installed, packages, archive, profile)
    assert result["linked"]["patched_source_symlinks"]["patched-123.clean/README.md"] == "main.c"
    assert result["linked"]["copyright_text_utf8_lossless"]
    assert result["linked"]["copyright_text"] == "Upstream license and notices"
    with zipfile.ZipFile(archive) as bundle:
        name = "sources/linked/patched-123.clean/README.md"
        assert stat.S_ISLNK(bundle.getinfo(name).external_attr >> 16)
        assert bundle.read(name) == b"main.c"
        assert bundle.read("sources/linked/patched-123.clean/dangling") == b"not-created-test-fixture"
        assert "vira-build/scripts/source_pdf_build.ps1" in bundle.namelist()


def test_relative_escape_link_rejected_without_reading_target(tool, tmp_path):
    source = tmp_path / "src"
    source.mkdir()
    (source / "escape").symlink_to("../../missing-outside")
    with pytest.raises(ValueError, match="Escaping source symlink"):
        list(tool.tree_entries(source))


def test_source_tree_order_is_portable_case_sensitive_posix(tool, tmp_path):
    (tmp_path / "a.c").write_text("lower")
    (tmp_path / "Z.c").write_text("upper")
    assert [relative for _, relative in tool.tree_entries(tmp_path)] == ["Z.c", "a.c"]
