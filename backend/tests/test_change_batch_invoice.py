"""Item 11 — the «سند» is an invoice form; debit/credit stay behind the scenes.

The user fills date / seller / buyer / items and sees a total. The two balanced
splits are derived from the seeded chart of accounts, so the ledger invariants
(balanced, posted, immutable) still hold.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import text

CHART = {
    "1030": ("موجودی مواد و کالا", "ASSET"),
    "1040": ("حساب‌های دریافتنی", "ASSET"),
    "2010": ("حساب‌های پرداختنی", "LIABILITY"),
    "4010": ("درآمد فروش محصولات", "INCOME"),
}


async def seed_chart(client) -> None:
    """The invoice mapping needs the four accounts of the real seeded chart."""
    for code, (name, kind) in CHART.items():
        response = await client.post(
            "/api/v1/accounts",
            json={"code": code, "name": name, "account_type": kind},
        )
        assert response.status_code == 201, response.text


def sale_payload(**kw) -> dict:
    return {
        "kind": "sale",
        "transaction_date": "2026-10-20",
        "seller": "فروشگاه ویرا",
        "buyer": "آقای مشتری",
        "note": "تحویل حضوری",
        "lines": [
            {"title": "مجسمهٔ روباه", "quantity": "2", "unit_price": "1500000"},
            {"title": "جاکلیدی", "quantity": "3", "unit_price": "250000.5"},
        ],
        **kw,
    }


async def test_sale_invoice_posts_a_balanced_entry_without_debit_credit_input(client):
    await seed_chart(client)
    response = await client.post("/api/v1/journal-entries/invoice", json=sale_payload())
    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["total"]) == Decimal("3750001.5000")
    assert [line["title"] for line in body["lines"]] == ["مجسمهٔ روباه", "جاکلیدی"]
    assert [Decimal(line["line_total"]) for line in body["lines"]] == [
        Decimal("3000000"),
        Decimal("750001.5"),
    ]
    assert body["debit_account"].startswith("1040")
    assert body["credit_account"].startswith("4010")
    entry = body["entry"]
    assert entry["status"] == "POSTED"
    assert entry["payee"] == "آقای مشتری"
    assert len(entry["splits"]) == 2
    debit = sum(Decimal(s["debit"] or 0) for s in entry["splits"])
    credit = sum(Decimal(s["credit"] or 0) for s in entry["splits"])
    assert debit == credit == Decimal("3750001.5000")
    # the detail the user typed is preserved on the entry, not lost with the form
    assert entry["metadata"]["invoice"]["lines"][1]["title"] == "جاکلیدی"
    assert entry["metadata"]["invoice"]["seller"] == "فروشگاه ویرا"


async def test_purchase_invoice_uses_the_inventory_and_payable_accounts(client):
    await seed_chart(client)
    payload = sale_payload(
        kind="purchase",
        seller="تأمین‌کنندهٔ فیلامنت",
        buyer=None,
        lines=[{"title": "فیلامنت PLA", "quantity": "1000", "unit_price": "1200"}],
    )
    response = await client.post("/api/v1/journal-entries/invoice", json=payload)
    assert response.status_code == 201, response.text
    body = response.json()
    assert Decimal(body["total"]) == Decimal("1200000")
    assert body["debit_account"].startswith("1030")
    assert body["credit_account"].startswith("2010")
    assert body["entry"]["payee"] == "تأمین‌کنندهٔ فیلامنت"


async def test_invoice_without_lines_or_with_zero_total_is_refused(client):
    await seed_chart(client)
    response = await client.post("/api/v1/journal-entries/invoice", json=sale_payload(lines=[]))
    assert response.status_code == 422, response.text
    response = await client.post(
        "/api/v1/journal-entries/invoice",
        json=sale_payload(lines=[{"title": "صفر", "quantity": "1", "unit_price": "0"}]),
    )
    assert response.status_code == 400, response.text
    assert "بزرگ‌تر از صفر" in response.json()["detail"]
    assert (await client.get("/api/v1/journal-entries")).json() == []


async def test_missing_mapping_account_fails_with_a_persian_message(client, database):
    await seed_chart(client)
    with database.session() as session:
        session.execute(text("UPDATE accounts SET is_active = 0 WHERE code = '4010'"))
    response = await client.post("/api/v1/journal-entries/invoice", json=sale_payload())
    assert response.status_code == 400, response.text
    assert "4010" in response.json()["detail"]
    assert "درآمد فروش محصولات" in response.json()["detail"]
    assert (await client.get("/api/v1/journal-entries")).json() == []


async def test_sale_requires_a_buyer_and_purchase_requires_a_seller(client):
    await seed_chart(client)
    for payload in (
        sale_payload(buyer=None),
        sale_payload(kind="purchase", seller=None),
        sale_payload(buyer="   "),
    ):
        response = await client.post("/api/v1/journal-entries/invoice", json=payload)
        assert response.status_code == 422, response.text
    assert (await client.get("/api/v1/journal-entries")).json() == []


async def test_retried_invoice_with_same_idempotency_key_does_not_post_twice(client, database):
    import sqlite3

    """A double click or a network retry must not duplicate a paper invoice."""
    await seed_chart(client)
    headers = {"Idempotency-Key": "invoice-retry-1"}
    first = await client.post(
        "/api/v1/journal-entries/invoice", json=sale_payload(), headers=headers
    )
    assert first.status_code == 201, first.text
    second = await client.post(
        "/api/v1/journal-entries/invoice", json=sale_payload(), headers=headers
    )
    assert second.status_code == 201, second.text
    assert second.json()["entry"]["id"] == first.json()["entry"]["id"]
    assert second.json()["total"] == first.json()["total"]

    # Count on a short-lived read connection: holding a session open across
    # requests would keep a write lock and stall the next request.
    with sqlite3.connect(database.settings.sqlite_database_path) as conn:
        count = conn.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0]
    assert count == 1

    changed = await client.post(
        "/api/v1/journal-entries/invoice",
        json=sale_payload(buyer="شخص دیگر"),
        headers=headers,
    )
    assert changed.status_code == 409, changed.text
    assert changed.json()["code"] == "idempotency_key_reuse"


async def test_a_posted_invoice_can_be_corrected_without_debit_credit_input(client):
    """ویرایش سند: the owner fixes the invoice; the server re-derives the splits."""
    await seed_chart(client)
    created = (
        await client.post("/api/v1/journal-entries/invoice", json=sale_payload())
    ).json()
    entry_id = created["entry"]["id"]

    response = await client.put(
        f"/api/v1/journal-entries/{entry_id}/invoice",
        json={
            "kind": "sale",
            "transaction_date": "2026-10-21",
            "seller": "فروشگاه ویرا",
            "buyer": "آقای مشتری",
            "note": "اصلاح مبلغ",
            "lines": [{"title": "مجسمهٔ روباه", "quantity": "1", "unit_price": "2000000"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert Decimal(body["total"]) == Decimal("2000000.0000")
    assert body["entry"]["status"] == "POSTED"
    assert body["entry"]["transaction_date"] == "2026-10-21"
    assert body["entry"]["metadata"]["invoice"]["lines"][0]["title"] == "مجسمهٔ روباه"
    debit = sum(Decimal(s["debit"] or 0) for s in body["entry"]["splits"])
    credit = sum(Decimal(s["credit"] or 0) for s in body["entry"]["splits"])
    assert debit == credit == Decimal("2000000.0000")

    # The books carry the corrected amount once — nothing was double posted.
    income = await client.get(
        "/api/v1/reports/income-statement", params={"start": "2026-04-01", "end": "2026-12-31"}
    )
    assert income.status_code == 200
    body = income.json()
    assert Decimal(body["total_income"]) == Decimal("2000000.0000")
    entries = (await client.get("/api/v1/journal-entries")).json()
    assert len(entries) == 1


async def test_invoice_edit_refuses_a_hand_written_entry(client):
    await seed_chart(client)
    cash = (
        await client.post(
            "/api/v1/accounts", json={"code": "1010", "name": "صندوق", "account_type": "ASSET"}
        )
    ).json()
    equity = (
        await client.post(
            "/api/v1/accounts", json={"code": "3010", "name": "سرمایه", "account_type": "EQUITY"}
        )
    ).json()
    raw = (
        await client.post(
            "/api/v1/journal-entries",
            json={
                "transaction_date": "2026-10-20",
                "description": "سند دستی",
                "splits": [
                    {"account_id": cash["id"], "debit": "10.0000"},
                    {"account_id": equity["id"], "credit": "10.0000"},
                ],
            },
        )
    ).json()
    response = await client.put(
        f"/api/v1/journal-entries/{raw['id']}/invoice",
        json=sale_payload(),
    )
    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_a_registered_invoice_prints_with_the_logo_and_the_name(client):
    """فاکتور فروش: the printed document carries the mark and the amount in Tomans."""
    await seed_chart(client)
    created = (await client.post("/api/v1/journal-entries/invoice", json=sale_payload())).json()
    entry_id = created["entry"]["id"]

    response = await client.get(f"/api/v1/journal-entries/{entry_id}/invoice.pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] in ("application/pdf", "text/html; charset=utf-8")
    assert "attachment" not in response.headers["content-disposition"]
    if response.headers["content-type"].startswith("text/html"):
        html = response.text
        assert '<img class="brand-logo" src="data:image/png;base64,' in html
        assert '<div class="brand-name">V.I.R.A</div>' in html
        assert "فاکتور فروش" in html
        assert "آقای مشتری" in html
        # 3,750,001.5 Rial is printed as 375,000.15 Toman (÷10 exactly once)
        assert "۳۷۵٬۰۰۰٫۱۵" in html
        assert "مجسمهٔ روباه" in html
        # a posted invoice says nothing alarming
        assert "ابطال شده" not in html


async def test_a_hand_written_entry_has_no_invoice_document(client):
    await seed_chart(client)
    cash = (
        await client.post(
            "/api/v1/accounts", json={"code": "1010", "name": "صندوق", "account_type": "ASSET"}
        )
    ).json()
    equity = (
        await client.post(
            "/api/v1/accounts", json={"code": "3010", "name": "سرمایه", "account_type": "EQUITY"}
        )
    ).json()
    raw = (
        await client.post(
            "/api/v1/journal-entries",
            json={
                "transaction_date": "2026-10-20",
                "description": "سند دستی",
                "splits": [
                    {"account_id": cash["id"], "debit": "10.0000"},
                    {"account_id": equity["id"], "credit": "10.0000"},
                ],
            },
        )
    ).json()
    response = await client.get(f"/api/v1/journal-entries/{raw['id']}/invoice.pdf")
    assert response.status_code == 400
    assert "فاکتور" in response.json()["detail"]
