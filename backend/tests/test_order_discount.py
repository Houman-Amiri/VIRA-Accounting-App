"""Order-level fixed and percentage discounts and invoice/report consistency."""
from decimal import Decimal

import pytest

from tests.order_helpers import order_payload


async def sample_order(client, *, kind="AMOUNT", value="0"):
    variable = await client.post("/api/v1/settings/pricing/variables", json={
        "name": "طراحی", "basis": "AMOUNT", "scope": "PER_UNIT",
        "value": "10000", "is_design_rate": True,
    })
    assert variable.status_code == 201
    payload = await order_payload(client, quantities=("2",), unit_price="100000", unit_cost="40000")
    payload["items"][0]["charges"] = [{"kind": "DESIGN", "hours": "5"}]
    payload["discount_type"] = kind
    payload["discount_value"] = value
    return await client.post("/api/v1/orders", json=payload), payload


@pytest.mark.asyncio
async def test_discount_fixed_then_percent_applies_to_charges_and_sales(client, app, monkeypatch):
    def no_pdf(*_args, **_kwargs):
        raise RuntimeError("HTML fallback")
    monkeypatch.setattr(app.state, "pdf_renderer", no_pdf)
    response, _payload = await sample_order(client, value="50000")
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["discount_type"] == "AMOUNT"
    assert Decimal(order["discount_value"]) == 50000
    assert Decimal(order["discount_amount"]) == 50000
    assert Decimal(order["total"]) == 200000  # 2 × 100000 + 50000 design - 50000
    assert Decimal(order["profit"]) == 120000
    report = await client.get("/api/v1/orders/reports/sales?period=daily&date_from=2026-10-16&date_to=2026-10-16")
    assert Decimal(report.json()["revenue"]) == 200000
    assert Decimal(report.json()["profit"]) == 120000

    response = await client.patch(f"/api/v1/orders/{order['id']}", json={
        "version_id": order["version_id"], "discount_type": "PERCENT", "discount_value": "10"
    })
    assert response.status_code == 200, response.text
    order = response.json()
    assert Decimal(order["discount_amount"]) == 25000
    assert Decimal(order["total"]) == 225000
    pdf = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
    assert "تخفیف (۱۰٪)" in pdf.text
    assert "۲۵٬۰۰۰" in pdf.text
    assert "۲۲۵٬۰۰۰" in pdf.text
    report = await client.get("/api/v1/orders/reports/sales?period=daily&date_from=2026-10-16&date_to=2026-10-16")
    assert Decimal(report.json()["revenue"]) == 225000
    assert Decimal(report.json()["profit"]) == 145000

    # Omitted fields on unrelated updates preserve the original type and value.
    saved = await client.patch(f"/api/v1/orders/{order['id']}", json={
        "version_id": order["version_id"], "customer_name": "نام جدید"
    })
    assert saved.status_code == 200
    assert Decimal(saved.json()["discount_value"]) == 10
    assert Decimal(saved.json()["total"]) == 225000


@pytest.mark.asyncio
async def test_invalid_discounts_do_not_save_and_rollback_edits(client):
    response, payload = await sample_order(client, value="50000")
    assert response.status_code == 201, response.text
    order = response.json()
    for kind, value in [("PERCENT", "100.0001"), ("AMOUNT", "250001"), ("AMOUNT", "-1")]:
        invalid = await client.patch(f"/api/v1/orders/{order['id']}", json={
            "version_id": order["version_id"], "discount_type": kind, "discount_value": value
        })
        assert invalid.status_code in (400, 422), invalid.text
        current = (await client.get(f"/api/v1/orders/{order['id']}")).json()
        assert current["version_id"] == order["version_id"]
        assert Decimal(current["total"]) == 200000

    # Reducing line prices below an existing fixed discount is rejected atomically.
    payload["items"][0]["unit_price"] = "1000"
    payload["items"][0]["charges"] = []
    invalid = await client.patch(f"/api/v1/orders/{order['id']}", json={
        "version_id": order["version_id"], "items": payload["items"]
    })
    assert invalid.status_code == 400, invalid.text
    current = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert Decimal(current["total"]) == 200000
    assert len(current["items"][0]["charges"]) == 1


@pytest.mark.asyncio
async def test_no_discount_default_and_full_percent(client):
    payload = await order_payload(client, quantities=("2",), unit_price="1000", unit_cost="400")
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    order = response.json()
    assert order["discount_type"] == "AMOUNT"
    assert Decimal(order["discount_value"]) == 0
    assert Decimal(order["discount_amount"]) == 0
    assert Decimal(order["total"]) == 2000
    updated = await client.patch(f"/api/v1/orders/{order['id']}", json={
        "version_id": order["version_id"], "discount_type": "PERCENT", "discount_value": "100"
    })
    assert updated.status_code == 200
    assert Decimal(updated.json()["discount_amount"]) == 2000
    assert Decimal(updated.json()["total"]) == 0
    assert Decimal(updated.json()["profit"]) == -800


