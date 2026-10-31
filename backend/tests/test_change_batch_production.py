"""Item 1, 2, 5, 6 and 7 of the owner's change list, on the real API.

* 1 — a warehouse item can be deleted; used items are deactivated, not lost.
* 2 — starting/finishing production never rewrites the warehouse unit price.
* 5 — an order whose filament cannot cover it is refused.
* 6 — a job carries several filament spools, each with its own grams/price.
* 7 — order lines come from the warehouse; shortages warn, absence refuses.
"""

from __future__ import annotations

from decimal import Decimal


async def post(client, path, **data):
    response = await client.post("/api/v1/" + path, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def item(client, name, *, kind="FILAMENT", unit="G", quantity="1000", price="100"):
    return await post(
        client,
        "warehouse/items",
        name=name,
        kind=kind,
        unit=unit,
        quantity=quantity,
        unit_price=price,
    )


async def stocked_product(client, name="محصول", quantity="5", price="500"):
    return await item(
        client, name, kind="PRODUCT", unit="PCS", quantity=quantity, price=price
    )


async def order_with(client, product, quantity="1", **extra):
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [
                {
                    "product_name": product["name"],
                    "quantity": quantity,
                    "unit_price": "1000",
                    "unit_cost": "100",
                    "inventory_item_id": product["id"],
                    **extra,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def job(client, product, filaments, quantity="2", **extra):
    return await post(
        client,
        "production/jobs",
        product_name="کار",
        quantity=quantity,
        product_item_id=product["id"],
        filaments=filaments,
        **extra,
    )


# ------------------------------------------------------- 6: several spools ---
async def test_job_consumes_every_selected_spool_with_its_own_cost(client):
    black, white = await item(client, "مشکی"), await item(
        client, "سفید", quantity="500", price="250"
    )
    product = await stocked_product(client, quantity="0")
    created = await job(
        client,
        product,
        [
            {"filament_item_id": black["id"], "grams_per_unit": "10"},
            {"filament_item_id": white["id"], "grams_per_unit": "2.5", "unit_cost": "300"},
        ],
    )
    assert created["filament_ready"] is True
    assert [Decimal(row["grams_per_unit"]) for row in created["filaments"]] == [
        Decimal("10"),
        Decimal("2.5"),
    ]
    assert [Decimal(row["grams_total"]) for row in created["filaments"]] == [
        Decimal("20"),
        Decimal("5"),
    ]
    # price defaults to the spool's warehouse price, otherwise the given one
    assert [Decimal(row["unit_cost"]) for row in created["filaments"]] == [
        Decimal("100"),
        Decimal("300"),
    ]
    assert Decimal(created["filament_grams"]) == Decimal("12.5")

    finished = await client.post(f"/api/v1/production/jobs/{created['id']}/finish")
    assert finished.status_code == 200, finished.text
    items = {i["name"]: i for i in (await client.get("/api/v1/warehouse/items")).json()}
    assert Decimal(items["مشکی"]["quantity"]) == Decimal("980")  # 1000 − 2×10
    assert Decimal(items["سفید"]["quantity"]) == Decimal("495")  # 500 − 2×2.5
    assert Decimal(items["محصول"]["quantity"]) == Decimal("2")


async def test_finishing_refuses_when_one_of_the_spools_is_short(client):
    plenty = await item(client, "پر", quantity="1000")
    short = await item(client, "کم", quantity="3")
    product = await stocked_product(client, quantity="0")
    created = await job(
        client,
        product,
        [
            {"filament_item_id": plenty["id"], "grams_per_unit": "1"},
            {"filament_item_id": short["id"], "grams_per_unit": "5"},
        ],
    )
    response = await client.post(f"/api/v1/production/jobs/{created['id']}/finish")
    assert response.status_code == 409
    assert response.json()["code"] == "insufficient_stock"
    assert "کم" in response.json()["detail"]
    # nothing was consumed and the job is still open: no half-deducted stock
    movements = (await client.get("/api/v1/warehouse/movements")).json()
    assert [m for m in movements if m["reference_id"] == created["id"]] == []
    state = (await client.get(f"/api/v1/production/jobs/{created['id']}")).json()
    assert state["status"] != "DONE"
    assert state["filament_ready"] is True


async def test_the_same_spool_cannot_appear_twice_in_one_job(client):
    spool = await item(client, "تکراری")
    product = await stocked_product(client, quantity="0")
    response = await client.post(
        "/api/v1/production/jobs",
        json={
            "product_name": "کار",
            "quantity": "1",
            "product_item_id": product["id"],
            "filaments": [
                {"filament_item_id": spool["id"], "grams_per_unit": "1"},
                {"filament_item_id": spool["id"], "grams_per_unit": "2"},
            ],
        },
    )
    assert response.status_code == 422
    assert "یک بار" in response.text


async def test_a_job_cannot_finish_without_any_filament(client):
    product = await stocked_product(client, quantity="0")
    created = await post(
        client, "production/jobs", product_name="بی‌فیلامنت", quantity="1",
        product_item_id=product["id"],
    )
    assert created["filament_ready"] is False
    response = await client.post(f"/api/v1/production/jobs/{created['id']}/finish")
    assert response.status_code == 400, response.text
    assert "فیلامنت" in response.json()["detail"]


# --------------------------------------------- 2: warehouse price stability ---
async def test_production_never_rewrites_the_warehouse_unit_price(client):
    spool = await item(client, "فیلامنت ثابت", price="100")
    product = await stocked_product(client, quantity="0", price="700")
    created = await job(
        client, product, [{"filament_item_id": spool["id"], "grams_per_unit": "5"}],
        unit_cost="1000",
    )
    assert (await client.post(f"/api/v1/production/jobs/{created['id']}/start")).status_code == 200
    assert (await client.post(f"/api/v1/production/jobs/{created['id']}/finish")).status_code == 200
    items = {i["name"]: i for i in (await client.get("/api/v1/warehouse/items")).json()}
    # the internal transfer must not re-price either side (item 2)
    assert Decimal(items["فیلامنت ثابت"]["unit_price"]) == Decimal("100")
    assert Decimal(items["محصول"]["unit_price"]) == Decimal("700")


# ---------------------------------------------------- 1: delete a warehouse item ---
async def test_unused_item_is_deleted_and_used_item_is_only_deactivated(client):
    unused = await item(client, "کالای بی‌استفاده", quantity="0")
    response = await client.delete(
        f"/api/v1/warehouse/items/{unused['id']}", params={"version_id": unused["version_id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["action"] == "deleted"
    names = [i["name"] for i in (await client.get("/api/v1/warehouse/items")).json()]
    assert "کالای بی‌استفاده" not in names

    used = await item(client, "کالای دارای گردش")
    await post(client, f"warehouse/items/{used['id']}/movements", kind="IN", quantity="5")
    listed = next(
        i for i in (await client.get("/api/v1/warehouse/items")).json() if i["id"] == used["id"]
    )
    response = await client.delete(
        f"/api/v1/warehouse/items/{used['id']}", params={"version_id": listed["version_id"]}
    )
    assert response.status_code == 200, response.text
    assert response.json()["action"] == "deactivated"
    # it disappears from the pickers, but its stock history is untouched
    listed_after = (await client.get("/api/v1/warehouse/items")).json()
    assert all(row["id"] != used["id"] for row in listed_after)
    assert len((await client.get("/api/v1/warehouse/movements")).json()) == 2


async def test_deleting_a_stale_item_is_refused_with_409(client):
    created = await item(client, "همزمان")
    await client.patch(
        f"/api/v1/warehouse/items/{created['id']}",
        json={"version_id": created["version_id"], "notes": "ویرایش"},
    )
    response = await client.delete(
        f"/api/v1/warehouse/items/{created['id']}", params={"version_id": created["version_id"]}
    )
    assert response.status_code == 409


# ------------------------------------ 7 + 5: ordering from the warehouse only ---
async def test_order_line_without_a_warehouse_product_is_refused(client):
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [{"product_name": "چیز نامعلوم", "quantity": "1", "unit_price": "10"}],
        },
    )
    assert response.status_code == 400
    assert "انبار" in response.json()["detail"]
    assert (await client.get("/api/v1/orders")).json() == []


async def test_a_filament_item_cannot_be_sold_as_an_order_line(client):
    spool = await item(client, "فقط فیلامنت")
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [
                {"quantity": "1", "unit_price": "10", "inventory_item_id": spool["id"]}
            ],
        },
    )
    assert response.status_code == 400
    assert "محصول" in response.json()["detail"]


async def test_short_stock_order_is_saved_with_a_shortage_warning(client):
    product = await stocked_product(client, quantity="1")
    order = await order_with(client, product, quantity="4")
    assert order["warnings"] and "کمبود" in order["warnings"][0]
    assert Decimal(order["items"][0]["quantity"]) == Decimal("4")
    # the stored name defaults to the warehouse item's name when omitted
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [
                {"quantity": "1", "unit_price": "1000", "inventory_item_id": product["id"]}
            ],
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["items"][0]["product_name"] == product["name"]
    assert response.json()["items"][0]["inventory_item_name"] == product["name"]


async def test_order_is_refused_when_the_filament_cannot_cover_it(client):
    spool = await item(client, "کمیاب", quantity="10")
    product = await stocked_product(client, quantity="0")
    done = await job(
        client, product, [{"filament_item_id": spool["id"], "grams_per_unit": "5"}],
        quantity="1",
    )
    assert (await client.post(f"/api/v1/production/jobs/{done['id']}/finish")).status_code == 200
    # the spool has 5 g left; 4 more pieces would need 20 g
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [
                {
                    "quantity": "4",
                    "unit_price": "1000",
                    "inventory_item_id": product["id"],
                }
            ],
        },
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "insufficient_stock"
    assert (await client.get("/api/v1/orders")).json() == []


# ------------------------------------- 4: add an order to the production line ---
async def test_add_to_production_plans_a_job_for_each_unbuilt_line(client):
    spool = await item(client, "خط تولید", quantity="1000")
    product = await stocked_product(client, quantity="0")
    seed_job = await job(
        client, product, [{"filament_item_id": spool["id"], "grams_per_unit": "7"}],
        quantity="1",
    )
    assert (await client.post(f"/api/v1/production/jobs/{seed_job['id']}/finish")).status_code == 200
    order = await order_with(client, product, quantity="2")

    planned = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert planned.status_code == 201, planned.text
    body = planned.json()
    assert body["warnings"] == []
    assert len(body["created"]) == 1
    job_read = body["created"][0]
    assert Decimal(job_read["quantity"]) == Decimal("2")
    assert [Decimal(row["grams_total"]) for row in job_read["filaments"]] == [Decimal("14")]

    again = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert again.status_code == 409
    assert "کار تولید باز" in again.json()["detail"]


async def test_add_to_production_warns_when_the_product_was_never_printed(client):
    product = await stocked_product(client, quantity="0")
    order = await order_with(client, product, quantity="1")
    planned = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert planned.status_code == 201, planned.text
    body = planned.json()
    assert len(body["created"]) == 1
    assert body["created"][0]["filaments"] == []
    assert body["warnings"] and "فرمول" in body["warnings"][0]


async def test_shortage_text_shows_plain_numbers_not_exponents(client):
    """`Decimal('20').normalize()` printed "2E+1" in a Persian error message."""
    from app.money import plain_number

    assert [plain_number(value) for value in ("20", "25", "12.5", "0.5", "1000")] == [
        "20",
        "25",
        "12.5",
        "0.5",
        "1000",
    ]

    product = await stocked_product(client, quantity="1")
    order = await order_with(client, product, quantity="20")
    warning = order["warnings"][0]
    assert "سفارش 20 عدد" in warning and "موجودی 1 عدد" in warning
    assert "E+" not in warning and "E-" not in warning

    spool = await item(client, "کم", quantity="20")
    done = await job(
        client, product, [{"filament_item_id": spool["id"], "grams_per_unit": "5"}], quantity="1"
    )
    assert (await client.post(f"/api/v1/production/jobs/{done['id']}/finish")).status_code == 200
    # 15 g left, 4 pieces need 20 g -> refused, and the text must stay readable
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-20",
            "customer_name": "مشتری",
            "items": [
                {"quantity": "4", "unit_price": "1000", "inventory_item_id": product["id"]}
            ],
        },
    )
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert "نیاز 20 گرم" in detail and "موجود 15 گرم" in detail
    assert "E+" not in detail and "E-" not in detail
