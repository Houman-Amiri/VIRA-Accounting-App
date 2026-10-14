"""Phase 5 security tests: RBAC, sudo, MFA recovery, rate limiting, webhooks,
envelope encryption, redaction, CSV injection, security headers."""

from __future__ import annotations

import time
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.ids import utc_now_iso, uuid7
from app.models import MfaRecoveryCode, SecurityAuditLog
from app.security.envelope import EnvelopeError, build_envelope, generate_key
from app.security.ratelimit import RateLimiter
from app.security.redact import REDACTED, redact_event
from app.security.sudo import issue_sudo_token, verify_sudo_token
from app.security.totp import generate_recovery_codes, hash_recovery_code
from app.security.webhooks import compute_signature, verify_webhook
from app.services.export import sanitize_csv_cell, write_csv_safe


# ---------------------------------------------------------------- helpers ---
async def _accounts(client) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:6]
    ids = []
    for code, name in ((f"81{suffix}", "sec-a"), (f"82{suffix}", "sec-b")):
        resp = await client.post(
            "/api/v1/accounts",
            json={"code": code, "name": name, "account_type": "ASSET"},
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids[0], ids[1]


def _entry_payload(a: str, b: str, amount: str = "100.0000") -> dict[str, Any]:
    return {
        "transaction_date": "2026-10-14",
        "description": "security-test",
        "splits": [
            {"account_id": a, "debit": amount, "credit": "0.0000"},
            {"account_id": b, "debit": "0.0000", "credit": amount},
        ],
    }


async def _sudo(client) -> str:
    r = await client.post("/api/v1/auth/sudo", json={"password": "test-password-1"})
    assert r.status_code == 200, r.text
    return r.json()["sudo_token"]


# ------------------------------------------------------------- envelope ---
def test_envelope_roundtrip_and_rotation() -> None:
    key1, key2 = generate_key(), generate_key()
    env1 = build_envelope(key1)
    ct = env1.encrypt("super-secret-token")
    assert ct != "super-secret-token"
    assert env1.decrypt(ct) == "super-secret-token"
    # rotation: old ciphertext still decrypts via the secondary key
    env2 = build_envelope(key2 + "," + key1)
    assert env2.decrypt(ct) == "super-secret-token"
    rotated = env2.rotate(ct)
    assert env2.decrypt(rotated) == "super-secret-token"
    with pytest.raises(EnvelopeError):
        build_envelope(key1).decrypt(build_envelope(key2).encrypt("x"))


# ----------------------------------------------------------------- sudo ---
def test_sudo_token_ttl_and_binding() -> None:
    class S:
        session_secret = "test-secret"

    tok = issue_sudo_token(S, "user-1", now=1000.0)  # type: ignore[arg-type]
    assert verify_sudo_token(S, tok, "user-1", now=1000.0)  # type: ignore[arg-type]
    assert verify_sudo_token(S, tok, "user-1", now=1299.0)  # type: ignore[arg-type]
    assert not verify_sudo_token(S, tok, "user-1", now=1301.0)  # type: ignore[arg-type]
    assert not verify_sudo_token(S, tok, "user-2", now=1000.0)  # type: ignore[arg-type]
    assert not verify_sudo_token(S, tok + "x", "user-1", now=1000.0)  # type: ignore[arg-type]


async def test_sudo_required_for_api_keys_and_period_reopen(client, database) -> None:
    # API-key creation without sudo → 403
    r = await client.post("/api/v1/api-keys", json={"name": "ingest"})
    assert r.status_code == 403
    token = await _sudo(client)
    r = await client.post(
        "/api/v1/api-keys", json={"name": "ingest"}, headers={"X-Sudo-Token": token}
    )
    assert r.status_code == 201
    body = r.json()
    assert body["api_key"].startswith("vira_sk_")
    key_id = body["record"]["id"]
    with database.session() as s:
        events = (
            s.execute(select(SecurityAuditLog).where(SecurityAuditLog.event == "API_KEY_CREATED"))
            .scalars()
            .all()
        )
    assert events and events[-1].actor_id is not None
    # revoke with sudo
    r = await client.post(
        f"/api/v1/api-keys/{key_id}/revoke", headers={"X-Sudo-Token": token}
    )
    assert r.status_code == 200
    # fiscal period reopen requires sudo
    r = await client.post(
        "/api/v1/fiscal-periods",
        json={"name": "1405", "start_date": "2026-03-21", "end_date": "2027-03-20"},
    )
    assert r.status_code == 201
    period_id = r.json()["id"]
    assert (await client.post(f"/api/v1/fiscal-periods/{period_id}/close")).status_code == 200
    assert (await client.post(f"/api/v1/fiscal-periods/{period_id}/reopen")).status_code == 403
    r = await client.post(
        f"/api/v1/fiscal-periods/{period_id}/reopen", headers={"X-Sudo-Token": token}
    )
    assert r.status_code == 200
    assert r.json()["is_closed"] is False
    with database.session() as s:
        events = (
            s.execute(select(SecurityAuditLog).where(SecurityAuditLog.event == "PERIOD_UNLOCKED"))
            .scalars()
            .all()
        )
    assert events


async def test_database_dump_sudo_and_audit(client, database) -> None:
    assert (await client.post("/api/v1/exports/database-dump")).status_code == 403
    token = await _sudo(client)
    r = await client.post("/api/v1/exports/database-dump", headers={"X-Sudo-Token": token})
    assert r.status_code == 200
    assert r.content[:16] == b"SQLite format 3\x00"
    with database.session() as s:
        events = (
            s.execute(select(SecurityAuditLog).where(SecurityAuditLog.event == "BACKUP_EXPORTED"))
            .scalars()
            .all()
        )
    assert events


# ------------------------------------------------------------------ RBAC ---
async def test_auditor_is_read_only(client, database) -> None:
    from app.api.auth import create_user

    a, b = await _accounts(client)  # create accounts as owner first
    with database.session() as s:
        create_user(s, username="aud", password="auditor-pass-1", role="AUDITOR")
    r = await client.post(
        "/api/v1/auth/login", json={"username": "aud", "password": "auditor-pass-1"}
    )
    assert r.status_code == 200
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    # reads are fine
    assert (await client.get("/api/v1/accounts")).status_code == 200
    # every mutation is 403
    r = await client.post("/api/v1/journal-entries", json=_entry_payload(a, b))
    assert r.status_code == 403
    r = await client.post("/api/v1/reports/balance-snapshots", json={})
    assert r.status_code == 403
    r = await client.post("/api/v1/reconciliation/sessions", json={"name": "x", "bank_account": "1010"})
    assert r.status_code == 403


async def test_ingest_key_scope(client, database) -> None:
    token = await _sudo(client)
    r = await client.post(
        "/api/v1/api-keys", json={"name": "scanner"}, headers={"X-Sudo-Token": token}
    )
    api_key = r.json()["api_key"]
    a, b = await _accounts(client)
    # key can create DRAFT journal entries without a cookie session
    client.cookies.clear()
    client.headers.pop("X-CSRF-Token", None)
    r = await client.post(
        "/api/v1/journal-entries",
        json=_entry_payload(a, b),
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 201
    assert r.json()["status"] == "DRAFT"
    # invalid key → 401
    r = await client.post(
        "/api/v1/journal-entries",
        json=_entry_payload(a, b),
        headers={"X-API-Key": "vira_sk_dead_beef"},
    )
    assert r.status_code == 401
    # revoked key stops working
    r = await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "test-password-1"}
    )
    client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    token = await _sudo(client)
    keys = await client.get("/api/v1/api-keys", headers={"X-Sudo-Token": token})
    key_id = keys.json()[-1]["id"]
    await client.post(f"/api/v1/api-keys/{key_id}/revoke", headers={"X-Sudo-Token": token})
    client.cookies.clear()
    r = await client.post(
        "/api/v1/journal-entries",
        json=_entry_payload(a, b),
        headers={"X-API-Key": api_key},
    )
    assert r.status_code == 401


