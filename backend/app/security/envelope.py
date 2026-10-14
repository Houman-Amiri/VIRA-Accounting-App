"""Field-level envelope encryption (Phase 5 §5).

AES-256 (Fernet) application-layer encryption for third-party credentials and
PII (bank tokens, webhook secrets, IBANs, TOTP secrets).  Keys come from
``APP_ENCRYPTION_KEY`` — one or more base64 Fernet keys separated by commas.
The FIRST key is the primary (encrypts new values); all keys decrypt, enabling
zero-downtime rotation via :class:`cryptography.fernet.MultiFernet`.

`key_id` is the first 8 chars of the SHA-256 of the primary key so stored rows
identify which key encrypted them without revealing key material.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class EnvelopeError(ValueError):
    """Raised for missing/invalid keys or undecryptable ciphertext."""


def generate_key() -> str:
    """Generate a fresh Fernet key (base64 url-safe 32 bytes)."""
    return Fernet.generate_key().decode("ascii")


@dataclass(frozen=True)
class Envelope:
    multi: MultiFernet
    key_id: str

    def encrypt(self, plaintext: str) -> str:
        token = self.multi.encrypt(plaintext.encode("utf-8"))
        return token.decode("ascii")

    def decrypt(self, ciphertext: str) -> str:
        try:
            return self.multi.decrypt(ciphertext.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise EnvelopeError("ciphertext cannot be decrypted with configured keys") from exc

    def rotate(self, ciphertext: str) -> str:
        """Re-encrypt with the current primary key."""
        return self.multi.rotate(ciphertext.encode("ascii")).decode("ascii")


def build_envelope(raw_key: str | None) -> Envelope:
    """Build an :class:`Envelope` from the configured key material.

    Accepts one or more comma-separated **Fernet keys** (44-char urlsafe
    base64).  Empty input yields a development-only ephemeral key (production
    boot validation refuses to start without APP_ENCRYPTION_KEY).
    """
    if not raw_key:
        # Development fallback — a throwaway key; production boot validation
        # refuses to start without APP_ENCRYPTION_KEY.
        raw_key = generate_key()
    parts = [p.strip() for p in raw_key.split(",") if p.strip()]
    if not parts:
        raise EnvelopeError("APP_ENCRYPTION_KEY contains no key material")
    fernets: list[Fernet] = []
    for part in parts:
        try:
            fernets.append(Fernet(part.encode("ascii")))
        except Exception as exc:  # noqa: BLE001 - normalize key parse failures
            raise EnvelopeError(
                "invalid Fernet key material — generate with "
                "app.security.envelope.generate_key()"
            ) from exc
    multi = MultiFernet(fernets)
    key_id = hashlib.sha256(parts[0].encode("ascii")).hexdigest()[:8]
    return Envelope(multi=multi, key_id=key_id)


_APP_ENVELOPE: Envelope | None = None


def get_envelope() -> Envelope:
    """Process-wide envelope built from ``APP_ENCRYPTION_KEY`` (lazy singleton)."""
    global _APP_ENVELOPE
    if _APP_ENVELOPE is None:
        _APP_ENVELOPE = build_envelope(os.environ.get("APP_ENCRYPTION_KEY", ""))
    return _APP_ENVELOPE


def set_envelope(envelope: Envelope | None) -> None:
    """Override the process-wide envelope (tests / startup wiring)."""
    global _APP_ENVELOPE
    _APP_ENVELOPE = envelope
