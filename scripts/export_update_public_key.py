"""Bake the update verification key into the packaged app.

The release pipeline gives this script the Ed25519 PRIVATE signing key only in
memory; the app that ships must carry the PUBLIC key so an installed client can
actually reject an unsigned or tampered ``latest.json``. Without this step the
signature exists in the release but no installed client would check it.

Never writes or prints the private key.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def export(destination: Path, key_pem: str) -> str:
    key_pem = (key_pem or "").strip()
    if not key_pem:
        raise ValueError("VIRA_UPDATE_SIGNING_KEY is required to bake a verification key")
    try:
        key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    except (ValueError, TypeError) as error:
        raise ValueError("Invalid release signing key") from error
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 release signing key required")
    public = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(public)
    return hashlib.sha256(public).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        fingerprint = export(args.out, os.environ.get("VIRA_UPDATE_SIGNING_KEY", ""))
    except (ValueError, OSError):
        print("Update public key export refused; check the signing key secret.", file=sys.stderr)
        return 1
    print(f"Update verification key written to {args.out} (sha256 {fingerprint[:16]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