# ------------------------------------------------------------------- MFA ---
async def test_recovery_codes_single_use(client, database) -> None:
    r = await client.post("/api/v1/auth/totp/enroll")
    assert r.status_code == 200
    codes = r.json()["recovery_codes"]
    assert len(codes) == 10
    secret = r.json()["secret"]
    # only hashes are stored; TOTP secret is stored ciphertext
    with database.session() as s:
        rows = s.execute(select(MfaRecoveryCode)).scalars().all()
        assert rows and all(c.code_hash not in codes for c in rows)
        from app.models import User

        user = s.execute(select(User).where(User.username == "owner")).scalar_one()
        assert user.totp_secret_enc is not None and user.totp_secret_enc != secret
    # single-use recovery
    r1 = await client.post("/api/v1/auth/totp/recovery-verify", json={"code": codes[0]})
    assert r1.json() == {"verified": True}
    r2 = await client.post("/api/v1/auth/totp/recovery-verify", json={"code": codes[0]})
    assert r2.json() == {"verified": False}
    # a fresh unused code still works
    r3 = await client.post("/api/v1/auth/totp/recovery-verify", json={"code": codes[1]})
    assert r3.json() == {"verified": True}


def test_recovery_hash_uniqueness() -> None:
    codes = generate_recovery_codes()
    assert len(codes) == len(set(codes))
    hashes = [hash_recovery_code(c) for c in codes]
    assert len(hashes) == len(set(hashes))


