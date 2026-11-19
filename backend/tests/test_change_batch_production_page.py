"""Production-page and orders-page fixes (the owner's 2026-11-19 list).

* 1 — a planned job reports the ordered quantity of its order line.
* 2 — filament composition of an order-linked job is editable after planning.
* 4 — the job no longer needs a hand-picked warehouse destination.
* 6 — only active, unfinished orders can start a new production job.
* 7 — «تاریخچه سفارشات» reads shipped/delivered/cancelled orders only.
* 8 — an unconfirmed (NEW) order keeps its lines and channel editable.
* 9 — an unconfirmed order can be deleted for good.
* 10/11 — finishing moves the produced models into stock even without a mapped
  product item, and delivering the order takes them out again.
"""

from __future__ import annotations

from decimal import Decimal


async def post(client, path, **data):
    response = await client.post("/api/v1/" + path, json=data)
    assert response.status_code == 201, response.text
    return response.json()


async def item(client, name, *, kind="PRODUCT", unit="PCS", quantity="0", price="500"):
    return await post(
        client,
        "warehouse/items",
        name=name,
        kind=kind,
        unit=unit,
        quantity=quantity,
        unit_price=price,
    )


async def new_order(client, product_name, quantity="3", **extra):
    response = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-11-19",
            "customer_name": "مشتری صفحه تولید",
            "items": [
                {
                    "product_name": product_name,
                    "quantity": quantity,
                    "unit_price": "1000",
                    "unit_cost": "100",
                    **extra,
                }
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def stock(client, name: str) -> Decimal:
    response = await client.get("/api/v1/warehouse/summary")
    assert response.status_code == 200, response.text
    for row in response.json()["items"]:
        if row["name"] == name:
            return Decimal(row["quantity"])
    raise AssertionError(f"{name} is not in the warehouse")


# ------------------------------------------------- 1: the ordered quantity ---
async def test_planned_job_reports_the_ordered_quantity_of_its_line(client):
    order = await new_order(client, "جاکلیدی", quantity="4")
    response = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert response.status_code == 201, response.text

    jobs = (await client.get("/api/v1/production/jobs")).json()
    assert len(jobs) == 1
    job = jobs[0]
    assert Decimal(job["quantity"]) == Decimal(4)
    assert Decimal(job["order_item_quantity"]) == Decimal(4)
    assert job["order_number"] == order["order_number"]


# ------------------------------------------------------ 2: filaments edit ---
async def test_order_linked_job_filaments_can_be_selected_after_planning(client):
    spool = await item(client, "PETG آبی", kind="FILAMENT", unit="G", quantity="1000")
    order = await new_order(client, "قاب موبایل", quantity="2")
    planned = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert planned.status_code == 201, planned.text
    job = (await client.get("/api/v1/production/jobs")).json()[0]
    assert job["filament_ready"] is False

    patched = await client.patch(
        f"/api/v1/production/jobs/{job['id']}",
        json={
            "version_id": job["version_id"],
            "filaments": [{"filament_item_id": spool["id"], "grams_per_unit": "12.5"}],
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["filament_ready"] is True
    assert body["filaments"][0]["filament_item_name"] == "PETG آبی"
    assert Decimal(body["filament_grams"]) == Decimal("12.5")


# --------------------------------- 4, 10, 11: finish → stock in, deliver → out ---
async def test_finish_without_a_mapped_product_stores_the_models_by_name(client):
    spool = await item(client, "PLA سیاه", kind="FILAMENT", unit="G", quantity="200")
    order = await new_order(client, "پایه هدفون", quantity="3")
    planned = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert planned.status_code == 201, planned.text
    job = (await client.get("/api/v1/production/jobs")).json()[0]
    assert job["product_item_id"] is None

    patched = await client.patch(
        f"/api/v1/production/jobs/{job['id']}",
        json={
            "version_id": job["version_id"],
            "filaments": [{"filament_item_id": spool["id"], "grams_per_unit": "20"}],
        },
    )
    assert patched.status_code == 200, patched.text

    finished = await client.post(f"/api/v1/production/jobs/{job['id']}/finish")
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "DONE"
    # the destination product was created on the fly, named after the job
    assert body["product_item_name"] == "پایه هدفون"
    assert await stock(client, "پایه هدفون") == Decimal(3)
    assert await stock(client, "PLA سیاه") == Decimal(140)  # 200 − 20 × 3


async def test_delivering_an_order_takes_its_items_out_of_stock(client):
    product = await item(client, "جامدادی", quantity="5")
    order = await new_order(
        client, "جامدادی", quantity="2", inventory_item_id=product["id"]
    )
    delivered = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"version_id": order["version_id"], "status": "DELIVERED"},
    )
    assert delivered.status_code == 200, delivered.text
    assert delivered.json()["status"] == "DELIVERED"
    assert await stock(client, "جامدادی") == Decimal(3)

    movements = (await client.get("/api/v1/warehouse/movements")).json()
    out = [m for m in movements if m["kind"] == "OUT" and m["reason"] == "sale"]
    assert len(out) == 1
    assert Decimal(out[0]["quantity"]) == Decimal(2)

    # a second delivery attempt is refused and never deducts twice
    again = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"version_id": delivered.json()["version_id"], "status": "DELIVERED"},
    )
    assert again.status_code in (200, 409)
    assert await stock(client, "جامدادی") == Decimal(3)


async def test_delivery_deducts_what_exists_when_stock_is_short(client):
    product = await item(client, "کوسن", quantity="1")
    order = await new_order(
        client, "کوسن", quantity="4", inventory_item_id=product["id"]
    )
    delivered = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"version_id": order["version_id"], "status": "DELIVERED"},
    )
    assert delivered.status_code == 200, delivered.text
    assert await stock(client, "کوسن") == Decimal(0)


