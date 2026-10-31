"""Shared helpers for order tests after the v1.0.12 warehouse rule.

Since item 7 of the owner's change list, every order line must point at an
active PRODUCT/PCS warehouse item with stock — a free-text product is refused.
Tests therefore create the product first and reference it, instead of hard
coding a name.
"""

from __future__ import annotations

from decimal import Decimal


async def make_product(
    client,
    name: str = "محصول آزمون",
    *,
    quantity: str = "100",
    unit_price: str = "1000",
    unit_cost: str | None = None,
) -> dict:
    """Create a stocked PRODUCT/PCS item and return its read model."""
    payload = {
        "name": name,
        "kind": "PRODUCT",
        "unit": "PCS",
        "quantity": quantity,
        "unit_price": unit_price,
    }
    response = await client.post("/api/v1/warehouse/items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def order_payload(client, quantities=("2",), **line_fields) -> dict:
    """Build an order body whose lines reference real, stocked products."""
    items = []
    for index, quantity in enumerate(quantities):
        product = await make_product(
            client, name=f"محصول آزمون {index + 1}", quantity=str(Decimal(quantity) + 10)
        )
        items.append(
            {
                "product_name": product["name"],
                "variant": "plain",
                "quantity": quantity,
                "unit_price": line_fields.get("unit_price", "123.4567"),
                "unit_cost": line_fields.get("unit_cost", "23.4567"),
                "weight_g": line_fields.get("weight_g", "12.5"),
                "print_hours": line_fields.get("print_hours", "1"),
                "inventory_item_id": product["id"],
            }
        )
    return {
        "order_date": line_fields.get("order_date", "2026-10-16"),
        "customer_name": line_fields.get("customer_name", "مشتری آزمون"),
        "items": items,
    }


async def create_order(client, quantities=("2",), **line_fields) -> dict:
    payload = await order_payload(client, quantities, **line_fields)
    response = await client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()