# ----------------------------------------------------------- rate limit ---
def test_login_lockout_exponential() -> None:
    rl = RateLimiter(rate_per_minute=5.0, burst=5.0, base_lockout_seconds=30.0)
    ident = "user@ip"
    assert all(rl.allow("login", ident, now=1000.0) for _ in range(5))
    assert not rl.allow("login", ident, now=1000.0)  # burst exhausted
    for _ in range(4):
        assert rl.register_failure("login", ident, now=1000.0) == 0.0  # no lock yet
    lock1 = rl.register_failure("login", ident, now=1000.0)  # 5th failure locks
    assert lock1 == 1030.0
    assert not rl.allow("login", ident, now=1010.0)  # locked
    lock2 = rl.register_failure("login", ident, now=1010.0)
    assert lock2 > lock1  # exponential
    rl.register_success("login", ident)
    assert rl.allow("login", ident, now=1130.0)  # tokens refilled after 2 minutes


async def test_login_rate_limit_http(client) -> None:
    from app.security.ratelimit import limiter

    limiter.reset()
    last = None
    for _ in range(6):
        last = await client.post(
            "/api/v1/auth/login", json={"username": "nobody", "password": "wrong"}
        )
    assert last is not None and last.status_code == 429


# --------------------------------------------------------------- webhooks ---
def test_webhook_signature_freshness() -> None:
    secret = "whsec_test"
    body = b'{"event":"sync"}'
    sig = compute_signature(secret, body)
    good = verify_webhook(
        secret=secret, body=body, signature=sig, timestamp_raw="1000", now=1000.0
    )
    assert good.ok
    bad_sig = verify_webhook(
        secret=secret,
        body=body,
        signature="sha256=" + "0" * 64,
        timestamp_raw="1000",
        now=1000.0,
    )
    assert not bad_sig.ok
    stale = verify_webhook(
        secret=secret, body=body, signature=sig, timestamp_raw="300", now=1000.0
    )
    assert not stale.ok
    missing = verify_webhook(secret=secret, body=body, signature=None, timestamp_raw=None)
    assert not missing.ok


async def test_webhook_endpoint_roundtrip(client, database) -> None:
    # no secret configured → rejected
    r = await client.post("/api/v1/webhooks/bank", content=b"{}")
    assert r.json()["status"] == "rejected"
    # configure secret, verify accept + dedup + bad signature
    from app.models import ExternalCredential
    from app.security.envelope import get_envelope

    env = get_envelope()
    with database.session() as s:
        s.add(
            ExternalCredential(
                id=uuid7(),
                provider="bank_webhook",
                label="signing_secret",
                ciphertext=env.encrypt("whsec_abc"),
                key_id=env.key_id,
                created_at=utc_now_iso(),
                updated_at=utc_now_iso(),
            )
        )
    body = b'{"hello":"world"}'
    ts = str(int(time.time()))
    sig = compute_signature("whsec_abc", body)
    headers = {
        "X-VIRA-Signature": sig,
        "X-VIRA-Timestamp": ts,
        "X-VIRA-Event-Id": "evt-1",
    }
    r = await client.post("/api/v1/webhooks/bank", content=body, headers=headers)
    assert r.json()["status"] == "accepted"
    r = await client.post("/api/v1/webhooks/bank", content=body, headers=headers)
    assert r.json()["status"] == "duplicate"
    r = await client.post(
        "/api/v1/webhooks/bank",
        content=body,
        headers={
            **headers,
            "X-VIRA-Event-Id": "evt-2",
            "X-VIRA-Signature": "sha256=" + "0" * 64,
        },
    )
    assert r.json()["status"] == "rejected"


