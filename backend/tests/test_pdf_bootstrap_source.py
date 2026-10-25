"""Phase 1 SOURCE contracts: every native byte here is FAKE, never build proof."""

import copy
import hashlib
import importlib.util
import json
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

import pytest

from app import private_pdf_bootstrap as boot

from .test_pdf_bootstrap_activation import simulated as simulated
from .test_pdf_bootstrap_preparation import payload as payload
from .test_pdf_bootstrap_preparation import put, stamp

ROOT = Path(__file__).resolve().parents[2]


def script():
    spec = importlib.util.spec_from_file_location(
        "phase1_source_bind", ROOT / "scripts/pdf_bootstrap_sdk_bind.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def source_payload(payload):
    root = payload.payload_root
    old = json.loads(
        (ROOT / "docs/dependencies/pdf-app-owned-source-http-evidence.json").read_text()
    )
    audit = copy.deepcopy(old["native_audit"])
    inventory = copy.deepcopy(old["cases"]["first-process"]["inventory"])
    for file in (root / "native/pdf/bin").iterdir():
        file.unlink()
    for name, item in audit["dlls"].items():
        data = b"FAKE NATIVE FILE NOT A SOURCE BUILD " + name.encode()
        (root / "native/pdf/bin" / name).write_bytes(data)
        item["sha256"] = hashlib.sha256(data).hexdigest()
        inventory["dlls"][name]["sha256"] = item["sha256"]
    put(root / "native/pdf/source-audit.json", audit)
    digest = hashlib.sha256((root / "native/pdf/source-audit.json").read_bytes()).hexdigest()
    inventory["native_audit_sha256"] = digest
    put(root / "native/pdf/runtime-inventory.json", inventory)
    return replace(stamp(root, payload.state_root), source_audit_sha256=digest)


def test_synthetic_source_plan_is_read_only_distinct_21_dll_preload(source_payload):
    result = boot.verify_private_plan(source_payload)
    assert len(result.dlls) == 21 and result.preload.name == "ffi-8.dll"
    assert result.scope == "PRIVATE_SOURCE_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION"
    assert not source_payload.state_root.exists()


@pytest.mark.parametrize(
    "kind",
    [
        "missing-digest",
        "wrong-digest",
        "audit-drift",
        "sdk-ffi",
        "notice",
        "archive",
        "source-file",
        "tree",
        "owner",
        "dll-hash",
        "count",
        "cache",
        "version",
    ],
)
def test_synthetic_source_mismatches_never_fall_back(source_payload, kind):
    plan = source_payload
    root = plan.payload_root
    afile, ifile = root / "native/pdf/source-audit.json", root / "native/pdf/runtime-inventory.json"
    audit, inv = json.loads(afile.read_text()), json.loads(ifile.read_text())
    if kind == "missing-digest":
        plan = replace(plan, source_audit_sha256=None)
    elif kind == "wrong-digest":
        plan = replace(plan, source_audit_sha256="0" * 64)
    elif kind == "audit-drift":
        afile.write_bytes(b"changed")
    else:
        if kind == "sdk-ffi":
            inv["preload_dlls"] = ["libffi-8.dll"]
        elif kind == "notice":
            audit["inline_change_date_notice_present_in_compiled_source"] = False
        elif kind == "archive":
            audit["noticed_source_archive_sha256"] = "0" * 64
        elif kind == "source-file":
            audit["noticed_source_file_sha256"] = "0" * 64
        elif kind == "tree":
            inv["source_packages"]["pango"]["patched_source_tree_sha256"] = "0" * 64
        elif kind == "owner":
            inv["dlls"]["ffi-8.dll"]["source_package"] = "pango"
        elif kind == "dll-hash":
            inv["dlls"]["ffi-8.dll"]["sha256"] = "0" * 64
        elif kind == "count":
            audit["dll_count"] = 27
        elif kind == "cache":
            inv["binary_cache"] = "ENABLED"
        elif kind == "version":
            audit["actual_pango_version_string"] = "1.58.2"
        put(afile, audit)
        digest = hashlib.sha256(afile.read_bytes()).hexdigest()
        inv["native_audit_sha256"] = digest
        put(ifile, inv)
        plan = replace(stamp(root, plan.state_root), source_audit_sha256=digest)
    with pytest.raises((ValueError, json.JSONDecodeError)):
        boot.verify_private_plan(plan)


def test_source_and_sdk_activation_are_explicit_not_inferred(source_payload, monkeypatch):
    calls = []

    @contextmanager
    def fake_activate(plan):
        calls.append(plan)
        yield "FAKE-NOT-NATIVE"

    monkeypatch.setattr(boot, "_activate_private", fake_activate)
    with (
        pytest.raises(ValueError, match="explicit activate_private_source"),
        boot.activate_private_sdk(source_payload),
    ):
        pass
    with (
        pytest.raises(ValueError, match="Independent source audit"),
        boot.activate_private_source(replace(source_payload, source_audit_sha256=None)),
    ):
        pass
    assert not calls
    with boot.activate_private_source(source_payload) as result:
        assert result == "FAKE-NOT-NATIVE"
    assert calls == [source_payload]


@pytest.fixture()
def source_binding(tmp_path):
    # Old app-owned source witness adapted solely as synthetic schema, not new proof.
    old = json.loads(
        (ROOT / "docs/dependencies/pdf-app-owned-source-http-evidence.json").read_text()
    )
    audit = tmp_path / "synthetic-audit.json"
    put(audit, old["native_audit"])
    digest = hashlib.sha256(audit.read_bytes()).hexdigest()
    reports = tmp_path / "reports"
    for name, case in old["cases"].items():
        p = case["launcher"]
        p.update(
            role="PRIVATE_APP_BOOTSTRAP_SOURCE_HTTP_NOT_INSTALLED",
            target_mode="PRIVATE_APP_BOOTSTRAP_HTTP",
            source_audit_sha256=digest,
            preflight_and_activation_module="app/private_pdf_bootstrap.py",
            activation_scope_restored=True,
            bootstrap_temp_cleaned=True,
        )
        p["activation"] = {
            "role": "APP_OWNED_PRIVATE_SOURCE_ACTIVATION_NOT_INSTALLED",
            "pid": p["pid"],
            "windows_acp": 65001,
            "manifest_sha256": p["payload_manifest_sha256"],
            "inventory_sha256": p["inventory_sha256"],
            "libffi": p["libffi"],
            "dll_count": 21,
            "payload_files": 1234,
            "bootstrap_temp": f"FAKE/{name}",
            "source_audit_sha256": digest,
        }
        case["http_pdf"]["worker"]["source_audit_sha256"] = digest
        case["inventory"]["native_audit_sha256"] = digest
        folder = reports / name
        for filename, value in [
            ("launcher-proof.json", p),
            ("http-bundled-proof.json", case["http_pdf"]),
            ("runtime-inventory.json", case["inventory"]),
        ]:
            put(folder / filename, value)
    negatives = old["negative_controls"]
    for key in ("unmanifested-code", "wrong-source-audit-digest"):
        negatives[key] = {"rejected": True, "exit_code": 1}
    put(reports / "negative-controls.json", negatives)
    return reports, audit


def test_synthetic_source_bootstrap_binding_and_annotation_volume(source_binding):
    import base64
    import zlib

    x = script().bind(*source_binding)
    assert x["role"] == "APP_OWNED_SOURCE_BOOTSTRAP_AND_HTTP_NOT_DISTRIBUTION"
    assert x["source21_activation_proven"] and not x["stock_sdk_used_in_source_job"]
    assert not x["installed_user_acceptance"] and not x["release_authorized"]
    assert len(x["native_audit"]["preferred_source_trees"]) == 20
    assert len(base64.b64encode(zlib.compress(json.dumps(x).encode(), 9))) <= 32 * 3000


@pytest.mark.parametrize(
    "fault", ["sdk-role", "activation-digest", "worker-digest", "negative", "preload"]
)
def test_source_binding_rejects_mixed_roles_and_audits(source_binding, fault):
    reports, audit = source_binding
    path = reports / "first-process/launcher-proof.json"
    p = json.loads(path.read_text())
    if fault == "sdk-role":
        p["role"] = "PRIVATE_APP_BOOTSTRAP_SDK_HTTP_NOT_INSTALLED"
    elif fault == "activation-digest":
        p["activation"]["source_audit_sha256"] = "0" * 64
    elif fault == "worker-digest":
        path = reports / "first-process/http-bundled-proof.json"
        p = json.loads(path.read_text())
        p["worker"]["source_audit_sha256"] = "0" * 64
    elif fault == "negative":
        path = reports / "negative-controls.json"
        p = json.loads(path.read_text())
        p.pop("wrong-source-audit-digest")
    else:
        path = reports / "first-process/runtime-inventory.json"
        p = json.loads(path.read_text())
        p["preload_dlls"] = ["libffi-8.dll"]
    put(path, p)
    with pytest.raises(ValueError):
        script().bind(reports, audit)


def test_phase_workflow_builds_cold_before_activation_and_reverifies_after():
    import yaml

    workflow = yaml.safe_load((ROOT / ".github/workflows/pdf-bootstrap-source.yml").read_text())
    jobs = workflow["jobs"]
    assert jobs["source-http-consumer"]["needs"] == "stock-http-preflight"
    names = [s.get("name", "") for s in jobs["source-http-consumer"]["steps"]]
    build = next(i for i, n in enumerate(names) if n.startswith("Compile all target"))
    activate = names.index(
        "Phase 1 app-owned source preflight and activation with distinct real HTTP processes"
    )
    assert (
        build
        < activate
        < names.index("Reverify noticed source envelope after app-owned bootstrap and HTTP")
    )


def test_simulated_source_activation_uses_source_ffi_and_audit_not_sdk(simulated, monkeypatch):
    import sys
    from types import SimpleNamespace

    plan, calls, _, _ = simulated
    plan = replace(plan, source_audit_sha256="d" * 64)
    verified = boot.VerifiedPrivatePlan(
        plan,
        (("ffi-8.dll", "c" * 64),),
        plan.payload_root / "native/pdf/bin/ffi-8.dll",
        plan.state_root / "cache",
        55,
    )
    monkeypatch.setattr(boot, "prepare_private_plan", lambda p: calls.append("prepare") or verified)
    monkeypatch.setattr(boot, "verify_private_plan", lambda p: calls.append("reverify") or verified)

    def load(path, flags):
        assert path == str(verified.preload) and flags == 0x1000
        calls.append("source-pin")
        return object()

    monkeypatch.setitem(
        sys.modules, "cffi", SimpleNamespace(FFI=lambda: SimpleNamespace(dlopen=load))
    )
    monkeypatch.setattr("ctypes.CDLL", lambda *_: object())
    with boot.activate_private_source(plan) as active:
        assert active.role == "APP_OWNED_PRIVATE_SOURCE_ACTIVATION_NOT_INSTALLED"
        assert active.source_audit_sha256 == "d" * 64
        assert Path(active.libffi).name == "ffi-8.dll"
        assert calls[-1] == "source-pin"
    assert calls[-1] == "close" and not plan.state_root.exists()


@pytest.mark.parametrize("fault", [None, "foreign-dependency", "unmapped", "load-error"])
def test_source_maps_full_closure_before_app_even_without_pdf(simulated, monkeypatch, fault):
    """FAKE loader lifecycle only: no Windows DLLs or native acceptance here."""
    import ctypes
    import sys
    import weakref
    from types import SimpleNamespace

    from app import desktop_entry

    from .test_pdf_bootstrap_activation import Fn, process_state

    plan, calls, kernel, _ = simulated
    plan = replace(plan, source_audit_sha256="d" * 64)
    names = ["ffi-8.dll", "pango-1.0-0.dll"] + [f"fake-lazy-{i}.dll" for i in range(19)]
    verified = boot.VerifiedPrivatePlan(
        plan, tuple((n, "c" * 64) for n in names),
        plan.payload_root / "native/pdf/bin/ffi-8.dll", plan.state_root / "cache", 55,
    )
    monkeypatch.setattr(boot, "prepare_private_plan", lambda _: verified)
    monkeypatch.setattr(boot, "verify_private_plan", lambda _: verified)
    monkeypatch.setitem(
        sys.modules, "cffi",
        SimpleNamespace(FFI=lambda: SimpleNamespace(dlopen=lambda *a, **k: object())),
    )
    mapped = {"ffi-8.dll"}
    handles, loads = [], []
    before = process_state()
    kernel.GetModuleHandleW.fn = lambda name: name if name in mapped else None
    original_filename = kernel.GetModuleFileNameW.fn

    def filename(name, buffer, length):
        if fault == "foreign-dependency" and name == names[-1]:
            buffer.value = str(plan.payload_root / "FOREIGN.dll")
            return len(buffer.value)
        return original_filename(name, buffer, length)

    kernel.GetModuleFileNameW.fn = filename

    class FakeHandle:
        pango_version_string = Fn(lambda: b"1.58.0-vira-local-source")

    def load(absolute):
        path = Path(absolute)
        assert path.parent == plan.payload_root / "native/pdf/bin"
        assert path.name in names
        if fault == "load-error" and path.name == names[-1]:
            raise OSError("Synthetic native load failure")
        loads.append(path.name)
        if not (fault == "unmapped" and path.name == names[-1]):
            mapped.add(path.name)
        handle = FakeHandle()
        handles.append(weakref.ref(handle))
        return handle

    monkeypatch.setattr(ctypes, "CDLL", load)
    inventory = plan.payload_root / "native/pdf/runtime-inventory.json"
    inventory.parent.mkdir(parents=True)
    inventory.write_text(json.dumps({"dlls": dict.fromkeys(names)}))
    # Reproduce the pre-fix shutdown failure in a process that never rendered:
    # the original FFI-only activation leaves the other modules unmapped.
    with pytest.raises(RuntimeError, match="Audited desktop native module absent"):
        desktop_entry.native_state(plan.payload_root)
    if fault:
        with pytest.raises((ValueError, RuntimeError, OSError)), boot.activate_private_source(plan):
            pytest.fail("Bad source closure must not enter the application body")
    else:
        with boot.activate_private_source(plan):
            # No renderer/factory/PDF has run; all 21 handles are already pinned.
            assert loads == names and len(mapped) == 21
            assert all(ref() is not None for ref in handles)
            assert len(desktop_entry.native_state(plan.payload_root)["loaded_dlls"]) == 21
        assert all(ref() is None for ref in handles)
    assert process_state() == before
    assert not plan.state_root.exists() and calls[-1] == "close"
