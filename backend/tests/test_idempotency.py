"""Idempotency-Key semantics on POST /journal-entries (Phase 4 §9)."""

from __future__ import annotations


async def _accounts(client) -> tuple[str, str]:
    codes = [("8101", "idem-a"), ("8102", "idem-b")]
    ids = []
    for code, name in codes:
        resp = await client.post(
            "/api/v1/accounts",
            json={"code": code, "name": name, "account_type": "ASSET"},
        )
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["id"])
    return ids[0], ids[1]


def _payload(a: str, b: str, amount: str = "10.0000") -> dict:
    return {
        "transaction_date": "2026-10-14",
        "description": "idempotent entry",
        "splits": [
            {"account_id": a, "debit": amount},
            {"account_id": b, "credit": amount},
        ],
    }


async def test_retry_with_same_key_returns_same_entry(client) -> None:
    a, b = await _accounts(client)
    body = _payload(a, b)
    headers = {"Idempotency-Key": "11111111-1111-7111-8111-111111111111"}

    r1 = await client.post("/api/v1/journal-entries", json=body, headers=headers)
    assert r1.status_code == 201, r1.text
    r2 = await client.post("/api/v1/journal-entries", json=body, headers=headers)
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]

    listing = await client.get("/api/v1/journal-entries")
    assert len([e for e in listing.json() if e["description"] == "idempotent entry"]) == 1


async def test_same_key_different_payload_conflicts(client) -> None:
    a, b = await _accounts(client)
    headers = {"Idempotency-Key": "22222222-2222-7222-8222-222222222222"}
    r1 = await client.post(
        "/api/v1/journal-entries", json=_payload(a, b, "10.0000"), headers=headers
    )
    assert r1.status_code == 201
    r2 = await client.post(
        "/api/v1/journal-entries", json=_payload(a, b, "99.0000"), headers=headers
    )
    assert r2.status_code == 409
    assert r2.json()["code"] == "idempotency_key_reuse"


async def test_without_key_creates_distinct_entries(client) -> None:
    a, b = await _accounts(client)
    body = _payload(a, b)
    r1 = await client.post("/api/v1/journal-entries", json=body)
    r2 = await client.post("/api/v1/journal-entries", json=body)
    assert r1.status_code == 201 and r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


async def test_failed_request_not_replayed(client) -> None:
    """4xx results are not stored — the retry re-executes (Stripe semantics)."""
    a, b = await _accounts(client)
    headers = {"Idempotency-Key": "33333333-3333-7333-8333-333333333333"}
    bad = _payload(a, b, "10.0000")
    bad["splits"][1]["credit"] = "7.0000"  # unbalanced → 422
    r1 = await client.post("/api/v1/journal-entries", json=bad, headers=headers)
    assert r1.status_code == 422
    good = _payload(a, b, "10.0000")
    r2 = await client.post("/api/v1/journal-entries", json=good, headers=headers)
    assert r2.status_code == 201
