"""Phase3 version contract. ALL native/interpreter bytes are synthetic; no execution proof."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from app import desktop_entry as entry
from app import private_pdf_bootstrap as boot
from app.private_installed_source import anchor

from .test_pdf_bootstrap_preparation import digest, put, stamp
from .test_pdf_bootstrap_preparation import payload as payload
from .test_pdf_bootstrap_source import source_payload as source_payload


@pytest.fixture()
def installed(source_payload):
    root = source_payload.payload_root
    bridge = root / "app/private_installed_source.py"
    bridge.write_bytes((Path(__file__).parents[1] / "app/private_installed_source.py").read_bytes())
    put(root / "version.json", dict(version="99.30.0"))
    plan = replace(
        stamp(root, source_payload.state_root),
        source_audit_sha256=source_payload.source_audit_sha256,
    )
    pin = root.parent / "external-anchor.json"
    put(
        pin,
        dict(
            schema=2,
            role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
            version="99.30.0",
            manifest_sha256=plan.manifest_sha256,
            inventory_sha256=plan.inventory_sha256,
            source_audit_sha256=plan.source_audit_sha256,
            port=8787,
            no_browser=True,
        ),
    )
    return replace(plan, installed_anchor=pin, installed_anchor_sha256=digest(pin))


def test_installed_source_version_is_read_only_independently_bound(installed):
    assert len(boot.verify_private_plan(installed).dlls) == 21
    assert not installed.state_root.exists()
    with pytest.raises(ValueError, match="Private staged version"):
        boot.verify_private_plan(
            replace(installed, installed_anchor=None, installed_anchor_sha256=None)
        )


@pytest.mark.parametrize(
    "fault",
    [
        "hash",
        "version",
        "manifest",
        "inventory",
        "audit",
        "schema",
        "unknown",
        "boolean",
        "sdk",
        "half-path",
        "half-sha",
        "inside-root",
        "symlink",
    ],
)
def test_installed_contract_never_weakens_legacy_or_digest_guards(installed, fault):
    p = installed
    if fault == "hash":
        p = replace(p, installed_anchor_sha256="0" * 64)
    elif fault == "sdk":
        with pytest.raises(ValueError):
            replace(p, source_audit_sha256=None)
        return
    elif fault in {"half-path", "half-sha", "inside-root"}:
        kw = {
            "half-path": dict(installed_anchor=None),
            "half-sha": dict(installed_anchor_sha256=None),
            "inside-root": dict(installed_anchor=p.payload_root / "anchor.json"),
        }[fault]
        with pytest.raises(ValueError):
            replace(p, **kw)
        return
    elif fault == "symlink":
        target = p.installed_anchor.with_suffix(".moved")
        p.installed_anchor.rename(target)
        p.installed_anchor.symlink_to(target)
    else:
        value = json.loads(p.installed_anchor.read_bytes())
        key = {
            "version": "version",
            "manifest": "manifest_sha256",
            "inventory": "inventory_sha256",
            "audit": "source_audit_sha256",
            "schema": "schema",
            "unknown": "extra",
            "boolean": "version",
        }[fault]
        value[key] = {"version": "99.30.1", "schema": 1, "unknown": True, "boolean": True}.get(
            fault, "f" * 64
        )
        put(p.installed_anchor, value)
        p = replace(p, installed_anchor_sha256=digest(p.installed_anchor))
    with pytest.raises((ValueError, KeyError)):
        boot.verify_private_plan(p)
    assert not p.state_root.exists()


@pytest.mark.parametrize("version", ["1.0.10", "99.30.1", "0.0.0"])
def test_v2_schema_versions_are_exact_release_triplets(installed, version):
    value = json.loads(installed.installed_anchor.read_bytes())
    value["version"] = version
    assert anchor(value)["version"] == version


@pytest.mark.parametrize(
    "version", [True, 1, None, "01.0.0", "1.0", "1.0.0\n", "1.0.0+local", "1.0.0-private", "١.٠.٠"]
)
def test_v2_schema_rejects_ambiguous_versions(installed, version):
    value = json.loads(installed.installed_anchor.read_bytes())
    value["version"] = version
    with pytest.raises(ValueError):
        anchor(value)


def test_installed_request_binds_port_profile_policy_and_anchor_bytes(tmp_path, monkeypatch):
    profile = tmp_path / "private profile"
    monkeypatch.setenv("LOCALAPPDATA", str(profile))
    pin = profile / "VIRA/private-native-installed/anchor.json"
    value = dict(
        schema=2,
        role="PRIVATE_SOURCE_INSTALLED_ANCHOR",
        version="99.30.0",
        manifest_sha256="a" * 64,
        inventory_sha256="b" * 64,
        source_audit_sha256="c" * 64,
        port=8787,
        no_browser=True,
    )
    put(pin, value)
    request = dict(
        role="PRIVATE_INSTALLED_SOURCE_DESKTOP_REQUEST",
        **{
            k: value[k]
            for k in (
                "manifest_sha256",
                "inventory_sha256",
                "source_audit_sha256",
                "port",
                "no_browser",
            )
        },
        state_root=str(pin.parent / "state"),
        launch_id="d" * 32,
        installed_anchor=str(pin),
        installed_anchor_sha256=digest(pin),
    )
    file = tmp_path / "request.json"
    put(file, request)
    assert entry.request(tmp_path / "payload", file) == request
    for key, bad in [
        ("port", 8788),
        ("no_browser", False),
        ("installed_anchor_sha256", "0" * 64),
        ("state_root", str(profile / "other")),
        ("role", "PRIVATE_SOURCE_DESKTOP_REQUEST"),
        ("installed_anchor", str(tmp_path / "foreign")),
    ]:
        put(file, dict(request, **{key: bad}))
        with pytest.raises(ValueError):
            entry.request(tmp_path / "payload", file)


def test_v2_cli_delta_assembles_and_reverifies_full_synthetic_source_payload(
    installed, tmp_path, monkeypatch
):
    """Actual ZIP/BSDIFF/manifest code, but deliberately fake native/interpreter bytes."""
    import os
    import runpy
    import shutil
    import subprocess
    import sys

    root = installed.payload_root
    (root / "vira-updater.exe").write_bytes(b"OPAQUE HELPER NEVER EXECUTED")
    old_manifest = stamp(root, installed.state_root).manifest_sha256
    old = json.loads(installed.installed_anchor.read_bytes())
    old["manifest_sha256"] = old_manifest
    put(installed.installed_anchor, old)
    target = tmp_path / "target VIRA فارسی ! &"
    shutil.copytree(root, target)
    put(target / "version.json", dict(version="99.30.1"))
    # Receipt bytes are application metadata, allowed ONLY in the private channel.
    receipt = target / "private-utf8-process-manifest.json"
    receipt.write_bytes(receipt.read_bytes() + b"\n")
    dll = target / "native/pdf/bin/ffi-8.dll"
    dll.write_bytes(b"FAKE CHANGED DLL NOT NATIVE EXECUTION")
    audit_path = target / "native/pdf/source-audit.json"
    audit = json.loads(audit_path.read_bytes())
    audit["dlls"]["ffi-8.dll"]["sha256"] = digest(dll)
    put(audit_path, audit)
    inv_path = target / "native/pdf/runtime-inventory.json"
    inv = json.loads(inv_path.read_bytes())
    inv["dlls"]["ffi-8.dll"]["sha256"] = digest(dll)
    inv["native_audit_sha256"] = digest(audit_path)
    put(inv_path, inv)
    repo = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, str(repo / "scripts/build_manifest.py"), str(target)], capture_output=True
    )
    assert proc.returncode == 0, proc.stderr
    new = dict(
        old,
        version="99.30.1",
        manifest_sha256=digest(target / "install_manifest.json"),
        inventory_sha256=digest(inv_path),
        source_audit_sha256=digest(audit_path),
    )
    pin = tmp_path / "target-anchor.json"
    put(pin, new)
    args = [
        sys.executable,
        str(repo / "scripts/gen_delta.py"),
        "--base-manifest",
        str(root / "install_manifest.json"),
        "--base-dir",
        str(root),
        "--target-dir",
        str(target),
        "--base-version",
        "99.30.0",
        "--target-version",
        "99.30.1",
        "--out",
        str(tmp_path / "out"),
        "--private-source-anchor",
        str(pin),
        "--patch-threshold",
        "1",
    ]
    proc = subprocess.run(args, env=dict(os.environ, GITHUB_ACTIONS="true"), capture_output=True)
    assert proc.returncode == 0, proc.stderr
    packet = next((tmp_path / "out").glob("*.zip"))
    assembled = tmp_path / "assembled هدف فارسی"
    controller = runpy.run_path(str(repo / "scripts/private_source_update.py"))
    _, _, changed = controller["assemble"](root, packet, assembled, old, new, digest(packet))
    assert "native/pdf/bin/ffi-8.dll" in changed
    assert "private-utf8-process-manifest.json" in changed
    from app.services.update_staging import extract_delta

    extract_delta(packet, tmp_path / "private-stage", "99.30.0", "99.30.1", private_pin=old)
    with pytest.raises(ValueError):
        extract_delta(packet, tmp_path / "public-stage", "99.30.0", "99.30.1")
    plan = boot.PrivateBootstrapPlan(
        assembled,
        tmp_path / "fresh state فارسی",
        new["manifest_sha256"],
        new["inventory_sha256"],
        source_audit_sha256=new["source_audit_sha256"],
        installed_anchor=pin,
        installed_anchor_sha256=digest(pin),
    )
    assert len(boot.verify_private_plan(plan).dlls) == 21
