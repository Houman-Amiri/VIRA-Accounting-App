"""Ed25519 signing for ``latest.json`` (Phase 8 §8).

The release pipeline signs the raw ``latest.json`` bytes → ``latest.json.sig``;
the app verifies with a baked-in public key before trusting any update.

Usage:
    python scripts/sign_update.py keygen --pub update.pub --priv update.key
    python scripts/sign_update.py sign --key update.key --file latest.json
    python scripts/sign_update.py verify --pub update.pub --file latest.json --sig latest.json.sig
"""

from __future__ import annotations

import argparse
import base64
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.update_engine import verify_latest_signature  # noqa: E402


def _keygen(pub: Path, priv: Path) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = Ed25519PrivateKey.generate()
    priv.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    print(f"[sign_update] public key -> {pub} (bake into the app as UPDATE_PUBLIC_KEY)")
    return 0


def _sign(key_path: Path, file_path: Path) -> int:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(key, Ed25519PrivateKey)
    sig = key.sign(file_path.read_bytes())
    sig_path = file_path.with_suffix(file_path.suffix + ".sig")
    sig_path.write_bytes(sig)
    print(f"[sign_update] signature -> {sig_path} ({base64.b64encode(sig).decode()[:16]}…)")
    return 0


def _verify(pub_path: Path, file_path: Path, sig_path: Path) -> int:
    try:
        verify_latest_signature(file_path.read_bytes(), sig_path.read_bytes(), pub_path.read_bytes())
    except Exception as exc:  # noqa: BLE001
        print(f"[sign_update] VERIFY FAILED: {exc}")
        return 1
    print("[sign_update] signature OK")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ed25519 latest.json signing")
    sub = parser.add_subparsers(dest="cmd", required=True)
    k = sub.add_parser("keygen")
    k.add_argument("--pub", type=Path, required=True)
    k.add_argument("--priv", type=Path, required=True)
    s = sub.add_parser("sign")
    s.add_argument("--key", type=Path, required=True)
    s.add_argument("--file", type=Path, required=True)
    v = sub.add_parser("verify")
    v.add_argument("--pub", type=Path, required=True)
    v.add_argument("--file", type=Path, required=True)
    v.add_argument("--sig", type=Path, required=True)
    args = parser.parse_args()
    if args.cmd == "keygen":
        return _keygen(args.pub, args.priv)
    if args.cmd == "sign":
        return _sign(args.key, args.file)
    return _verify(args.pub, args.file, args.sig)


if __name__ == "__main__":
    raise SystemExit(main())
