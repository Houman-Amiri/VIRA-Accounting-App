"""Real file/Ed25519/CLI checks; NOT Windows packaging or release clearance."""
from __future__ import annotations

import hashlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/finalize_release_assets.py"))


def pem(key):
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption()).decode()


@pytest.fixture
def assets(tmp_path, monkeypatch):
    monkeypatch.delenv("GITHUB_REF", raising=False)
    out = tmp_path / "release"
    out.mkdir()
    (out / "latest.json").write_bytes(b'{"schema_version":1,"version":"1.0.11"}\n')
    (out / "VIRA-Setup-1.0.11.exe").write_bytes(b"OPAQUE NOT AN EXECUTABLE")
    (out / "delta.zip").write_bytes(b"OPAQUE NOT AN UPDATE")
    (out / "release-notes-fa.md").write_text("یادداشت آزمایشی، نه انتشار", encoding="utf-8")
    (out / "app").mkdir()
    (out / "app/ignored-assembly-file").write_bytes(b"Not a flat asset")
    return out


def checked_sums(out):
    lines = (out / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
    entries = dict(line.split("  ", 1)[::-1] for line in lines)
    expected = {p.name for p in out.iterdir() if p.is_file() and p.name != "SHA256SUMS.txt"}
    assert set(entries) == expected
    assert len(entries) == len(lines)
    for name, digest in entries.items():
        assert digest == hashlib.sha256((out / name).read_bytes()).hexdigest()
    return entries


def test_finalizer_signs_raw_final_bytes_then_includes_signature_in_all_checksums(assets):
    key = Ed25519PrivateKey.generate()
    raw = (assets / "latest.json").read_bytes()
    result = MODULE["finalize"](assets, pem(key), require_signature=True)
    assert result == dict(signed=True, checksummed_assets=5, unsigned_approval="")
    key.public_key().verify((assets / "latest.json.sig").read_bytes(), raw)
    assert "latest.json.sig" in checked_sums(assets)
    before = {p.name: p.read_bytes() for p in assets.iterdir() if p.is_file()}
    MODULE["finalize"](assets, pem(key), require_signature=True)
    assert before == {p.name: p.read_bytes() for p in assets.iterdir() if p.is_file()}
    assert all(b"PRIVATE KEY" not in data for data in before.values())
    assert not list(assets.glob("*.tmp-*"))


def test_finalizer_can_sign_changed_metadata_without_stale_checksum_or_signature(assets):
    key = Ed25519PrivateKey.generate()
    MODULE["finalize"](assets, pem(key))
    old_signature = (assets / "latest.json.sig").read_bytes()
    raw = b'{"schema_version":1,"version":"1.0.12"}'
    (assets / "latest.json").write_bytes(raw)
    MODULE["finalize"](assets, pem(key))
    assert old_signature != (assets / "latest.json.sig").read_bytes()
    key.public_key().verify((assets / "latest.json.sig").read_bytes(), raw)
    checked_sums(assets)


@pytest.mark.parametrize("key", [None, "", "  ", "INVALID PRIVATE KEY"])
def test_tagged_release_never_falls_back_to_unsigned_assets(assets, monkeypatch, key):
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v1.0.11")
    before = {p.name:p.read_bytes() for p in assets.iterdir() if p.is_file()}
    with pytest.raises(ValueError):
        MODULE["finalize"](assets, key)
    assert before == {p.name:p.read_bytes() for p in assets.iterdir() if p.is_file()}


def test_debug_unsigned_assets_are_explicit_and_cannot_adopt_a_stale_signature(assets):
    result = MODULE["finalize"](assets, None)
    assert result == dict(signed=False, checksummed_assets=4, unsigned_approval="")
    checked_sums(assets)
    (assets / "latest.json.sig").write_bytes(b"UNVERIFIED OLD SIGNATURE")
    before = (assets / "SHA256SUMS.txt").read_bytes()
    with pytest.raises(ValueError, match="cannot be adopted"):
        MODULE["finalize"](assets, None)
    assert (assets / "SHA256SUMS.txt").read_bytes() == before


def test_finalizer_refuses_wrong_key_algorithm(assets):
    key = generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(ValueError, match="Ed25519"):
        MODULE["finalize"](assets, pem(key), require_signature=True)
    assert not (assets / "SHA256SUMS.txt").exists()
    assert not (assets / "latest.json.sig").exists()


@pytest.mark.parametrize("fault", ["root-link", "asset-link", "signature-link", "checksum-link", "private-key", "key-name", "unfinished", "line-break"])
def test_finalizer_rejects_foreign_paths_secrets_and_unfinished_assets(assets, tmp_path, fault):
    outside = tmp_path / "outside"
    outside.write_bytes(b"FOREIGN MUST NOT CHANGE")
    supplied = assets
    if fault == "root-link":
        supplied = tmp_path / "alias"
        supplied.symlink_to(assets, target_is_directory=True)
    elif fault in {"asset-link", "signature-link", "checksum-link"}:
        name = {"asset-link":"foreign.bin", "signature-link":"latest.json.sig", "checksum-link":"SHA256SUMS.txt"}[fault]
        (assets / name).symlink_to(outside)
    elif fault == "private-key":
        (assets / "mistaken-public.pem").write_text(pem(Ed25519PrivateKey.generate()))
    elif fault == "key-name":
        (assets / "update.key").write_bytes(b"MUST NOT SHIP")
    elif fault == "unfinished":
        (assets / "latest.json.tmp-abc").write_bytes(b"UNFINISHED")
    elif fault == "line-break":
        if os.name == "nt":
            with pytest.raises(OSError):
                (assets / "bad\nfilename").write_bytes(b"UNSAFE NAME")
            return  # Filesystem rejection, not a skipped validation check.
        (assets / "bad\nfilename").write_bytes(b"UNSAFE NAME")
    with pytest.raises(ValueError):
        MODULE["finalize"](supplied, pem(Ed25519PrivateKey.generate()))
    assert outside.read_bytes() == b"FOREIGN MUST NOT CHANGE"
    assert not (assets / "latest.json.sig").exists() or (assets / "latest.json.sig").is_symlink()


def test_real_cli_hides_bad_key_and_returns_failure_without_partial_signing(assets):
    env = dict(os.environ, VIRA_UPDATE_SIGNING_KEY="SENSITIVE INVALID KEY MUST NOT APPEAR", GITHUB_REF="refs/tags/v1.0.11")
    child = subprocess.run([sys.executable, str(ROOT / "scripts/finalize_release_assets.py"), str(assets)],
                           env=env, capture_output=True, text=True, timeout=15)
    assert child.returncode == 1
    assert "SENSITIVE" not in child.stdout + child.stderr and "Traceback" not in child.stderr
    assert not (assets / "latest.json.sig").exists() and not (assets / "SHA256SUMS.txt").exists()


def test_real_cli_produces_verifiable_signature_without_writing_a_key(assets):
    key = Ed25519PrivateKey.generate()
    env = dict(os.environ, VIRA_UPDATE_SIGNING_KEY=pem(key), GITHUB_REF="refs/tags/v1.0.11")
    child = subprocess.run([sys.executable, str(ROOT / "scripts/finalize_release_assets.py"), str(assets)],
                           env=env, capture_output=True, text=True, timeout=15)
    assert child.returncode == 0, child.stderr
    key.public_key().verify((assets / "latest.json.sig").read_bytes(), (assets / "latest.json").read_bytes())
    checked_sums(assets)
    assert pem(key) not in child.stdout + child.stderr
    assert not (assets / "update.key").exists()


def test_actual_release_workflow_finalizes_after_smoke_and_before_upload_or_publish():
    text = (ROOT / ".github/workflows/release.yml").read_text()
    assert text.index("Refuse unsigned tagged publication") < text.index("Build SPA + sync backend deps")
    final = text.index("Final signature and complete checksums")
    assert text.index("Windows install/upgrade/rollback smoke test") < final
    assert final < text.index("Upload workflow artifact") < text.index("Publish GitHub Release")
    delta = (ROOT / "scripts/build_deltas.ps1").read_text()
    assert delta.index("latest.json updated") < delta.index("scripts/finalize_release_assets.py")
    assert "Set-Content -Path $keyPath" not in delta
    assert 'throw "release asset signing/checksum finalization failed"' in delta


def test_dated_owner_authorization_allows_one_unsigned_tagged_publication(assets, monkeypatch):
    """The secret cannot be created by an App token; the owner authorized this."""
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v1.0.11")
    monkeypatch.setenv("VIRA_UNSIGNED_PUBLICATION_APPROVAL", "owner-authorized-2026-10-31")
    result = MODULE["finalize"](assets, None)
    assert result == dict(signed=False, checksummed_assets=4, unsigned_approval="owner-authorized-2026-10-31")
    assert not (assets / "latest.json.sig").exists()
    assert "latest.json" in checked_sums(assets)


@pytest.mark.parametrize(
    "approval",
    ["", "yes", "owner-authorized", "owner-authorized-2026-10", "owned-authorized-2026-10-28",
     "owner-authorized-2026-10-31-extra", " owner-authorized-2026-10-31 ", "true", "1"],
)
def test_a_hand_typed_or_partial_authorization_never_publishes_unsigned_labels(assets, monkeypatch, approval):
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v1.0.11")
    monkeypatch.setenv("VIRA_UNSIGNED_PUBLICATION_APPROVAL", approval)
    before = {p.name: p.read_bytes() for p in assets.iterdir() if p.is_file()}
    with pytest.raises(ValueError, match="no unsigned fallback"):
        MODULE["finalize"](assets, None)
    assert before == {p.name: p.read_bytes() for p in assets.iterdir() if p.is_file()}


def test_unsigned_publication_is_announced_loudly_and_never_leaks_a_key(assets, monkeypatch):
    monkeypatch.setenv("GITHUB_REF", "refs/tags/v1.0.11")
    monkeypatch.setenv("VIRA_UNSIGNED_PUBLICATION_APPROVAL", "owner-authorized-2026-10-31")
    child = subprocess.run(
        [sys.executable, str(ROOT / "scripts/finalize_release_assets.py"), str(assets)],
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT,
        env={k: v for k, v in os.environ.items() if k != "VIRA_UPDATE_SIGNING_KEY"},
    )
    assert child.returncode == 0, child.stderr
    assert "::warning title=unsigned-release::" in child.stdout
    assert "refs/tags" not in child.stdout
    assert "PRIVATE KEY" not in child.stdout + child.stderr


def test_the_workflow_carries_exactly_this_dated_authorization_and_keeps_failing_closed():
    text = (ROOT / ".github/workflows/release.yml").read_text()
    assert 'VIRA_UNSIGNED_PUBLICATION_APPROVAL: "owner-authorized-2026-10-31"' in text
    guard = text[text.index("Refuse unsigned tagged publication"):]
    guard = guard[:guard.index("- uses:")]
    assert 'throw "Tagged publication requires the configured Ed25519 signing key; no unsigned fallback"' in guard
    assert "::warning title=unsigned-publication::" in guard
    token = '"owner-authorized-2026-10-31"'
    assert text.count(token) == 2, "the dated token appears once as env and once as the guard comparison"
    assert "-ne " + token in guard
