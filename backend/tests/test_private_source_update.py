"""Synthetic byte/transaction-preflight tests, NOT Windows/DLL/Inno execution."""

from __future__ import annotations

import copy
import hashlib
import json
import runpy
import zipfile
from pathlib import Path

import bsdiff4
import pytest

from app import private_installed_source as bridge
from app.services.update_engine import build_manifest, manifest_to_json, plan_delta

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/private_source_update.py"))


def raw(value):
    return json.dumps(value, indent=2, ensure_ascii=False).encode()


def fixture(tmp_path):
    base = tmp_path / "base"
    base.mkdir()
    before = {
        "version.json": raw({"version": "99.30.0", "spa_build": "old"}),
        "app/main.py": b"# synthetic, never executed\n",
        "native/pdf/bin/pango.dll": b"OPAQUE SYNTHETIC NOT A DLL\n" * 1000,
        "python/python.exe": b"OPAQUE SYNTHETIC NOT AN INTERPRETER\n" * 100,
        "static/deleted.txt": b"old deletion restored on rollback",
        "static/edit.txt": b"old",
    }
    after = dict(before)
    after["version.json"] = raw({"version": "99.30.1", "spa_build": "new"})
    after["native/pdf/bin/pango.dll"] += b"synthetic changed native-directory bytes"
    after["static/edit.txt"] = b"new"
    del after["static/deleted.txt"]
    after["static/added.txt"] = b"added"
    target_dir = tmp_path / "target-input"
    for directory, files in [(base, before), (target_dir, after)]:
        for name, data in files.items():
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    bm, tm = build_manifest(base), build_manifest(target_dir)
    old_raw, target_raw = raw(manifest_to_json(bm)), raw(manifest_to_json(tm))
    (base / "install_manifest.json").write_bytes(old_raw)
    plan, members = plan_delta("99.30.0", "99.30.1", bm, tm, patch_threshold=128)
    contents = {"install_manifest.json": target_raw, "version.json": after["version.json"]}
    hashes = {}
    for name, (kind, relative) in members.items():
        data = (
            bsdiff4.diff(before[relative], after[relative])
            if kind.value == "patch"
            else after[relative]
        )
        contents[name] = data
        hashes[name] = hashlib.sha256(data).hexdigest()
    doc = plan.to_json()
    doc["hashes"] = hashes
    contents["update.json"] = raw(doc)
    contents["delete.json"] = raw({"deleted": ["static/deleted.txt"]})
    return (
        base,
        before,
        after,
        contents,
        {"manifest_sha256": hashlib.sha256(old_raw).hexdigest()},
        {"manifest_sha256": hashlib.sha256(target_raw).hexdigest()},
    )


def packet(tmp_path, contents):
    path = tmp_path / "delta.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
    return path


def assemble(tmp_path, base, contents, old, target):
    archive = packet(tmp_path, contents)
    return MODULE["assemble"](
        base, archive, tmp_path / "assembled", old, target, MODULE["sha"](archive)
    )


def test_lossless_changed_parts_native_directory_patch_and_complete_target(tmp_path):
    base, before, after, contents, old, target = fixture(tmp_path)
    bm, tm, changed = assemble(tmp_path, base, contents, old, target)
    assert set(bm) == set(before) and set(tm) == set(after)
    assert "python/python.exe" not in changed
    assert "patches/native/pdf/bin/pango.dll.bsdiff" in contents
    assert not any("python.exe" in name for name in contents)
    assert all((tmp_path / "assembled" / name).read_bytes() == data for name, data in after.items())
    assert all((base / name).read_bytes() == data for name, data in before.items())


@pytest.mark.parametrize(
    "mutation",
    [
        "extra-member",
        "traversal",
        "case-collision",
        "missing-member",
        "member-hash",
        "missing-hash",
        "extra-op",
        "missing-op",
        "wrong-kind",
        "op-hash",
        "op-size",
        "wrong-base-version",
        "wrong-target-version",
        "target-manifest",
        "base-bytes",
        "base-extra",
        "patch-header",
        "patch-path",
        "duplicate-json",
        "opaque-data-target",
    ],
)
def test_preflight_tampering_never_changes_installed_baseline(tmp_path, mutation):
    base, before, _, contents, old, target = fixture(tmp_path)
    doc = json.loads(contents["update.json"])
    name = next(n for n in contents if n.startswith("files/"))
    if mutation == "extra-member":
        contents["unexpected.exe"] = b"never executed"
    elif mutation == "traversal":
        contents["files/app/../../data/vira.sqlite3"] = b"no"
    elif mutation == "case-collision":
        contents[name.upper()] = contents[name]
    elif mutation == "missing-member":
        del contents[name]
    elif mutation == "member-hash":
        contents[name] += b"corrupt"
    elif mutation == "missing-hash":
        del doc["hashes"][name]
    elif mutation == "extra-op":
        doc["operations"].append(copy.deepcopy(doc["operations"][0]))
    elif mutation == "missing-op":
        doc["operations"].pop()
    elif mutation == "wrong-kind":
        doc["operations"][0]["op"] = "exec"
    elif mutation == "op-hash":
        next(o for o in doc["operations"] if o["op"] != "delete")["sha256"] = "0" * 64
    elif mutation == "op-size":
        next(o for o in doc["operations"] if o["op"] != "delete")["size"] = -1
    elif mutation == "wrong-base-version":
        doc["base_version"] = "99.0.0"
    elif mutation == "wrong-target-version":
        doc["target_version"] = "99.0.0"
    elif mutation == "target-manifest":
        contents["install_manifest.json"] += b" "
    elif mutation == "base-bytes":
        (base / "app/main.py").write_bytes(b"preexisting corruption")
    elif mutation == "base-extra":
        (base / "unexpected.py").write_bytes(b"preexisting unmanifested")
    elif mutation == "patch-header":
        member = next(n for n in contents if n.startswith("patches/"))
        contents[member] = b"invalid"
        doc["hashes"][member] = hashlib.sha256(contents[member]).hexdigest()
    elif mutation == "patch-path":
        next(o for o in doc["operations"] if o["op"] == "patch")["patch"] = (
            "patches/app/../bad.bsdiff"
        )
    elif mutation == "opaque-data-target":
        doc["operations"][0]["path"] = "data/vira.sqlite3"
    if mutation == "duplicate-json":
        contents["update.json"] = b'{"operations":[],"operations":[]}'
    else:
        contents["update.json"] = raw(doc)
    baseline = {
        p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()
    }
    with pytest.raises((ValueError, KeyError)):
        assemble(tmp_path, base, contents, old, target)
    assert baseline == {
        p.relative_to(base).as_posix(): p.read_bytes() for p in base.rglob("*") if p.is_file()
    }