@pytest.mark.asyncio
async def test_discount_percentage_rounds_to_four_places(client):
    payload = await order_payload(client, quantities=("1",), unit_price="10.1234")
    payload.update(discount_type="PERCENT", discount_value="12.5")
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    assert Decimal(response.json()["discount_amount"]) == Decimal("1.2654")
    assert Decimal(response.json()["total"]) == Decimal("8.8580")


@pytest.mark.asyncio
async def test_invalid_discounts_fail_on_create_and_leave_no_order(client):
    payload = await order_payload(client, quantities=("1",), unit_price="1000")
    for kind, value in [("PERCENT", "101"), ("AMOUNT", "1001")]:
        payload.update(discount_type=kind, discount_value=value)
        response = await client.post("/api/v1/orders", json=payload)
        assert response.status_code == 400, response.text
    assert (await client.get("/api/v1/orders")).json() == []


@pytest.mark.asyncio
async def test_fractional_subtotal_and_percentage_round_once(client):
    payload = await order_payload(client, quantities=("0.3333",), unit_price="100.1111", unit_cost="0")
    payload.update(discount_type="PERCENT", discount_value="100")
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    order = response.json()
    assert Decimal(order["discount_amount"]) == Decimal("33.3670")
    assert Decimal(order["total"]) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("discount_type", "discount_value", "expected_discount", "expected_total"),
    [("AMOUNT", "50000", "۵۰٬۰۰۰", "۲۰۰٬۰۰۰"),
     ("PERCENT", "10", "۲۵٬۰۰۰", "۲۲۵٬۰۰۰"),
     ("AMOUNT", "0", "۰", "۲۵۰٬۰۰۰")],
)
async def test_invoice_displays_full_pre_discount_total_above_discount(
    client, app, monkeypatch, discount_type, discount_value, expected_discount, expected_total
):
    def no_pdf(*_args, **_kwargs):
        raise RuntimeError("use printable HTML")

    monkeypatch.setattr(app.state, "pdf_renderer", no_pdf)
    response, _ = await sample_order(client, kind=discount_type, value=discount_value)
    assert response.status_code == 201, response.text
    html = (await client.get(f"/api/v1/orders/{response.json()['id']}/proforma.pdf")).text
    totals = html[html.index('<table class="totals">'):]
    assert '<td>جمع اقلام</td><td class="num">۲۰۰٬۰۰۰</td>' in totals
    assert '<td>هزینهٔ طراحی و متغیرها</td><td class="num">۵۰٬۰۰۰</td>' in totals
    expected_row = '<tr><td>جمع کل پیش از تخفیف (تومان)</td><td class="num">۲۵۰٬۰۰۰</td></tr>'
    assert expected_row in totals
    assert totals.index(expected_row) < totals.index('<tr><td>تخفیف')
    assert f'<td class="num">{expected_discount}</td></tr>' in totals
    assert f'<td>مبلغ قابل پرداخت (تومان)</td><td class="num">{expected_total}</td>' in totals


@pytest.mark.asyncio
async def test_invoice_pre_discount_total_without_charges_uses_rounded_subtotal(client, app, monkeypatch):
    def no_pdf(*_args, **_kwargs):
        raise RuntimeError("use printable HTML")

    monkeypatch.setattr(app.state, "pdf_renderer", no_pdf)
    payload = await order_payload(client, quantities=("0.3333",), unit_price="100.1111")
    payload.update(discount_type="PERCENT", discount_value="100")
    created = await client.post("/api/v1/orders", json=payload)
    assert created.status_code == 201, created.text
    order = created.json()
    assert Decimal(order["total_cost"]) == Decimal("7.8181")
    assert Decimal(order["profit"]) == Decimal("-7.8181")
    report = await client.get("/api/v1/orders/reports/sales?period=daily&date_from=2026-10-16&date_to=2026-10-16")
    assert Decimal(report.json()["cost"]) == Decimal("7.8181")
    assert Decimal(report.json()["profit"]) == Decimal("-7.8181")
    response = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
    totals = response.text[response.text.index('<table class="totals">'):]
    assert "هزینهٔ طراحی و متغیرها" not in totals
    assert '<td>جمع کل پیش از تخفیف (تومان)</td><td class="num">۳۳٫۳۶۷</td>' in totals
    assert '<td>تخفیف (۱۰۰٪)</td><td class="num">۳۳٫۳۶۷</td>' in totals
    assert '<td>مبلغ قابل پرداخت (تومان)</td><td class="num">۰</td>' in totals
