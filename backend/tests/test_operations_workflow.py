"""Phase 7: complete and failure-path proofs on isolated on-disk SQLite."""

from decimal import Decimal

import pytest

from app.services.errors import DomainError
from app.services.operations import OperationsService


async def post(client, path, **data):
    response = await client.post("/api/v1/" + path, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def setup_stock(client, quantity="1000"):
    filament = await post(
        client,
        "warehouse/items",
        name="فیلامنت آزمون",
        kind="FILAMENT",
        unit="G",
        quantity=quantity,
        unit_price="100",
    )
    product = await post(
        client, "warehouse/items", name="محصول آزمون", kind="PRODUCT", unit="PCS", quantity="0"
    )
    return filament, product


async def setup_order(client, quantities=("2", "1")):
    """Order lines reference real warehouse products (item 7 of the change list)."""
    items = []
    for i, q in enumerate(quantities):
        product = await post(
            client,
            "warehouse/items",
            name=f"قلم {i}",
            kind="PRODUCT",
            unit="PCS",
            quantity=q,
            unit_price="500",
        )
        items.append(
            dict(
                product_name=f"قلم {i}",
                quantity=q,
                unit_price="123.4567",
                unit_cost="23.4567",
                weight_g="12.5",
                print_hours="1",
                inventory_item_id=product["id"],
            )
        )
    return await post(
        client,
        "orders",
        order_date="2026-10-16",
        customer_name="مشتری آزمون",
        items=items,
    )


def payload(filament, product, **kw):
    return dict(
        product_name="آزمون",
        quantity="1",
        filament_item_id=filament["id"],
        product_item_id=product["id"],
        filament_grams="12.5",
        **kw,
    )


async def get_item(client, id):
    return next(
        i for i in (await client.get("/api/v1/warehouse/summary")).json()["items"] if i["id"] == id
    )


async def test_partial_multiline_order_only_ready_after_every_line(client):
    filament, product = await setup_stock(client)
    order = await setup_order(client)
    jobs = []
    for line in [order["items"][0], order["items"][1], order["items"][0]]:
        job = await post(
            client,
            "production/jobs",
            **payload(filament, product, order_id=order["id"], order_item_id=line["id"]),
        )
        jobs.append(job)
        assert (await client.post(f"/api/v1/production/jobs/{job['id']}/finish")).status_code == 200
        state = (await client.get(f"/api/v1/orders/{order['id']}")).json()
        assert state["status"] == ("READY" if len(jobs) == 3 else "IN_PRODUCTION")
        if len(jobs) == 1:
            denied = await client.patch(
                f"/api/v1/orders/{order['id']}",
                json={"version_id": state["version_id"], "status": "READY"},
            )
            assert denied.status_code == 409
    assert Decimal((await get_item(client, filament["id"]))["quantity"]) == Decimal("962.5")
    assert Decimal((await get_item(client, product["id"]))["quantity"]) == 3
    extra = await client.post(
        "/api/v1/production/jobs",
        json=payload(
            filament, product, order_id=order["id"], order_item_id=order["items"][0]["id"]
        ),
    )
    assert extra.status_code == 400
    repeat = await client.post(f"/api/v1/production/jobs/{jobs[0]['id']}/finish")
    assert repeat.status_code == 409
    movements = (await client.get("/api/v1/warehouse/movements")).json()
    for job in jobs:
        legs = [m for m in movements if m["reference_id"] == job["id"]]
        assert sorted((m["kind"], Decimal(m["quantity"])) for m in legs) == [
            ("IN", Decimal("1")),
            ("OUT", Decimal("12.5")),
        ]


async def test_relationships_and_overbooking_are_checked_before_writing(client):
    filament, product = await setup_stock(client)
    a = await setup_order(client, ("1",))
    b = await setup_order(client, ("1",))
    for refs in [
        dict(order_item_id=a["items"][0]["id"]),
        dict(order_id=a["id"]),
        dict(order_id=a["id"], order_item_id=b["items"][0]["id"]),
    ]:
        response = await client.post(
            "/api/v1/production/jobs", json=payload(filament, product, **refs)
        )
        assert response.status_code == 400
    first = await post(
        client,
        "production/jobs",
        **payload(filament, product, order_id=a["id"], order_item_id=a["items"][0]["id"]),
    )
    overflow = await client.post(
        "/api/v1/production/jobs",
        json=payload(filament, product, order_id=a["id"], order_item_id=a["items"][0]["id"]),
    )
    assert overflow.status_code == 400
    state = (await client.get(f"/api/v1/orders/{a['id']}")).json()
    blocked = await client.patch(
        f"/api/v1/orders/{a['id']}", json={"version_id": state["version_id"], "items": b["items"]}
    )
    assert blocked.status_code == 409
    assert (await client.post(f"/api/v1/production/jobs/{first['id']}/cancel")).status_code == 200
    assert (await client.post(f"/api/v1/production/jobs/{first['id']}/cancel")).status_code == 409
    await post(
        client,
        "production/jobs",
        **payload(filament, product, order_id=a["id"], order_item_id=a["items"][0]["id"]),
    )


async def test_finish_failure_rolls_back_both_stock_legs_and_status(client, monkeypatch):
    filament, product = await setup_stock(client)
    order = await setup_order(client, ("1",))
    job = await post(
        client,
        "production/jobs",
        **payload(filament, product, order_id=order["id"], order_item_id=order["items"][0]["id"]),
    )
    before = (await client.get("/api/v1/warehouse/movements")).json()
    original = OperationsService.move_stock

    def failing_move(self, id, data):
        if id == product["id"]:
            raise DomainError("injected failure on second stock leg")
        return original(self, id, data)

    monkeypatch.setattr(OperationsService, "move_stock", failing_move)
    result = await client.post(f"/api/v1/production/jobs/{job['id']}/finish")
    assert result.status_code == 400
    assert Decimal((await get_item(client, filament["id"]))["quantity"]) == 1000
    assert Decimal((await get_item(client, product["id"]))["quantity"]) == 0
    assert (await client.get("/api/v1/warehouse/movements")).json() == before
    assert (await client.get(f"/api/v1/production/jobs/{job['id']}")).json()["status"] == "PLANNED"
    assert (await client.get(f"/api/v1/orders/{order['id']}")).json()["status"] == "CONFIRMED"


async def test_finish_requires_stock_mapping_and_can_be_repaired_without_recreating_job(client):
    filament, product = await setup_stock(client)
    job = await post(
        client, "production/jobs", product_name="برنامهٔ اولیه", quantity="1", filament_grams="10"
    )
    assert (await client.post(f"/api/v1/production/jobs/{job['id']}/finish")).status_code == 400
    repaired = await client.patch(
        f"/api/v1/production/jobs/{job['id']}",
        json={
            "version_id": job["version_id"],
            "filament_item_id": filament["id"],
            "product_item_id": product["id"],
        },
    )
    assert repaired.status_code == 200
    assert (await client.post(f"/api/v1/production/jobs/{job['id']}/finish")).status_code == 200
    assert Decimal((await get_item(client, filament["id"]))["quantity"]) == 990


async def test_invalid_or_inactive_stock_references_and_unit_changes_rejected(client):
    filament, product = await setup_stock(client)
    job = await post(client, "production/jobs", **payload(filament, product))
    invalid = await client.patch(
        f"/api/v1/production/jobs/{job['id']}",
        json={"version_id": job["version_id"], "filament_item_id": product["id"]},
    )
    assert invalid.status_code == 400
    assert (await client.get(f"/api/v1/production/jobs/{job['id']}")).json()[
        "filament_item_id"
    ] == filament["id"]
    changed = await client.patch(
        f"/api/v1/warehouse/items/{filament['id']}",
        json={"version_id": filament["version_id"], "unit": "PCS"},
    )
    assert changed.status_code == 400
    inactive = await client.patch(
        f"/api/v1/warehouse/items/{product['id']}",
        json={"version_id": product["version_id"], "is_active": False},
    )
    assert inactive.status_code == 200
    assert (await client.post(f"/api/v1/production/jobs/{job['id']}/finish")).status_code == 400
    assert Decimal((await get_item(client, filament["id"]))["quantity"]) == 1000


@pytest.mark.parametrize(
    "fields",
    [
        dict(quantity="0.0001", filament_grams="0.0001"),
        dict(quantity="99999999999999", filament_grams="99999999999999"),
    ],
)
async def test_filament_product_is_representable_without_silent_rounding(client, fields):
    response = await client.post(
        "/api/v1/production/jobs", json=dict(product_name="precision", **fields)
    )
    assert response.status_code == 400


@pytest.mark.parametrize(
    "path, data",
    [
        ("warehouse/items", dict(name="bad", quantity="-1")),
        ("warehouse/items", dict(name="bad", kind="PRODUCT", unit="G")),
        ("production/jobs", dict(product_name="bad", quantity="1", unit_cost="-1")),
        (
            "orders",
            dict(
                order_date="2026-10-16",
                customer_name="bad",
                items=[dict(product_name="bad", quantity="1", unit_price="-1")],
            ),
        ),
    ],
)
async def test_bad_numeric_or_unit_input_never_becomes_sqlite_500(client, path, data):
    response = await client.post("/api/v1/" + path, json=data)
    assert response.status_code in (400, 422)


async def test_null_update_is_validation_error_and_stock_move_invalidates_old_revision(client):
    filament, product = await setup_stock(client)
    response = await client.patch(
        f"/api/v1/warehouse/items/{filament['id']}",
        json={"version_id": filament["version_id"], "unit_price": None},
    )
    assert response.status_code == 422
    assert (
        await client.post(
            f"/api/v1/warehouse/items/{filament['id']}/movements",
            json={"kind": "IN", "quantity": "1"},
        )
    ).status_code == 201
    stale = await client.patch(
        f"/api/v1/warehouse/items/{filament['id']}",
        json={"version_id": filament["version_id"], "unit_price": "20"},
    )
    assert stale.status_code == 409
    movement_page = await client.get(
        "/api/v1/warehouse/movements", params={"item_id": filament["id"], "limit": 1, "offset": 1}
    )
    assert movement_page.status_code == 200
    assert len(movement_page.json()) == 1
    assert Decimal(movement_page.json()[0]["quantity"]) == 1000


async def test_orders_and_jobs_can_be_paged_without_losing_rows(client):
    for _ in range(3):
        await setup_order(client, ("1",))
        await post(client, "production/jobs", product_name="page", quantity="1")
    for path in ["orders", "production/jobs"]:
        ids = []
        for offset in range(3):
            response = await client.get("/api/v1/" + path, params={"offset": offset, "limit": 1})
            assert response.status_code == 200
            ids.append(response.json()[0]["id"])
        assert len(set(ids)) == 3
        assert (await client.get("/api/v1/" + path, params={"offset": 3, "limit": 1})).json() == []


async def test_simultaneous_finish_consumes_stock_once(client):
    import asyncio

    filament, product = await setup_stock(client)
    job = await post(client, "production/jobs", **payload(filament, product))
    responses = await asyncio.gather(
        *[client.post(f"/api/v1/production/jobs/{job['id']}/finish") for _ in range(2)]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    assert Decimal((await get_item(client, filament["id"]))["quantity"]) == Decimal("987.5")
    assert Decimal((await get_item(client, product["id"]))["quantity"]) == 1


async def test_computed_values_over_limit_fail_cleanly_and_roll_back(client):
    before = (await client.get("/api/v1/warehouse/summary")).json()
    response = await client.post(
        "/api/v1/warehouse/items",
        json={
            "name": "out-of-range valuation",
            "kind": "PRODUCT",
            "unit": "PCS",
            "quantity": "99999999999999",
            "unit_price": "2",
        },
    )
    assert response.status_code == 400, response.text
    assert (await client.get("/api/v1/warehouse/summary")).json() == before
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-16",
            "channel": "direct",
            "customer_name": "limit",
            "items": [
                {
                    "product_name": "huge",
                    "quantity": "99999999999999",
                    "unit_price": "2",
                    "inventory_item_id": (
                        await post(
                            client,
                            "warehouse/items",
                            name="huge",
                            kind="PRODUCT",
                            unit="PCS",
                            quantity="10",
                            unit_price="2",
                        )
                    )["id"],
                }
            ],
        },
    )
    assert response.status_code == 400, response.text
    assert (await client.get("/api/v1/orders")).json() == []


