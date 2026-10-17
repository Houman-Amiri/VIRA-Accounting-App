"""Catalog persistence, reference safety, permissions, concurrency and exact math."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest
from sqlalchemy import text

BASE = "/api/v1/warehouse"


async def add(client, category, name):
    path = f"{BASE}/suppliers" if category == "suppliers" else f"{BASE}/catalog/{category}"
    res = await client.post(path, json={"name": name})
    assert res.status_code == 201, res.text
    return res.json(), path


async def item(client, kind="FILAMENT", unit="G", supplier=None):
    return await client.post(
        f"{BASE}/items",
        json={
            "name": "کالای آزمایشی",
            "kind": kind,
            "unit": unit,
            "supplier_id": supplier,
            "quantity": "12.3456",
            "unit_price": "7.0001",
            "min_quantity": "20",
        },
    )


async def test_catalog_persistence_generic_stock_and_no_implicit_production(client, database):
    typ, _ = await add(client, "types", "رزین")
    unit, _ = await add(client, "units", "لیتر")
    sup, _ = await add(client, "suppliers", "تأمین رزین")
    assert typ["production_role"] == "NONE" and typ["required_unit"] is None
    res = await item(client, typ["id"], unit["id"], sup["id"])
    assert res.status_code == 201, res.text
    row = res.json()
    assert (row["kind_name"], row["unit_name"], row["supplier_name"]) == (
        "رزین",
        "لیتر",
        "تأمین رزین",
    )
    assert Decimal(row["value"]) == Decimal("12.3456") * Decimal("7.0001")
    move = await client.post(
        f"{BASE}/items/{row['id']}/movements", json={"kind": "OUT", "quantity": "0.1234"}
    )
    assert move.status_code == 201
    rows = (await client.get(f"{BASE}/items")).json()
    assert Decimal(rows[0]["quantity"]) == Decimal("12.2222")
    assert (await client.get(f"{BASE}/summary")).json()["other_count"] == 1
    alarm = (await client.get(f"{BASE}/alarms")).json()[0]
    assert (alarm["kind_name"], alarm["unit_name"]) == ("رزین", "لیتر")
    # Explicitly not a filament/product despite using an existing warehouse unit.
    job = await client.post(
        "/api/v1/production/jobs",
        json={
            "product_name": "رزین",
            "quantity": "1",
            "filament_item_id": row["id"],
            "filament_grams": "1",
        },
    )
    assert job.status_code == 400
    from app.db import Database

    other = Database(database.settings)
    try:
        with other.session() as s:
            assert (
                s.execute(
                    text("SELECT name FROM item_units WHERE id=:id"), {"id": unit["id"]}
                ).scalar()
                == "لیتر"
            )
            assert s.execute(text("PRAGMA foreign_key_check")).all() == []
            assert s.execute(text("SELECT COUNT(*) FROM stock_movements")).scalar() == 2
    finally:
        other.dispose()


@pytest.mark.parametrize("category", ["types", "units", "suppliers"])
async def test_used_deletion_preserves_references_reactivation_stale_and_audit(
    client, database, category
):
    choice, path = await add(client, category, "گزینهٔ استفاده‌شده")
    typ = choice["id"] if category == "types" else "FILAMENT"
    unit = choice["id"] if category == "units" else "G"
    if category == "units":
        custom, _ = await add(client, "types", "کالای عمومی")
        typ = custom["id"]
    row = (await item(client, typ, unit, choice["id"] if category == "suppliers" else None)).json()
    with database.session() as s:
        before = s.execute(text("SELECT * FROM inventory_items")).all()
        movements = s.execute(text("SELECT * FROM stock_movements")).all()
    removed = await client.delete(f"{path}/{choice['id']}", params={"version_id": 1})
    assert removed.status_code == 200, removed.text
    assert removed.json()["action"] == "deactivated"
    assert "سوابق" in removed.json()["reason"]
    assert (
        await item(client, typ, unit, choice["id"] if category == "suppliers" else None)
    ).status_code == 400
    assert (
        await client.patch(f"{path}/{choice['id']}", json={"version_id": 1, "is_active": True})
    ).status_code == 409
    active = (await client.get(path, params={"active_only": True})).json()
    assert choice["id"] not in [r["id"] for r in active]
    assert any(r["id"] == row["id"] for r in (await client.get(f"{BASE}/items")).json())
    with database.session() as s:
        assert s.execute(text("SELECT * FROM inventory_items")).all() == before
        assert s.execute(text("SELECT * FROM stock_movements")).all() == movements
        assert s.execute(text("PRAGMA foreign_key_check")).all() == []
        events = s.execute(
            text("SELECT actor_id, detail FROM security_audit_logs WHERE event='CATALOG_CHANGED'")
        ).all()
        assert any(
            actor and json.loads(detail)["action"] == "deactivated" for actor, detail in events
        )
    # Existing inventory and historical unit remain usable, without conversion.
    assert (
        await client.post(
            f"{BASE}/items/{row['id']}/movements", json={"kind": "OUT", "quantity": "1"}
        )
    ).status_code == 201
    restored = await client.patch(
        f"{path}/{choice['id']}", json={"version_id": 2, "is_active": True}
    )
    assert restored.status_code == 200, restored.text
    assert (
        await item(client, typ, unit, choice["id"] if category == "suppliers" else None)
    ).status_code == 201


@pytest.mark.parametrize("category", ["types", "units", "suppliers"])
async def test_unused_deletion_and_duplicate_name_rules(client, category):
    row, path = await add(client, category, "  كالا   جديد  ")
    assert row["name"] == "کالا جدید"
    for name in ["کالا جدید", "كالا جديد", "کالا   جدید"]:
        assert (await client.post(path, json={"name": name})).status_code == 409
    for name in ["", "   ", "\u202etest"]:
        assert (await client.post(path, json={"name": name})).status_code == 422
    assert (
        await client.delete(f"{path}/{row['id']}", params={"version_id": 99})
    ).status_code == 409
    deleted = await client.delete(f"{path}/{row['id']}", params={"version_id": 1})
    assert deleted.status_code == 200 and deleted.json()["action"] == "deleted"
    assert row["id"] not in [r["id"] for r in (await client.get(path)).json()]


@pytest.mark.parametrize(
    "kind,unit,status",
    [
        ("FILAMENT", "PCS", 400),
        ("PRODUCT", "G", 400),
        ("missing", "G", 404),
        ("FILAMENT", "missing", 404),
    ],
)
async def test_invalid_pair_or_reference_rejected(client, kind, unit, status):
    assert (await item(client, kind, unit)).status_code == status


async def test_system_semantics_cannot_be_injected_and_unit_cannot_be_changed(client):
    res = await client.post(
        f"{BASE}/catalog/types", json={"name": "رزین", "production_role": "FILAMENT"}
    )
    assert res.status_code == 422
    row = (await item(client)).json()
    unit, _ = await add(client, "units", "کیلوگرم")
    change = await client.patch(
        f"{BASE}/items/{row['id']}", json={"version_id": row["version_id"], "unit": unit["id"]}
    )
    assert change.status_code == 400
    seeded = await client.delete(f"{BASE}/catalog/types/FILAMENT", params={"version_id": 1})
    assert seeded.status_code == 200 and seeded.json()["action"] == "deactivated"
    assert (await item(client)).status_code == 400


async def test_concurrent_revision_and_name_requests(client):
    row, path = await add(client, "types", "هم‌زمان")
    responses = await asyncio.gather(
        *[
            client.patch(f"{path}/{row['id']}", json={"version_id": 1, "is_active": False})
            for _ in range(2)
        ]
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    responses = await asyncio.gather(
        *[client.post(f"{BASE}/catalog/units", json={"name": "نام هم‌زمان"}) for _ in range(2)]
    )
    assert sorted(r.status_code for r in responses) == [201, 409]


async def test_catalog_authentication_permissions_and_csrf(anon_client, app, client):
    # fixture client shares cookies; use an independent unauthenticated transport.
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get(f"{BASE}/catalog/types")).status_code == 401
    csrf = client.headers.pop("X-CSRF-Token")
    assert (await client.post(f"{BASE}/catalog/types", json={"name": "ممنوع"})).status_code == 403
    client.headers["X-CSRF-Token"] = csrf
    from app.api.deps import get_current_user
    from app.security.session import SessionUser

    app.dependency_overrides[get_current_user] = lambda: SessionUser(
        user_id="audit", username="audit", role="AUDITOR"
    )
    try:
        assert (await client.get(f"{BASE}/catalog/types")).status_code == 200
        assert (
            await client.post(f"{BASE}/catalog/types", json={"name": "ممنوع"})
        ).status_code == 403
        assert (
            await client.delete(f"{BASE}/catalog/units/G", params={"version_id": 1})
        ).status_code == 403
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("supplier_id", ["", "missing-supplier"])
async def test_invalid_supplier_reference_is_rejected_before_sql(client, supplier_id):
    response = await item(client, supplier=supplier_id)
    assert response.status_code == 404
    row = (await item(client)).json()
    changed = await client.patch(f"{BASE}/items/{row['id']}", json={"version_id": row["version_id"], "supplier_id": supplier_id})
    assert changed.status_code == 404
