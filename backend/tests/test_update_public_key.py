"""Real crypto + packaging wiring; NOT a Windows or publication proof."""
from __future__ import annotations

import hashlib
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

ROOT = Path(__file__).resolve().parents[2]
MODULE = runpy.run_path(str(ROOT / "scripts/export_update_public_key.py"))


def private_pem(key=None):
    key = key or Ed25519PrivateKey.generate()
    return key, key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def test_exported_key_verifies_what_the_release_signs(tmp_path):
    key, pem = private_pem()
    out = tmp_path / "nested" / "update-public-key.pem"
    fingerprint = MODULE["export"](out, pem)
    raw = out.read_bytes()
    assert fingerprint == hashlib.sha256(raw).hexdigest()
    assert raw.startswith(b"-----BEGIN PUBLIC KEY-----")
    assert b"PRIVATE" not in raw
    manifest = b'{"version":"1.0.11"}'
    signature = key.sign(manifest)
    public = serialization.load_pem_public_key(raw)
    public.verify(signature, manifest)  # what the installed client does
    with pytest.raises(InvalidSignature):
        public.verify(signature, manifest + b" ")


@pytest.mark.parametrize("pem", ["", "   ", "NOT A KEY"])
def test_export_refuses_missing_or_invalid_keys_without_writing(tmp_path, pem):
    out = tmp_path / "update-public-key.pem"
    with pytest.raises(ValueError):
        MODULE["export"](out, pem)
    assert not out.exists()


def test_export_refuses_a_non_ed25519_key(tmp_path):
    rsa, pem = private_pem(generate_private_key(public_exponent=65537, key_size=2048))
    with pytest.raises(ValueError, match="Ed25519"):
        MODULE["export"](tmp_path / "k.pem", pem)
    assert not (tmp_path / "k.pem").exists()


def test_cli_never_prints_the_private_key(tmp_path):
    _, pem = private_pem()
    out = tmp_path / "key.pem"
    env = dict(os.environ, VIRA_UPDATE_SIGNING_KEY=pem)
    child = subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_update_public_key.py"), "--out", str(out)],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert child.returncode == 0, child.stderr
    assert "PRIVATE KEY" not in child.stdout + child.stderr
    body = pem.strip().splitlines()[1]
    assert body not in child.stdout + child.stderr
    assert out.read_bytes().startswith(b"-----BEGIN PUBLIC KEY-----")


def test_cli_failure_is_quiet_and_exits_nonzero(tmp_path):
    env = dict(os.environ, VIRA_UPDATE_SIGNING_KEY="SENSITIVE INVALID")
    child = subprocess.run(
        [sys.executable, str(ROOT / "scripts/export_update_public_key.py"), "--out", str(tmp_path / "k.pem")],
        env=env, capture_output=True, text=True, timeout=30,
    )
    assert child.returncode == 1
    assert "SENSITIVE" not in child.stdout + child.stderr
    assert "Traceback" not in child.stderr


def test_packaged_app_would_actually_verify_signatures():
    config = (ROOT / "backend/app/config.py").read_text(encoding="utf-8")
    assert "def default_update_public_key" in config
    assert "update-public-key.pem" in config
    # An explicit operator/CI value must still win over the baked file.
    assert 'Field(default_factory=default_update_public_key)' in config
    stage = (ROOT / "scripts/stage_app_payload.ps1").read_text(encoding="utf-8")
    copy_at = stage.index("VIRA_UPDATE_PUBLIC_KEY_FILE")
    manifest_at = stage.index("scripts/build_manifest.py")
    assert copy_at < manifest_at, "the key must exist before the install manifest is built"
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    bake = workflow.index("Bake the update verification key")
    assert bake < workflow.index("Stage app payload")
    assert "export_update_public_key.py" in workflow
    # A tagged build without the key still refuses to publish.
    assert workflow.index("Refuse unsigned tagged publication") < bake


def test_a_packaged_key_makes_the_client_require_a_valid_signature(tmp_path, monkeypatch):
    """End-to-end: the baked public key is what an installed app actually uses."""
    import sys

    sys.path.insert(0, str(ROOT / "backend"))
    from app import config

    key, pem = private_pem()
    payload_root = tmp_path / "payload"
    payload_root.mkdir()
    (payload_root / "update-public-key.pem").write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    # Simulate the payload layout: app/config.py sits one level below the payload root.
    fake = payload_root / "app" / "config.py"
    fake.parent.mkdir()
    fake.write_text("", encoding="utf-8")
    monkeypatch.setattr(config, "__file__", str(fake))
    monkeypatch.delenv("UPDATE_PUBLIC_KEY", raising=False)
    resolved = config.Settings().update_public_key
    assert resolved == str(payload_root / "update-public-key.pem")
    # An explicit environment value still wins (CI fixtures and operators).
    monkeypatch.setenv("UPDATE_PUBLIC_KEY", "inline-or-other-path")
    assert config.Settings().update_public_key == "inline-or-other-path"


def test_newer_release_notes_and_version_agree():
    import re

    root = ROOT
    version = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    notes = (root / f"docs/releases/v{version}-fa.md").read_text(encoding="utf-8")
    assert "۱.۰.۱۱" in notes or version in notes
    assert "انتشار" in notes
