"""«هزینهٔ طراحی» and the owner's variables on individual order lines.

The owner types design hours next to the unit price; the server multiplies them
by the variable he marked as the design rate in Settings and stores both the
hours and the rate it used, so an old proforma never changes when the rate does.
Leaving the field empty must price the order exactly as before.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.pricing import PricingVariable
from tests.order_helpers import create_order, make_product, order_payload

VARIABLES = "/api/v1/settings/pricing/variables"


async def _design_variable(client, value: str = "50000") -> dict:
    response = await client.post(
        VARIABLES,
        json={
            "name": "هزینه طراحی",
            "scope": "PER_UNIT",
            "basis": "AMOUNT",
            "value": value,
            "is_design_rate": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_only_one_variable_can_be_the_design_rate(client, database) -> None:
    first = await _design_variable(client)
    assert first["is_design_rate"] is True

    second = await client.post(
        VARIABLES,
        json={
            "name": "طراحی دوم",
            "scope": "PER_UNIT",
            "basis": "AMOUNT",
            "value": "70000",
            "is_design_rate": True,
        },
    )
    assert second.status_code == 201, second.text

    listed = (await client.get(VARIABLES)).json()
    flags = {row["name"]: row["is_design_rate"] for row in listed}
    assert flags == {"هزینه طراحی": False, "طراحی دوم": True}

    with database.session() as session:
        stored = session.execute(
            text("SELECT count(*) FROM pricing_variables WHERE is_design_rate = 1")
        ).scalar_one()
        assert stored == 1


@pytest.mark.asyncio
async def test_a_percent_variable_cannot_be_the_design_rate(client) -> None:
    response = await client.post(
        VARIABLES,
        json={
            "name": "درصد طراحی",
            "scope": "PER_UNIT",
            "basis": "PERCENT_OF_COST",
            "value": "12",
            "is_design_rate": True,
        },
    )
    assert response.status_code >= 400
    assert "مبلغ" in response.json()["detail"]


@pytest.mark.asyncio
async def test_design_hours_add_money_and_a_snapshot_to_the_line(client) -> None:
    await _design_variable(client, "50000")
    product = await make_product(client, unit_price="1000")
    payload = {
        "order_date": "2026-10-16",
        "customer_name": "مشتری طراحی",
        "items": [
            {
                "product_name": product["name"],
                "variant": "plain",
                "quantity": "2",
                "unit_price": "1000",
                "unit_cost": "400",
                "inventory_item_id": product["id"],
                "charges": [{"kind": "DESIGN", "hours": "3"}],
            }
        ],
    }
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    order = response.json()

    charge = order["items"][0]["charges"][0]
    assert charge["kind"] == "DESIGN"
    assert charge["name"] == "هزینه طراحی"
    assert Decimal(charge["hours"]) == Decimal("3")
    assert Decimal(charge["rate"]) == Decimal("50000")
    assert Decimal(charge["amount"]) == Decimal("150000")
    # ۲ × ۱۰۰۰ + ۱۵۰٬۰۰۰ طراحی
    assert Decimal(order["total"]) == Decimal("152000")
    assert Decimal(order["items"][0]["charges_total"]) == Decimal("150000")

    # The saved rate is a snapshot: raising the Settings rate changes nothing.
    variables = (await client.get(VARIABLES)).json()
    await client.patch(
        f"{VARIABLES}/{variables[0]['id']}", json={"value": "90000"}
    )
    again = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert Decimal(again["items"][0]["charges"][0]["rate"]) == Decimal("50000")
    assert Decimal(again["total"]) == Decimal("152000")


@pytest.mark.asyncio
async def test_an_empty_design_field_prices_exactly_as_before(client) -> None:
    await _design_variable(client)
    plain = await create_order(client, quantities=("2",))
    with_blank = await order_payload(client, quantities=("2",))
    with_blank["items"][0]["charges"] = [{"kind": "DESIGN", "hours": "0"}]
    response = await client.post("/api/v1/orders", json=with_blank)
    assert response.status_code == 201, response.text
    assert with_blank["items"][0]["quantity"] == "2"
    assert Decimal(response.json()["total"]) == Decimal(plain["total"])
    assert response.json()["items"][0]["charges"] == []


@pytest.mark.asyncio
async def test_design_hours_without_a_rate_are_refused_with_a_hint(client) -> None:
    product = await make_product(client)
    payload = {
        "order_date": "2026-10-16",
        "customer_name": "بدون نرخ",
        "items": [
            {
                "product_name": product["name"],
                "variant": "plain",
                "quantity": "1",
                "unit_price": "1000",
                "unit_cost": "400",
                "inventory_item_id": product["id"],
                "charges": [{"kind": "DESIGN", "hours": "2"}],
            }
        ],
    }
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code >= 400
    assert "نرخ" in response.json()["detail"]


@pytest.mark.asyncio
async def test_a_variable_picked_for_the_line_is_stored_by_name(client) -> None:
    variable = await client.post(
        VARIABLES,
        json={"name": "اجرت پرسنل", "scope": "PER_UNIT", "value": "1000"},
    )
    variable_id = variable.json()["id"]
    product = await make_product(client, unit_price="1000")
    payload = {
        "order_date": "2026-10-16",
        "customer_name": "متغیر روی ردیف",
        "items": [
            {
                "product_name": product["name"],
                "variant": "plain",
                "quantity": "1",
                "unit_price": "1000",
                "unit_cost": "400",
                "inventory_item_id": product["id"],
                "charges": [
                    {"kind": "VARIABLE", "variable_id": variable_id, "amount": "25000"}
                ],
            }
        ],
    }
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    order = response.json()
    charge = order["items"][0]["charges"][0]
    assert charge["kind"] == "VARIABLE"
    assert charge["name"] == "اجرت پرسنل"
    assert Decimal(charge["amount"]) == Decimal("25000")
    assert Decimal(order["total"]) == Decimal("26000")

    # Deleting the settings row keeps the invoice readable (name + amount stay).
    await client.delete(f"{VARIABLES}/{variable_id}")
    again = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert again["items"][0]["charges"][0]["variable_id"] is None
    assert again["items"][0]["charges"][0]["name"] == "اجرت پرسنل"


@pytest.mark.asyncio
async def test_the_proforma_prints_design_cost_on_its_own_row(client) -> None:
    await _design_variable(client, "50000")
    product = await make_product(client, unit_price="1000")
    created = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-16",
            "customer_name": "پیش‌فاکتور طراحی",
            "items": [
                {
                    "product_name": product["name"],
                    "variant": "plain",
                    "quantity": "2",
                    "unit_price": "1000",
                    "unit_cost": "400",
                    "inventory_item_id": product["id"],
                    "charges": [{"kind": "DESIGN", "hours": "3"}],
                }
            ],
        },
    )
    order_id = created.json()["id"]
    response = await client.get(f"/api/v1/orders/{order_id}/proforma.pdf")
    assert response.status_code == 200
    body = response.text
    assert "هزینه طراحی" in body
    assert "۳ ساعت" in body
    assert "هزینهٔ طراحی و متغیرها" in body
    assert "۱۵۰٬۰۰۰" in body


@pytest.mark.asyncio
async def test_the_design_rate_flag_survives_a_rename(client, database) -> None:
    created = await _design_variable(client, "50000")
    patched = await client.patch(
        f"{VARIABLES}/{created['id']}",
        json={"name": "نرخ طراحی مدل", "is_design_rate": True},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["is_design_rate"] is True
    with database.session() as session:
        row = session.get(PricingVariable, created["id"])
        assert row is not None and row.is_design_rate == 1
