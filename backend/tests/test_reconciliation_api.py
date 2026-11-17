"""Reconciliation screen support endpoints.

The reconcile page used to render hardcoded demo rows and its buttons only
mutated local state. These endpoints are what make the buttons real:

* ``GET /reconciliation/sessions`` — the sessions the screen offers to work on;
* ``POST /imports/lines/{id}/status`` — «نادیده گرفتن» / «تطبیق» on a statement
  line, persisted instead of kept in the browser;
* ``GET /imports/lines`` — carries ``account_id`` so the screen can show the
  lines of the account being reconciled.
"""

from __future__ import annotations

import pytest

CSV = (
    b"date,payee,amount,reference\n"
    b"2026-10-01,Aria Co,1250.50,1024\n"
    b"2026-10-03,Pars,480.00,8811\n"
)


async def _account(client, code: str, name: str) -> str:
    r = await client.post(
        "/api/v1/accounts",
        json={"code": code, "name": name, "account_type": "ASSET"},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _session(client, account_id: str, *, ending: str = "0.0000") -> dict:
    r = await client.post(
        "/api/v1/reconciliation/sessions",
        json={
            "account_id": account_id,
            "statement_date": "2026-10-14",
            "beginning_balance": "0.0000",
            "ending_balance": ending,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


async def _import_lines(client, account_id: str) -> list[dict]:
    r = await client.post(
        "/api/v1/imports/bank",
        files={"file": ("statement.csv", CSV, "text/csv")},
        data={"account_id": account_id},
    )
    assert r.status_code == 201, r.text
    lines = await client.get("/api/v1/imports/lines")
    assert lines.status_code == 200, lines.text
    return lines.json()


# ------------------------------------------------------------ session listing ---
@pytest.mark.asyncio
async def test_sessions_list_is_empty_before_any_session(client) -> None:
    r = await client.get("/api/v1/reconciliation/sessions")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_sessions_list_returns_created_sessions_newest_first(client) -> None:
    bank = await _account(client, "1020", "بانک")
    first = await _session(client, bank)
    second = await _session(client, bank, ending="10.0000")

    r = await client.get("/api/v1/reconciliation/sessions")
    assert r.status_code == 200
    ids = [row["id"] for row in r.json()]
    assert ids == [second["id"], first["id"]]
    assert r.json()[0]["ending_balance"] == "10.0000"


@pytest.mark.asyncio
async def test_sessions_list_filters_by_account(client) -> None:
    bank = await _account(client, "1020", "بانک")
    cash = await _account(client, "1010", "صندوق")
    await _session(client, bank)
    await _session(client, cash)

    r = await client.get(
        "/api/v1/reconciliation/sessions", params={"account_id": bank}
    )
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["account_id"] == bank


# -------------------------------------------------------------- line status ---
@pytest.mark.asyncio
async def test_lines_carry_their_account(client) -> None:
    bank = await _account(client, "1020", "بانک")
    lines = await _import_lines(client, bank)
    assert len(lines) == 2
    assert all(line["account_id"] == bank for line in lines)
    assert all(line["status"] == "UNMATCHED" for line in lines)


@pytest.mark.asyncio
async def test_a_line_can_be_ignored_and_restored(client) -> None:
    bank = await _account(client, "1020", "بانک")
    line = (await _import_lines(client, bank))[0]

    r = await client.post(
        f"/api/v1/imports/lines/{line['id']}/status", json={"status": "IGNORED"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"id": line["id"], "status": "IGNORED"}

    lines = (await client.get("/api/v1/imports/lines")).json()
    assert next(row for row in lines if row["id"] == line["id"])["status"] == "IGNORED"

    r = await client.post(
        f"/api/v1/imports/lines/{line['id']}/status", json={"status": "UNMATCHED"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "UNMATCHED"


@pytest.mark.asyncio
async def test_a_line_can_be_marked_matched(client) -> None:
    bank = await _account(client, "1020", "بانک")
    line = (await _import_lines(client, bank))[0]
    r = await client.post(
        f"/api/v1/imports/lines/{line['id']}/status", json={"status": "MATCHED"}
    )
    assert r.status_code == 200
    assert r.json()["status"] == "MATCHED"


@pytest.mark.asyncio
async def test_unknown_line_is_a_404_not_a_500(client) -> None:
    r = await client.post(
        "/api/v1/imports/lines/no-such-line/status", json={"status": "IGNORED"}
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_an_unknown_status_is_rejected(client) -> None:
    bank = await _account(client, "1020", "بانک")
    line = (await _import_lines(client, bank))[0]
    r = await client.post(
        f"/api/v1/imports/lines/{line['id']}/status", json={"status": "MAYBE"}
    )
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_line_status_requires_a_signed_in_user(anon_client) -> None:
    r = await anon_client.post(
        "/api/v1/imports/lines/anything/status", json={"status": "IGNORED"}
    )
    # CSRF runs before authentication on mutations, so an anonymous POST is 403
    assert r.status_code == 403, r.text


# ------------------------------------------------------- the full owner path ---
@pytest.mark.asyncio
async def test_ledger_rows_expose_the_split_that_reconciliation_links(client) -> None:
    """The screen links a *split*; the ledger row must carry its id."""
    bank = await _account(client, "1020", "بانک")
    equity = await _account(client, "3010", "سرمایه")
    r = await client.post(
        "/api/v1/journal-entries",
        json={
            "transaction_date": "2026-10-02",
            "description": "واریز سرمایه",
            "splits": [
                {"account_id": bank, "debit": "1250.5000", "credit": "0.0000"},
                {"account_id": equity, "debit": "0.0000", "credit": "1250.5000"},
            ],
        },
    )
    assert r.status_code == 201, r.text
    entry = r.json()
    await client.post(f"/api/v1/journal-entries/{entry['id']}/post")

    ledger = await client.get(
        f"/api/v1/accounts/{bank}/ledger",
        params={"start": "2026-10-01", "end": "2026-10-31"},
    )
    assert ledger.status_code == 200, ledger.text
    row = ledger.json()["rows"][0]
    split_ids = {s["id"] for s in entry["splits"] if s["account_id"] == bank}
    assert row["split_id"] in split_ids
    assert row["reconciliation_status"] == "UNRECONCILED"


@pytest.mark.asyncio
async def test_import_suggest_link_complete_reconciles_a_real_statement(client) -> None:
    """The whole screen in one test: import, match, link, complete, verify."""
    bank = await _account(client, "1020", "بانک")
    equity = await _account(client, "3010", "سرمایه")
    entry = (
        await client.post(
            "/api/v1/journal-entries",
            json={
                "transaction_date": "2026-10-01",
                "description": "Aria Co invoice",
                "splits": [
                    {"account_id": bank, "debit": "1250.5000", "credit": "0.0000"},
                    {"account_id": equity, "debit": "0.0000", "credit": "1250.5000"},
                ],
            },
        )
    ).json()
    await client.post(f"/api/v1/journal-entries/{entry['id']}/post")

    lines = await _import_lines(client, bank)
    line = next(row for row in lines if row["status"] != "IGNORED")

    ledger = (
        await client.get(
            f"/api/v1/accounts/{bank}/ledger",
            params={"start": "2026-10-01", "end": "2026-10-31"},
        )
    ).json()
    split_id = ledger["rows"][0]["split_id"]

    session = await _session(client, bank, ending="1250.5000")
    sid = session["id"]

    linked = await client.post(
        f"/api/v1/reconciliation/sessions/{sid}/splits/{split_id}/link"
    )
    assert linked.status_code == 200, linked.text

    progress = await client.get(f"/api/v1/reconciliation/sessions/{sid}/progress")
    assert progress.status_code == 200
    assert progress.json()["linked_total"] == "1250.5000"
    assert progress.json()["expected_delta"] == "1250.5000"
    assert progress.json()["balanced"] is True

    done = await client.post(
        f"/api/v1/reconciliation/sessions/{sid}/complete",
        headers={"Idempotency-Key": "11111111-1111-7111-8111-111111111111"},
    )
    assert done.status_code == 200, done.text
    assert done.json()["status"] == "COMPLETED"

    # The split now reads back as reconciled, so the screen can stop offering it.
    ledger = (
        await client.get(
            f"/api/v1/accounts/{bank}/ledger",
            params={"start": "2026-10-01", "end": "2026-10-31"},
        )
    ).json()
    assert ledger["rows"][0]["reconciliation_status"] == "RECONCILED"

    # And a completed session refuses a second completion.
    again = await client.post(f"/api/v1/reconciliation/sessions/{sid}/complete")
    assert again.status_code == 409, again.text
    assert line["status"] in {"UNMATCHED", "SUGGESTED"}


@pytest.mark.asyncio
async def test_lines_can_be_filtered_by_the_account_being_reconciled(client) -> None:
    bank = await _account(client, "1020", "بانک")
    cash = await _account(client, "1010", "صندوق")
    await _import_lines(client, bank)
    await _import_lines(client, cash)

    r = await client.get("/api/v1/imports/lines", params={"account_id": bank})
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert all(row["account_id"] == bank for row in rows)
