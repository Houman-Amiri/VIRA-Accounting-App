"""Offline guard tests are not native Windows/launcher integration proof."""
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("private_launcher", ROOT / "scripts/pdf_private_launcher.py")
launcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launcher)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def stamp(root):
    files = [{"path": p.relative_to(root).as_posix(), "size": p.stat().st_size, "sha256": digest(p)}
             for p in root.rglob("*") if p.is_file() and p.name != "install_manifest.json"]
    put(root / "install_manifest.json", {"files": files})
    return digest(root / "install_manifest.json"), digest(root / "native/pdf/runtime-inventory.json")


@pytest.fixture()
def payload(tmp_path):
    root = tmp_path / "برنامه & مسیر با فاصله"
    for relative in launcher.REQUIRED:
        file = root / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"Synthetic test fixture, never native proof")
    put(root / "version.json", {"version": "0.0.0-private-unicode-proof"})
    put(root / "private-utf8-process-manifest.json", {
        "private_only": True, "python_executable_is_unmodified_upstream_binary": False,
        "release_or_redistribution_approval": False,
        "executable_sha256_before": "0" * 64, "executable_sha256_after": digest(root / "python/python.exe"),
    })
    dlls = {}
    for name in ["libffi-8.dll", *[f"synthetic-{i}.dll" for i in range(26)]]:
        file = root / "native/pdf/bin" / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"not a real DLL")
        dlls[name] = {"sha256": digest(file)}
    put(root / "native/pdf/runtime-inventory.json", {
        "upstream": {"sha256": launcher.SDK_SHA256}, "dlls": dlls,
        "distribution_status": launcher.BLOCKED,
    })
    return root


def test_valid_private_payload_is_checked_without_native_import(payload):
    before = set(sys.modules)
    inventory = launcher.validate_payload(payload, *stamp(payload))
    assert len(inventory["dlls"]) == 27
    assert not (set(sys.modules) - before) & {"cffi", "ctypes", "weasyprint"}


@pytest.mark.parametrize("relative", ["../escape", "a/../escape", "/escape", "C:escape", "C:\\escape", "\\\\host\\share\\file", "a\\..\\escape", "a.dll:stream", "./a", "a//b", ""])
def test_member_rejects_both_os_path_escapes(tmp_path, relative):
    with pytest.raises(ValueError, match="Unsafe payload"):
        launcher.member(tmp_path, relative)


def test_member_rejects_symlink_escape(tmp_path):
    root = tmp_path / "app"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"outside")
    (root / "link").symlink_to(outside)
    with pytest.raises(ValueError, match="escaped"):
        launcher.member(root, "link")


@pytest.mark.parametrize("which", [0, 1])
def test_independent_digests_cannot_be_silently_recomputed(payload, which):
    hashes = list(stamp(payload))
    hashes[which] = "f" * 64
    with pytest.raises(ValueError, match="Independent digest"):
        launcher.validate_payload(payload, *hashes)


@pytest.mark.parametrize("file", ["python/python.exe", "scripts/pdf_unicode_probe.py", "site-packages/cffi/__init__.py", "native/pdf/bin/libffi-8.dll"])
def test_changed_payload_fails_before_native_import(payload, file):
    hashes = stamp(payload)
    (payload / file).write_bytes(b"changed")
    with pytest.raises(ValueError, match="Baseline file changed"):
        launcher.validate_payload(payload, *hashes)


def test_missing_required_baseline_entry_is_not_unchecked_code(payload):
    stamp(payload)
    file = payload / "install_manifest.json"
    value = json.loads(file.read_text())
    value["files"] = [e for e in value["files"] if e["path"] != "scripts/pdf_unicode_probe.py"]
    put(file, value)
    with pytest.raises(ValueError, match="Required bootstrap"):
        launcher.validate_payload(payload, digest(file), digest(payload / "native/pdf/runtime-inventory.json"))


def test_case_aliased_manifest_entry_is_rejected(payload):
    stamp(payload)
    file = payload / "install_manifest.json"
    value = json.loads(file.read_text())
    entry = dict(value["files"][0])
    entry["path"] = entry["path"].upper()
    value["files"].append(entry)
    put(file, value)
    with pytest.raises(ValueError, match="Duplicate payload"):
        launcher.validate_payload(payload, digest(file), digest(payload / "native/pdf/runtime-inventory.json"))


@pytest.mark.parametrize("fault", ["version", "origin", "sdk", "status", "preload", "dll-sha", "pe", "duplicate-json"])
def test_no_source_legal_or_preload_policy_fallback(payload, fault):
    file = payload / "native/pdf/runtime-inventory.json"
    inventory = json.loads(file.read_text())
    if fault == "version":
        put(payload / "version.json", {"version": "1.0.10"})
    elif fault == "origin":
        inventory["origin"] = "LOCAL_PINNED_VCPKG_SOURCE_BUILD"
    elif fault == "sdk":
        inventory["upstream"]["sha256"] = "0" * 64
    elif fault == "status":
        inventory["distribution_status"] = "APPROVED"
    elif fault == "preload":
        inventory["preload_dlls"] = ["foreign.dll"]
    elif fault == "dll-sha":
        inventory["dlls"]["libffi-8.dll"]["sha256"] = "0" * 64
    elif fault == "pe":
        put(payload / "private-utf8-process-manifest.json", {"private_only": False})
    put(file, inventory)
    if fault == "duplicate-json":
        file.write_text('{"dlls":{},"dlls":{}}')
    with pytest.raises(ValueError):
        launcher.validate_payload(payload, *stamp(payload))


@pytest.mark.parametrize("missing", ["isolated", "no_site", "dont_write_bytecode", "utf8_mode"])
def test_each_explicit_python_flag_is_required(monkeypatch, missing):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    flags = dict.fromkeys(["isolated", "no_site", "dont_write_bytecode", "utf8_mode"], 1)
    flags[missing] = 0
    with pytest.raises(RuntimeError, match="requires -I -S -B -X utf8"):
        launcher.startup_guards("win32", SimpleNamespace(**flags), {})


@pytest.mark.parametrize("name", ["ctypes", "cffi.api", "_cffi_backend", "weasyprint.text", "app.main", "uvicorn", "sitecustomize"])
def test_early_sensitive_import_fails_closed(monkeypatch, name):
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    flags = SimpleNamespace(isolated=1, no_site=1, dont_write_bytecode=1, utf8_mode=1)
    with pytest.raises(RuntimeError, match="Sensitive module"):
        launcher.startup_guards("win32", flags, {name: object()})


def test_entry_module_itself_is_stdlib_only_in_fresh_isolated_process():
    code = f'''import runpy,sys
runpy.run_path({str(ROOT / 'scripts/pdf_private_launcher.py')!r},run_name='module_import_test')
assert not any(n == p or n.startswith(p+'.') for n in sys.modules for p in ('app','cffi','ctypes','weasyprint','uvicorn'))
'''
    subprocess.run([sys.executable, "-I", "-S", "-B", "-X", "utf8", "-c", code], check=True)