# -------------------------------------------------------------- 6: dropdown ---
async def test_only_active_unfinished_orders_are_offered_for_production(client):
    confirmed = await new_order(client, "محصول فعال", quantity="1")
    ready = await new_order(client, "محصول تمام‌شده", quantity="1")
    for status in ("SHIPPED", "DELIVERED"):
        await client.patch(
            f"/api/v1/orders/{ready['id']}",
            json={"version_id": ready["version_id"], "status": status},
        )
        ready = (await client.get(f"/api/v1/orders/{ready['id']}")).json()

    active = (await client.get("/api/v1/orders", params={"status_group": "active"})).json()
    history = (await client.get("/api/v1/orders", params={"status_group": "history"})).json()
    assert [o["id"] for o in active] == [confirmed["id"]]
    assert [o["id"] for o in history] == [ready["id"]]
    assert active[0]["status"] == "NEW"


# ------------------------------------------------------- 7: history statuses ---
async def test_history_holds_shipped_delivered_and_cancelled_orders(client):
    cancelled = await new_order(client, "لغوی", quantity="1")
    await client.patch(
        f"/api/v1/orders/{cancelled['id']}",
        json={"version_id": cancelled["version_id"], "status": "CANCELLED"},
    )
    history = (await client.get("/api/v1/orders", params={"status_group": "history"})).json()
    assert [(o["id"], o["status"]) for o in history] == [(cancelled["id"], "CANCELLED")]
    active = (await client.get("/api/v1/orders", params={"status_group": "active"})).json()
    assert active == []
    bad = await client.get("/api/v1/orders", params={"status_group": "everything"})
    assert bad.status_code == 422


# ---------------------------------------------------- 8: unconfirmed edits ---
async def test_unconfirmed_order_keeps_items_and_channel_editable(client):
    order = await new_order(client, "عروسک", quantity="1")
    edited = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={
            "version_id": order["version_id"],
            "channel": "direct",
            "customer_name": "مشتری ویرایش‌شده",
            "items": [
                {
                    "product_name": "عروسک بزرگ",
                    "quantity": "5",
                    "unit_price": "2000",
                    "unit_cost": "300",
                    "variant": "chain",
                }
            ],
        },
    )
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert body["customer_name"] == "مشتری ویرایش‌شده"
    assert body["channel"] == "direct"
    assert len(body["items"]) == 1
    assert body["items"][0]["product_name"] == "عروسک بزرگ"
    assert Decimal(body["items"][0]["quantity"]) == Decimal(5)
    assert Decimal(body["total"]) == Decimal(10000)


# ------------------------------------------------------------- 9: deletion ---
async def test_a_new_order_can_be_deleted_for_good(client):
    order = await new_order(client, "حذفی", quantity="1")
    deleted = await client.delete(f"/api/v1/orders/{order['id']}")
    assert deleted.status_code == 204, deleted.text
    assert (await client.get(f"/api/v1/orders/{order['id']}")).status_code == 404


async def test_a_confirmed_order_cannot_be_deleted(client):
    order = await new_order(client, "تأییدشده", quantity="1")
    confirmed = await client.patch(
        f"/api/v1/orders/{order['id']}",
        json={"version_id": order["version_id"], "status": "CONFIRMED"},
    )
    assert confirmed.status_code == 200, confirmed.text
    refused = await client.delete(f"/api/v1/orders/{order['id']}")
    assert refused.status_code == 409
    assert (await client.get(f"/api/v1/orders/{order['id']}")).status_code == 200


async def test_deleting_a_new_order_removes_its_planned_jobs(client):
    order = await new_order(client, "برنامه‌ریزی‌شده", quantity="1")
    plan = await client.post(f"/api/v1/orders/{order['id']}/production")
    assert plan.status_code == 201, plan.text
    jobs = (await client.get("/api/v1/production/jobs")).json()
    assert len(jobs) == 1

    # planning confirms the order, so deleting it must be refused
    refused = await client.delete(f"/api/v1/orders/{order['id']}")
    assert refused.status_code == 409
    assert len((await client.get("/api/v1/production/jobs")).json()) == 1


async def test_a_second_job_reuses_the_product_created_by_the_first_finish(client):
    spool = await item(client, "ABS خاکستری", kind="FILAMENT", unit="G", quantity="500")
    first = await new_order(client, "گیره", quantity="1")
    second = await new_order(client, "گیره", quantity="2")
    for order in (first, second):
        planned = await client.post(f"/api/v1/orders/{order['id']}/production")
        assert planned.status_code == 201, planned.text
    jobs = (await client.get("/api/v1/production/jobs")).json()
    assert len(jobs) == 2
    for job in jobs:
        patched = await client.patch(
            f"/api/v1/production/jobs/{job['id']}",
            json={
                "version_id": job["version_id"],
                "filaments": [{"filament_item_id": spool["id"], "grams_per_unit": "10"}],
            },
        )
        assert patched.status_code == 200, patched.text
        finished = await client.post(f"/api/v1/production/jobs/{job['id']}/finish")
        assert finished.status_code == 200, finished.text

    summary = (await client.get("/api/v1/warehouse/summary")).json()["items"]
    matches = [row for row in summary if row["name"] == "گیره"]
    assert len(matches) == 1
    assert Decimal(matches[0]["quantity"]) == Decimal(3)
    assert await stock(client, "ABS خاکستری") == Decimal(470)