# -------------------------------------------------- redaction / CSV / sec ---
def test_redaction_scrubs_sensitive_fields() -> None:
    out = redact_event(
        None,
        "info",
        {
            "password": "hunter2",
            "authorization": "Bearer xyz",
            "iban": "DE89370400440532013000",
            "nested": {"api_key": "sk-123", "note": "iban DE89370400440532013000 in text"},
            "amount": 12,
        },
    )
    assert out["password"] == REDACTED
    assert out["authorization"] == REDACTED
    assert out["iban"] == REDACTED
    assert out["nested"]["api_key"] == REDACTED
    assert "DE89370400440532013000" not in out["nested"]["note"]
    assert out["amount"] == 12


def test_csv_formula_injection_sanitized() -> None:
    assert sanitize_csv_cell("=cmd|'/c calc'!A0") == "'=cmd|'/c calc'!A0"
    assert sanitize_csv_cell("+1234") == "'+1234"
    assert sanitize_csv_cell("-5") == "'-5"
    assert sanitize_csv_cell("@x") == "'@x"
    assert sanitize_csv_cell("plain") == "plain"
    csv_text = write_csv_safe(
        [{"memo": "=HYPERLINK(x)", "amount": "10.0000"}], ["memo", "amount"]
    )
    assert "'=HYPERLINK(x)" in csv_text


async def test_security_headers_present(client) -> None:
    r = await client.get("/api/v1/health/live")
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["Referrer-Policy"] == "same-origin"
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]


async def test_ledger_csv_export(client) -> None:
    r = await client.get("/api/v1/exports/ledger.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "entry_number" in r.text


# ----------------------------------------------- idempotent reconciliation ---
async def test_reconciliation_complete_idempotent_and_reopen_sudo(client, database) -> None:
    a, _ = await _accounts(client)
    r = await client.post(
        "/api/v1/reconciliation/sessions",
        json={
            "account_id": a,
            "statement_date": "2026-10-14",
            "beginning_balance": "0.0000",
            "ending_balance": "0.0000",
        },
    )
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    headers = {"Idempotency-Key": "99999999-9999-7999-8999-999999999999"}
    r1 = await client.post(
        f"/api/v1/reconciliation/sessions/{sid}/complete", headers=headers
    )
    assert r1.status_code == 200
    r2 = await client.post(
        f"/api/v1/reconciliation/sessions/{sid}/complete", headers=headers
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == r1.json()["id"]
    # reopen requires sudo
    assert (
        await client.post(f"/api/v1/reconciliation/sessions/{sid}/reopen")
    ).status_code == 403
    token = await _sudo(client)
    r = await client.post(
        f"/api/v1/reconciliation/sessions/{sid}/reopen", headers={"X-Sudo-Token": token}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "OPEN"


async def test_login_security_events_recorded(client, database) -> None:
    await client.post("/api/v1/auth/login", json={"username": "owner", "password": "nope"})
    await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "test-password-1"}
    )
    with database.session() as s:
        events = (
            s.execute(
                select(SecurityAuditLog).where(
                    SecurityAuditLog.event.in_(["LOGIN_FAILED", "LOGIN_SUCCESS"])
                )
            )
            .scalars()
            .all()
        )
        kinds = {e.event for e in events}
        assert "LOGIN_FAILED" in kinds and "LOGIN_SUCCESS" in kinds
        # immutability: UPDATE rejected by trigger
        from sqlalchemy.exc import DatabaseError

        with pytest.raises(DatabaseError):
            s.execute(
                SecurityAuditLog.__table__.update()
                .where(SecurityAuditLog.id == events[0].id)
                .values(event="X")
            )
            s.flush()
        s.rollback()
