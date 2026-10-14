"""Keyset/cursor pagination on /journal-entries (Phase 4 §8)."""

from __future__ import annotations

import base64
import json


async def _accounts(client) -> tuple[str, str]:
    ids = []
    for code in ("8201", "8202"):
        resp = await client.post(
            "/api/v1/accounts",
            json={"code": code, "name": f"pg-{code}", "account_type": "ASSET"},
        )
        assert resp.status_code == 201
        ids.append(resp.json()["id"])
    return ids[0], ids[1]


async def _create_entries(client, a: str, b: str, n: int, *, day: int) -> list[str]:
    out = []
    for i in range(n):
        resp = await client.post(
            "/api/v1/journal-entries",
            json={
                "transaction_date": f"2026-10-{day:02d}",
                "description": f"entry {day}-{i}",
                "splits": [
                    {"account_id": a, "debit": "1.0000"},
                    {"account_id": b, "credit": "1.0000"},
                ],
            },
        )
        assert resp.status_code == 201, resp.text
        out.append(resp.json()["id"])
    return out


async def test_cursor_pages_do_not_overlap_or_skip(client) -> None:
    a, b = await _accounts(client)
    await _create_entries(client, a, b, 7, day=5)

    seen: list[str] = []
    cursor = None
    for _ in range(10):
        resp = await client.get(
            "/api/v1/journal-entries", params={"limit": 3, **({"cursor": cursor} if cursor else {})}
        )
        assert resp.status_code == 200
        page = resp.json()
        seen.extend(e["id"] for e in page)
        cursor = resp.headers.get("x-next-cursor")
        if not cursor:
            break

    assert len(seen) == len(set(seen)), "cursor pages must not repeat rows"
    assert len(seen) == 7, "cursor pages must cover every row exactly once"


async def test_cursor_order_is_date_desc_then_id_desc(client) -> None:
    a, b = await _accounts(client)
    await _create_entries(client, a, b, 3, day=1)
    await _create_entries(client, a, b, 3, day=2)

    resp = await client.get("/api/v1/journal-entries", params={"limit": 2})
    page = resp.json()
    assert page[0]["transaction_date"] >= page[1]["transaction_date"]

    nxt = resp.headers["x-next-cursor"]
    raw = json.loads(base64.urlsafe_b64decode(nxt))
    assert raw == [page[1]["transaction_date"], page[1]["id"]]


async def test_status_filter_with_cursor(client) -> None:
    a, b = await _accounts(client)
    ids = await _create_entries(client, a, b, 2, day=8)
    posted = await client.post(f"/api/v1/journal-entries/{ids[0]}/post", json={"version_id": 1})
    assert posted.status_code == 200

    resp = await client.get(
        "/api/v1/journal-entries", params={"status": "POSTED", "limit": 10}
    )
    rows = resp.json()
    assert [e["id"] for e in rows] == [ids[0]]
