"""Cancel snapshots and restore only cancelled orders without altering operations."""
from decimal import Decimal

import pytest
from sqlalchemy import text

from tests.order_helpers import create_order


async def patch_status(client, order, status):
    return await client.patch(f"/api/v1/orders/{order['id']}", json={
        "version_id": order["version_id"], "status": status,
    })


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", ["NEW", "CONFIRMED", "IN_PRODUCTION", "READY"])
async def test_restore_preserves_original_status_and_order_contents(client, database, previous):
    order = await create_order(client, quantities=("2",), unit_price="1000")
    if previous != "NEW":
        order = (await patch_status(client, order, previous)).json()
    original = order
    cancelled_response = await patch_status(client, order, "CANCELLED")
    assert cancelled_response.status_code == 200, cancelled_response.text
    cancelled = cancelled_response.json()
    with database.session() as session:
        assert session.execute(text("SELECT status_before_cancel FROM orders WHERE id=:id"),
                               {"id": order["id"]}).scalar_one() == previous
    history = (await client.get("/api/v1/orders?status_group=history")).json()
    assert any(row["id"] == order["id"] for row in history)
    restored_response = await client.post(f"/api/v1/orders/{order['id']}/restore", json={
        "version_id": cancelled["version_id"]
    })
    assert restored_response.status_code == 200, restored_response.text
    restored = restored_response.json()
    assert restored["status"] == previous
    assert restored["version_id"] == cancelled["version_id"] + 1
    assert restored["items"] == original["items"]
    assert Decimal(restored["total"]) == Decimal(original["total"])
    assert any(row["id"] == order["id"] for row in
               (await client.get("/api/v1/orders?status_group=active")).json())
    assert all(row["id"] != order["id"] for row in
               (await client.get("/api/v1/orders?status_group=history")).json())
    with database.session() as session:
        assert session.execute(text("SELECT status_before_cancel FROM orders WHERE id=:id"),
                               {"id": order["id"]}).scalar_one() is None


@pytest.mark.asyncio
async def test_restore_rejects_stale_or_non_cancelled_and_regular_patch_cannot_restore(client):
    order = await create_order(client)
    path = f"/api/v1/orders/{order['id']}"
    assert (await client.post(path + "/restore", json={"version_id": order["version_id"]})).status_code == 409
    cancelled = (await patch_status(client, order, "CANCELLED")).json()
    assert (await client.post(path + "/restore", json={"version_id": order["version_id"]})).status_code == 409
    assert (await client.patch(path, json={"version_id": cancelled["version_id"], "status": "NEW"})).status_code == 409
    assert (await client.get(path)).json()["status"] == "CANCELLED"
    restored = await client.post(path + "/restore", json={"version_id": cancelled["version_id"]})
    assert restored.status_code == 200
    assert (await client.post(path + "/restore", json={"version_id": cancelled["version_id"]})).status_code == 409


@pytest.mark.asyncio
async def test_legacy_cancelled_without_previous_status_is_restored_as_new(client, database):
    order = await create_order(client)
    cancelled = (await patch_status(client, order, "CANCELLED")).json()
    with database.session() as session:
        session.execute(text("UPDATE orders SET status_before_cancel=NULL WHERE id=:id"), {"id": order["id"]})
    restored = await client.post(f"/api/v1/orders/{order['id']}/restore", json={"version_id": cancelled["version_id"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "NEW"


@pytest.mark.asyncio
async def test_cannot_restore_delivered_order_or_anonymous(client, anon_client):
    order = await create_order(client)
    delivered = await patch_status(client, order, "DELIVERED")
    assert delivered.status_code == 200, delivered.text
    path = f"/api/v1/orders/{order['id']}/restore"
    assert (await client.post(path, json={"version_id": delivered.json()["version_id"]})).status_code == 409
    anon_client.cookies.clear()
    assert (await anon_client.post(path, json={"version_id": delivered.json()["version_id"]})).status_code in (401, 403)


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_restore_produced_order_preserves_jobs_and_stock(client, database, legacy):
    order = await create_order(client, quantities=("2",), unit_price="1000")
    filament_response = await client.post("/api/v1/warehouse/items", json={
        "name": "فیلامنت برای بازیابی", "kind": "FILAMENT", "unit": "G",
        "quantity": "100", "unit_price": "50",
    })
    assert filament_response.status_code == 201
    filament = filament_response.json()
    job_response = await client.post("/api/v1/production/jobs", json={
        "product_name": order["items"][0]["product_name"], "quantity": "2",
        "order_id": order["id"], "order_item_id": order["items"][0]["id"],
        "product_item_id": order["items"][0]["inventory_item_id"],
        "filament_item_id": filament["id"], "filament_grams": "10",
    })
    assert job_response.status_code == 201, job_response.text
    job = job_response.json()
    # Cancelling the order while a job is open is still refused.
    current = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert (await patch_status(client, current, "CANCELLED")).status_code == 409
    finished = await client.post(f"/api/v1/production/jobs/{job['id']}/finish")
    assert finished.status_code == 200, finished.text
    ready = (await client.get(f"/api/v1/orders/{order['id']}")).json()
    assert ready["status"] == "READY"
    stock = (await client.get("/api/v1/warehouse/items")).json()
    movements = (await client.get("/api/v1/warehouse/movements")).json()
    cancelled = (await patch_status(client, ready, "CANCELLED")).json()
    if legacy:
        with database.session() as session:
            session.execute(text("UPDATE orders SET status_before_cancel=NULL WHERE id=:id"), {"id": order["id"]})
    restored = await client.post(f"/api/v1/orders/{order['id']}/restore", json={"version_id": cancelled["version_id"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "READY"
    assert (await client.get("/api/v1/warehouse/items")).json() == stock
    assert (await client.get("/api/v1/warehouse/movements")).json() == movements
    assert (await client.get(f"/api/v1/production/jobs/{job['id']}")).json()["status"] == "DONE"