@pytest.mark.parametrize(
    "path",
    [
        "../app/x",
        "/app/x",
        "app/../x",
        "app/./x",
        "app//x",
        "app/x.",
        "app/x ",
        "app/NUL.txt",
        "app/COM1",
        "app/x:y",
        "app\\x",
        "data/vira.sqlite3",
        "native/other/x",
        "app/*",
        "app/x\x00",
    ],
)
def test_windows_path_aliases_and_business_paths_rejected(path):
    with pytest.raises(ValueError):
        MODULE["relative"](path)


def test_external_sha_and_symlinks_rejected_without_mutation(tmp_path):
    base, _, _, contents, old, target = fixture(tmp_path)
    archive = packet(tmp_path, contents)
    with pytest.raises(ValueError, match="External archive"):
        MODULE["assemble"](base, archive, tmp_path / "out", old, target, "0" * 64)
    source = base / "app/main.py"
    original = tmp_path / "original.py"
    source.rename(original)
    source.symlink_to(original)
    with pytest.raises(ValueError, match="reparse/symlink"):
        assemble(tmp_path, base, contents, old, target)


def test_manifest_case_alias_and_boolean_size_rejected(tmp_path):
    base, _, _, _, old, _ = fixture(tmp_path)
    doc = json.loads((base / "install_manifest.json").read_bytes())
    for change in ("case", "bool"):
        value = copy.deepcopy(doc)
        if change == "case":
            value["files"].append(dict(value["files"][0], path=value["files"][0]["path"].upper()))
        else:
            value["files"][0]["size"] = True
        data = raw(value)
        with pytest.raises(ValueError):
            MODULE["manifest"](data, hashlib.sha256(data).hexdigest())
    with pytest.raises(ValueError):
        MODULE["manifest"](raw(doc), "0" * 64)


@pytest.mark.parametrize(
    "old,new",
    [
        (b"", b""),
        (b"", b"new"),
        (b"old", b""),
        (bytes(range(256)) * 50, bytes(range(255, -1, -1)) * 48),
    ],
    ids=["empty", "insert", "delete", "binary-12kb"],
)
def test_bounded_stdlib_patch_matches_actual_bsdiff4(old, new):
    assert MODULE["patch"](old, bsdiff4.diff(old, new), len(new)) == new


@pytest.mark.parametrize(
    "key,value",
    [
        ("schema", True),
        ("role", "PUBLIC"),
        ("port", True),
        ("port", 0),
        ("no_browser", 1),
        ("manifest_sha256", "A" * 64),
        ("source_audit_sha256", None),
    ],
)
def test_installed_anchor_strict_schema(key, value):
    doc = dict(
        schema=1,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        manifest_sha256="a" * 64,
        inventory_sha256="b" * 64,
        source_audit_sha256="c" * 64,
        port=8787,
        no_browser=True,
    )
    assert bridge.anchor(doc) == doc
    doc[key] = value
    with pytest.raises(ValueError):
        bridge.anchor(doc)


def test_no_duplicate_anchor_or_public_profile(tmp_path, monkeypatch):
    path = tmp_path / "anchor.json"
    path.write_bytes(b'{"role":"a","role":"b"}')
    with pytest.raises(ValueError):
        bridge.read(path)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "outside"))
    monkeypatch.setenv("RUNNER_TEMP", str(tmp_path / "runner"))
    with pytest.raises(ValueError):
        bridge.location()


def test_patch_decompression_budget_and_invalid_header():
    with pytest.raises(ValueError):
        MODULE["patch"](b"", b"BSDIFF40" + b"\xff" * 24, 0)
    with pytest.raises(ValueError):
        MODULE["patch"](b"", b"not a patch", 0)


def test_imports_are_stdlib_only_and_no_native_or_installer_claim():
    for path in (
        ROOT / "scripts/private_source_update.py",
        ROOT / "backend/app/private_installed_source.py",
    ):
        import ast

        tree = ast.parse(path.read_text())
        assert not any(
            isinstance(n, ast.ImportFrom) and n.module and n.module.startswith(("app.", "scripts."))
            for n in ast.walk(tree)
        )
    assert "Synthetic" in __doc__