async def test_real_second_stock_leg_overflow_rolls_back_the_first(client):
    filament, product = await setup_stock(client)
    response = await client.post(
        f"/api/v1/warehouse/items/{product['id']}/movements",
        json={
            "kind": "IN",
            "quantity": "99999999999999.9999",
        },
    )
    assert response.status_code == 201, response.text
    job = await post(client, "production/jobs", **payload(filament, product))
    before = (await client.get("/api/v1/warehouse/summary")).json()
    moves = (await client.get("/api/v1/warehouse/movements")).json()
    response = await client.post(f"/api/v1/production/jobs/{job['id']}/finish")
    assert response.status_code == 400, response.text
    assert (await client.get("/api/v1/warehouse/summary")).json() == before
    assert (await client.get("/api/v1/warehouse/movements")).json() == moves
    assert (await client.get(f"/api/v1/production/jobs/{job['id']}")).json()["status"] == "PLANNED"


async def test_proforma_fallback_keeps_exact_snapshot_and_escapes_customer(client, monkeypatch):
    order = await post(
        client,
        "orders",
        order_date="2026-10-16",
        customer_name="<script>آزمون</script>",
        items=[
            dict(
                product_name="مدل اول",
                quantity="2",
                unit_price="123.4567",
                unit_cost="23.4567",
                inventory_item_id=(
                    await post(
                        client,
                        "warehouse/items",
                        name="مدل اول",
                        kind="PRODUCT",
                        unit="PCS",
                        quantity="2",
                        unit_price="123.4567",
                    )
                )["id"],
            ),
            dict(
                product_name="مدل دوم",
                variant="chain",
                quantity="1",
                unit_price="456.1234",
                unit_cost="56.1234",
                inventory_item_id=(
                    await post(
                        client,
                        "warehouse/items",
                        name="مدل دوم",
                        kind="PRODUCT",
                        unit="PCS",
                        quantity="1",
                        unit_price="456.1234",
                    )
                )["id"],
            ),
        ],
    )

    def missing_pdf(*args, **kwargs):
        raise RuntimeError("native renderer unavailable")

    monkeypatch.setattr("app.services.pdf.render_pdf", missing_pdf)
    response = await client.get(f"/api/v1/orders/{order['id']}/proforma.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert response.headers["content-disposition"].endswith('.html"')
    assert "۷۰۳٫۰۳۶۸" in response.text
    assert "۱۲۳٫۴۵۶۷" in response.text and "۴۵۶٫۱۲۳۴" in response.text
    assert "مدل دوم (حلقه و زنجیر)" in response.text
    assert "&lt;script&gt;آزمون&lt;/script&gt;" in response.text
    assert "<script>آزمون</script>" not in response.text
