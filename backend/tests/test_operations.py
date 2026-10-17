"""Operations domain (MASTER_PROMPT §3.1–§3.3) — warehouse, orders, production.

Covers the mandated behaviours: stockout alarms, supplier suggestion by
price/quality/delivery score, stock never going negative, production consuming
filament and yielding products, sales reports, and the proforma document.
"""

from __future__ import annotations

import os
from decimal import Decimal

from sqlalchemy import text


# ------------------------------------------------------------------ fixtures ---
async def _supplier(client, name: str, price: int, quality: int, delivery: int) -> dict:
    resp = await client.post(
        "/api/v1/warehouse/suppliers",
        json={
            "name": name,
            "address": "تهران",
            "phone": "021000000",
            "score_price": price,
            "score_quality": quality,
            "score_delivery": delivery,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _item(client, name: str, **kw) -> dict:
    payload = {
        "name": name,
        "kind": kw.pop("kind", "FILAMENT"),
        "unit": kw.pop("unit", "G"),
        "quantity": kw.pop("quantity", "1000"),
        "min_quantity": kw.pop("min_quantity", "200"),
        "unit_price": kw.pop("unit_price", "700"),
        **kw,
    }
    resp = await client.post("/api/v1/warehouse/items", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ----------------------------------------------------------------- suppliers ---
async def test_supplier_crud_scores_and_suggestion(client) -> None:
    weak = await _supplier(client, "پلاستیک ارزان", 90, 40, 30)  # mean 53.3
    strong = await _supplier(client, "فیلامنت برتر", 70, 95, 90)  # mean 85
    assert strong["score"] == 85.0
    assert weak["score"] == 53.3

    resp = await client.get("/api/v1/warehouse/suppliers/suggestions")
    assert resp.status_code == 200
    assert [s["name"] for s in resp.json()][0] == "فیلامنت برتر"

    # duplicate name is a 409 problem+json, not a 500
    dup = await client.post("/api/v1/warehouse/suppliers", json={"name": "فیلامنت برتر"})
    assert dup.status_code == 409
    assert dup.json()["code"] == "duplicate_entity"

    # optimistic locking
    stale = await client.patch(
        f"/api/v1/warehouse/suppliers/{strong['id']}",
        json={"version_id": 99, "notes": "x"},
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"


# ----------------------------------------------------------------- inventory ---
async def test_inventory_crud_alarm_and_movements(client) -> None:
    supplier = await _supplier(client, "تأمین‌کنندهٔ الف", 80, 80, 80)
    item = await _item(
        client, "فیلامنت PLA سفید", color="سفید", supplier_id=supplier["id"], quantity="500"
    )
    assert item["supplier_name"] == "تأمین‌کنندهٔ الف"
    assert Decimal(item["quantity"]) == Decimal("500")
    assert Decimal(item["value"]) == Decimal("350000")  # 500 g × 700
    assert item["low_stock"] is False

    # take stock out → crosses the minimum → alarm appears
    out = await client.post(
        f"/api/v1/warehouse/items/{item['id']}/movements",
        json={"kind": "OUT", "quantity": "350", "reason": "production"},
    )
    assert out.status_code == 201, out.text
    alarms = await client.get("/api/v1/warehouse/alarms")
    assert alarms.status_code == 200
    body = alarms.json()
    assert [a["name"] for a in body] == ["فیلامنت PLA سفید"]
    assert body[0]["suggested_supplier"] == "تأمین‌کنندهٔ الف"
    assert Decimal(body[0]["quantity"]) == Decimal("150")

    # stock can never go negative
    too_much = await client.post(
        f"/api/v1/warehouse/items/{item['id']}/movements",
        json={"kind": "OUT", "quantity": "10000"},
    )
    assert too_much.status_code == 409
    assert too_much.json()["code"] == "insufficient_stock"

    # a zeroed ADJUST is allowed (physical count) and appends to the ledger
    adjust = await client.post(
        f"/api/v1/warehouse/items/{item['id']}/movements",
        json={"kind": "ADJUST", "quantity": "0", "note": "شمارش انبار"},
    )
    assert adjust.status_code == 201, adjust.text
    items = await client.get("/api/v1/warehouse/items")
    assert Decimal(items.json()[0]["quantity"]) == Decimal("0")


async def test_movements_are_append_only(client, database) -> None:
    await _item(client, "فیلامنت ABS مشکی", quantity="100")
    rows = await client.get("/api/v1/warehouse/movements")
    assert len(rows.json()) == 1
    movement_id = rows.json()[0]["id"]
    with database.session() as session:
        try:
            session.execute(
                text("UPDATE stock_movements SET note='tampered' WHERE id=:i"),
                {"i": movement_id},
            )
            session.commit()
            raise AssertionError("UPDATE on stock_movements must be rejected")
        except Exception as exc:  # noqa: BLE001 - SQLite trigger aborts
            assert "append-only" in str(exc)
            session.rollback()


async def test_inventory_summary_counts_kinds(client) -> None:
    await _item(client, "فیلامنت PLA", quantity="100", min_quantity="100")  # low
    await _item(
        client,
        "مجسمهٔ روباه",
        kind="PRODUCT",
        unit="PCS",
        quantity="5",
        min_quantity="0",
        unit_price="450000",
    )
    resp = await client.get("/api/v1/warehouse/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["filament_count"] == 1
    assert body["product_count"] == 1
    assert body["low_stock_count"] == 1
    assert Decimal(body["total_value"]) == Decimal("100") * 700 + Decimal("5") * 450000


# -------------------------------------------------------------------- orders ---
async def _order(client, **kw) -> dict:
    payload = {
        "order_date": "2026-10-15",
        "customer_name": "مشتری نمونه",
        "customer_phone": "09120000000",
        "customer_address": "تهران، خیابان نمونه",
        "channel": "marketplace",
        "items": [
            {
                "product_name": "مجسمهٔ روباه",
                "variant": "chain",
                "quantity": "2",
                "unit_price": "2760748.5",
                "unit_cost": "834000",
                "weight_g": "240",
                "print_hours": "10",
            }
        ],
        **kw,
    }
    resp = await client.post("/api/v1/orders", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_order_lifecycle_totals_and_sales_report(client) -> None:
    order = await _order(client)
    assert order["order_number"] == 1
    assert Decimal(order["total"]) == Decimal("5521497.0")  # 2 × 2 760 748.5
    assert Decimal(order["total_cost"]) == Decimal("1668000")
    assert Decimal(order["profit"]) == Decimal("3853497.0")

    patched = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"version_id": order["version_id"], "status": "CONFIRMED"},
    )
    assert patched.status_code == 200
    assert patched.json()["status"] == "CONFIRMED"

    # update with items replaces the line set and bumps the version
    replaced = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={
            "version_id": patched.json()["version_id"],
            "items": [
                {
                    "product_name": "مجسمهٔ روباه",
                    "variant": "plain",
                    "quantity": "1",
                    "unit_price": "2760748.5",
                    "unit_cost": "834000",
                }
            ],
        },
    )
    assert replaced.status_code == 200
    assert Decimal(replaced.json()["total"]) == Decimal("2760748.5")

    report = await client.get("/api/v1/orders/reports/sales?period=monthly")
    assert report.status_code == 200
    body = report.json()
    assert body["orders"] == 1
    assert Decimal(body["revenue"]) == Decimal("2760748.5")
    assert body["rows"][0]["period"] == "2026-10"
    assert Decimal(body["profit"]) == Decimal("1926748.5")

    search = await client.get("/api/v1/orders?search=نمونه&status=CONFIRMED")
    assert search.status_code == 200 and len(search.json()) == 1
    empty = await client.get("/api/v1/orders?search=ناموجود")
    assert empty.json() == []


async def test_proforma_document_renders(client, pdf_inspector) -> None:
    order = await _order(client)
    resp = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] in ("application/pdf", "text/html; charset=utf-8")
    if os.environ.get("VIRA_REQUIRE_NATIVE_PDF") == "1":
        assert resp.headers["content-type"] == "application/pdf", "HTML fallback is NOT native PDF evidence"
    if resp.headers["content-type"].startswith("application/pdf"):
        proof = pdf_inspector(resp.content, expected_digits="۲۷۶۰۴۸۵")
        assert proof["pages"] == 1
    else:  # WeasyPrint unavailable on this host → printable HTML fallback
        html = resp.text
        assert html.count("data:font/ttf;base64,") == 2
        assert "پیش‌فاکتور فروش" in html
        assert "مجسمهٔ روباه (حلقه و زنجیر)" in html
        assert "۲٬۷۶۰٬۷۴۸٫۵" in html  # Persian-grouped money


# ---------------------------------------------------------------- production ---
async def test_production_consumes_filament_and_yields_products(client) -> None:
    filament = await _item(client, "فیلامنت PETG سبز", quantity="1000", min_quantity="100")
    product = await _item(
        client, "مجسمهٔ گربه", kind="PRODUCT", unit="PCS", quantity="0", unit_price="1500000"
    )
    order = await _order(client, items=[{"product_name": "مجسمهٔ گربه", "quantity": "3", "unit_price": "2760748.5", "unit_cost": "1200000"}])

    job = await client.post(
        "/api/v1/production/jobs",
        json={
            "product_name": "مجسمهٔ گربه",
            "quantity": "3",
            "variant": "plain",
            "channel": "marketplace",
            "order_id": order["id"],
            "order_item_id": order["items"][0]["id"],
            "filament_item_id": filament["id"],
            "product_item_id": product["id"],
            "filament_grams": "120",
            "print_hours": "6",
            "unit_cost": "1200000",
            "unit_price": "2760748.5",
        },
    )
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    assert job.json()["status"] == "PLANNED"
    assert job.json()["order_number"] == order["order_number"]

    started = await client.post(f"/api/v1/production/jobs/{job_id}/start")
    assert started.json()["status"] == "IN_PROGRESS"
    order_after_start = await client.get(f"/api/v1/orders/{order['id']}")
    assert order_after_start.json()["status"] == "IN_PRODUCTION"

    finished = await client.post(f"/api/v1/production/jobs/{job_id}/finish")
    assert finished.status_code == 200, finished.text
    assert finished.json()["status"] == "DONE"
    assert finished.json()["finished_at"]

    # 1000 − 3×120 = 640 g left; 3 produced models in stock
    items = {i["name"]: i for i in (await client.get("/api/v1/warehouse/items")).json()}
    assert Decimal(items["فیلامنت PETG سبز"]["quantity"]) == Decimal("640")
    assert Decimal(items["مجسمهٔ گربه"]["quantity"]) == Decimal("3")
    assert items["فیلامنت PETG سبز"]["low_stock"] is False

    # the order flips to READY once every job is done
    assert (await client.get(f"/api/v1/orders/{order['id']}")).json()["status"] == "READY"

    # finishing twice is refused
    again = await client.post(f"/api/v1/production/jobs/{job_id}/finish")
    assert again.status_code == 409
    assert again.json()["code"] == "invalid_operations_state"

    summary = await client.get("/api/v1/production/summary")
    assert summary.json()["done"] == 1

    # movement ledger records both sides
    kinds = [(m["kind"], Decimal(m["quantity"])) for m in
             (await client.get("/api/v1/warehouse/movements")).json()]
    assert ("OUT", Decimal("360")) in kinds
    assert ("IN", Decimal("3")) in kinds


async def test_production_refuses_insufficient_filament(client) -> None:
    filament = await _item(client, "فیلامنت کمیاب", quantity="50", min_quantity="10")
    product = await _item(client, "محصول مقصد", kind="PRODUCT", unit="PCS", quantity="0")
    job = await client.post(
        "/api/v1/production/jobs",
        json={
            "product_name": "قطعهٔ بزرگ",
            "quantity": "10",
            "product_item_id": product["id"],
            "filament_item_id": filament["id"],
            "filament_grams": "40",
        },
    )
    assert job.status_code == 201
    resp = await client.post(f"/api/v1/production/jobs/{job.json()['id']}/finish")
    assert resp.status_code == 409
    assert resp.json()["code"] == "insufficient_stock"
    # the failed job stays open and stock is untouched
    items = (await client.get("/api/v1/warehouse/items")).json()
    assert Decimal(items[0]["quantity"]) == Decimal("50")
    assert (await client.get(f"/api/v1/production/jobs/{job.json()['id']}")).json()[
        "status"
    ] != "DONE"


async def test_dashboard_counts_and_sales_are_not_truncated(client, session) -> None:
    """Recent-orders is a page; counts and revenue must include ALL matching orders."""
    from sqlalchemy import insert

    from app.models import Order, OrderItem

    orders = [
        dict(
            id=f"dashboard-{i}",
            order_number=i + 1,
            order_date="2026-10-16",
            customer_name="dashboard fixture",
            status="NEW" if i < 10001 else "CANCELLED",
            channel="direct",
            created_at="2026-10-16T00:00:00Z",
            updated_at="2026-10-16T00:00:00Z",
        )
        for i in range(10002)
    ]
    session.execute(insert(Order), orders)
    session.execute(
        insert(OrderItem),
        [
            dict(
                id=f"dashboard-line-{i}",
                order_id=o["id"],
                position=0,
                product_name="fixture",
                variant="plain",
                quantity=Decimal("2"),
                unit_price=Decimal("12.3401"),
                unit_cost=Decimal("3.0001"),
                weight_g=Decimal("1"),
                print_hours=Decimal("1"),
            )
            for i, o in enumerate(orders)
        ],
    )
    session.commit()
    recent = await client.get("/api/v1/orders")
    assert recent.status_code == 200
    assert len(recent.json()) == 200
    summary = await client.get("/api/v1/orders/summary")
    assert summary.status_code == 200
    assert summary.json() == dict(
        total=10002,
        new=10001,
        confirmed=0,
        in_production=0,
        ready=0,
        delivered=0,
        shipped=0,
        cancelled=1,
    )
    response = await client.get(
        "/api/v1/orders/reports/sales",
        params={
            "period": "daily",
            "date_from": "2026-10-16",
            "date_to": "2026-10-16",
        },
    )
    assert response.status_code == 200
    report = response.json()
    assert report["orders"] == 10001
    assert Decimal(report["revenue"]) == Decimal("246826.6802")
    assert Decimal(report["profit"]) == Decimal("186818.6800")


async def test_dashboard_production_counts_and_active_sample_are_not_truncated(
    client, session
) -> None:
    from sqlalchemy import insert

    from app.models import ProductionJob

    session.execute(
        insert(ProductionJob),
        [
            dict(
                id=f"dashboard-job-{i}",
                job_number=i + 1,
                product_name="fixture",
                status="PLANNED" if i == 0 else "IN_PROGRESS" if i == 1 else "DONE",
                quantity=Decimal("2.5"),
                filament_grams=Decimal("10.1"),
                created_at="2026-01-01" if i < 2 else "2026-10-16",
                updated_at="2026-10-16",
            )
            for i in range(10002)
        ],
    )
    session.commit()
    response = await client.get("/api/v1/production/summary")
    assert response.status_code == 200
    summary = response.json()
    assert (summary["planned"], summary["in_progress"], summary["done"]) == (1, 1, 10000)
    assert Decimal(summary["filament_grams_planned"]) == Decimal("50.5")
    assert len(summary["jobs"]) == 200
    assert [j["status"] for j in summary["jobs"][:2]] == ["PLANNED", "IN_PROGRESS"]


async def test_dashboard_inventory_value_includes_items_beyond_recent_page(client, session) -> None:
    from sqlalchemy import insert

    from app.models import InventoryItem

    session.execute(insert(InventoryItem), [dict(
        id=f"dashboard-stock-{i}", name=f"fixture-{i:04d}",
        kind="FILAMENT" if i != 500 else "PRODUCT", unit="G" if i != 500 else "PCS",
        quantity=Decimal("1") if i != 500 else Decimal("3"),
        unit_price=Decimal("0.0001") if i != 500 else Decimal("123.4567"),
        min_quantity=Decimal("0") if i != 500 else Decimal("4"),
        is_active=1 if i < 501 else 0,
        created_at="2026-10-16", updated_at="2026-10-16",
    ) for i in range(502)])
    session.commit()
    page = await client.get("/api/v1/warehouse/items")
    assert page.status_code == 200
    assert len(page.json()) == 500
    response = await client.get("/api/v1/warehouse/summary")
    assert response.status_code == 200
    summary = response.json()
    assert summary["filament_count"] == 500
    assert summary["product_count"] == 1
    assert summary["low_stock_count"] == 1
    assert len(summary["items"]) == 501
    assert Decimal(summary["total_value"]) == Decimal("370.4201")
