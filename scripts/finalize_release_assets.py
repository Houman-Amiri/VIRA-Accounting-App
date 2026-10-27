"""Sign final metadata in memory, then checksum all flat release assets.

This is packaging integrity, NOT native acceptance, license clearance, or
verification that recipients trust the chosen signing key. Never writes a key.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import uuid
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def no_links(path: Path) -> None:
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.stat(), "st_file_attributes", 0) & 0x400):
            raise ValueError("Release asset reparse paths are forbidden")


def atomic(path: Path, content: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def finalize(directory: Path, key_pem: str | None, *, require_signature: bool = False) -> dict:
    directory = directory.absolute()
    no_links(directory)
    if not directory.is_dir():
        raise ValueError("Existing release asset directory required")
    # Recheck the environment here too: callers cannot accidentally omit the CLI
    # flag and produce an unsigned public tagged release.
    required = require_signature or os.environ.get("GITHUB_REF", "").startswith("refs/tags/")
    key_pem = (key_pem or "").strip()
    if required and not key_pem:
        raise ValueError("Tagged release requires VIRA_UPDATE_SIGNING_KEY; no unsigned fallback")
    latest, signature, sums = (directory / name for name in ("latest.json", "latest.json.sig", "SHA256SUMS.txt"))
    for path in directory.iterdir():
        no_links(path)
        if not path.is_file():
            continue  # app/ is an assembly directory, not a flat published asset.
        if any(c in path.name for c in "\r\n"):
            raise ValueError("Release filenames must not contain line breaks")
        if ".tmp-" in path.name or path.name.casefold() in {"update.key", ".env"}:
            raise ValueError("Secret or unfinished file in release assets")
        with path.open("rb") as stream:
            head = stream.read(4096)
        if head.startswith(b"-----BEGIN ") and b"PRIVATE KEY-----" in head:
            raise ValueError("Private signing material in release assets")
    if not latest.is_file():
        raise ValueError("Final latest.json required")
    signed = False
    if key_pem:
        try:
            key = serialization.load_pem_private_key(key_pem.encode(), password=None)
        except (ValueError, TypeError) as from_error:
            raise ValueError("Invalid release signing key") from from_error
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("Ed25519 release signing key required")
        raw = latest.read_bytes()
        payload = key.sign(raw)
        key.public_key().verify(payload, raw)
        atomic(signature, payload)
        signed = True
    elif signature.exists():
        raise ValueError("Existing signature cannot be adopted without the signing key")
    assets = sorted((p for p in directory.iterdir() if p.is_file() and p != sums), key=lambda p: p.name)
    lines = []
    for path in assets:
        no_links(path)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        lines.append(f"{digest}  {path.name}\n")
    atomic(sums, "".join(lines).encode("utf-8"))
    return dict(signed=signed, checksummed_assets=len(assets))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--require-signature", action="store_true")
    args = parser.parse_args()
    try:
        result = finalize(args.directory, os.environ.get("VIRA_UPDATE_SIGNING_KEY"), require_signature=args.require_signature)
    except (ValueError, OSError):
        # Never echo a PEM, its parse error, or any environment value.
        print("Release finalization refused: check asset paths, signing configuration and unfinished/private files.", file=sys.stderr)
        return 1
    print(f"Release assets finalized: signed={result['signed']}, checksummed={result['checksummed_assets']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
