"""Real authenticated pricing preferences, scaled SQLite storage and migrations."""
from decimal import Decimal

import pytest
from sqlalchemy import select, text

from app.models import User
from app.models.pricing import PricingSettings

PATH = "/api/v1/settings/pricing"


def update_body(doc, **patch):
    return {k: v for k, v in doc.items() if k != "updated_at"} | patch


async def test_defaults_and_saved_constants_survive_fresh_session(client, database):
    doc = (await client.get(PATH)).json()
    assert doc["filamentPerGram"] == "3000.0000"
    assert Decimal(doc["profitFactor"]) == Decimal("2.5")
    saved = await client.put(PATH, json=update_body(doc, filamentPerGram="4000.1234", profitFactor="3.125"))
    assert saved.status_code == 200, saved.text
    assert saved.json()["version_id"] == doc["version_id"] + 1
    with database.session() as session:
        raw = session.execute(text("SELECT filament_per_gram, profit_factor, typeof(filament_per_gram) FROM pricing_settings")).one()
        assert raw == (400012340, 31250, "integer")  # Toman -> Rial -> ×10000
        assert session.get(PricingSettings, 1).filament_per_gram == Decimal("40001.2340")
        events = session.execute(text("SELECT event FROM security_audit_logs WHERE event='PRICING_CONSTANTS_UPDATED'")).all()
        assert len(events) == 1
    fetched = await client.get(PATH)
    assert fetched.json() == saved.json()


async def test_stale_revision_does_not_overwrite_other_save(client):
    original = (await client.get(PATH)).json()
    assert (await client.put(PATH, json=update_body(original, labelPerUnit="9000"))).status_code == 200
    stale = await client.put(PATH, json=update_body(original, labelPerUnit="10000"))
    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_version"
    assert Decimal((await client.get(PATH)).json()["labelPerUnit"]) == Decimal("9000")


@pytest.mark.parametrize("patch", [
    {"filamentPerGram": "-1"}, {"filamentPerGram": "NaN"}, {"filamentPerGram": "Infinity"},
    {"filamentPerGram": "0.12345"}, {"filamentPerGram": "1000000000001"},
    {"profitFactor": "1001"}, {"profitFactor": "-1"}, {"version_id": 0},
    {"commissionPercent": "20"}, {"printerPowerKw": "3"}, {"nylonPerUnit": "100"},
])
async def test_invalid_or_inactive_values_are_rejected_without_writes(client, patch):
    before = (await client.get(PATH)).json()
    result = await client.put(PATH, json=update_body(before, **patch))
    assert result.status_code == 422, result.text
    assert (await client.get(PATH)).json() == before


async def test_anonymous_cannot_read_or_save(anon_client):
    assert (await anon_client.get(PATH)).status_code == 401
    assert (await anon_client.put(PATH, json={})).status_code in (401, 403)


async def test_write_requires_csrf(client):
    doc = (await client.get(PATH)).json()
    del client.headers["X-CSRF-Token"]
    assert (await client.put(PATH, json=update_body(doc))).status_code == 403


@pytest.mark.parametrize("role,read_status,write_status", [("AUDITOR", 200, 403), ("INGEST_API", 403, 403), ("BOOKKEEPER", 200, 200)])
async def test_roles_enforced_on_server(client, database, role, read_status, write_status):
    original = (await client.get(PATH)).json()
    with database.session() as session:
        session.scalar(select(User).where(User.username == "owner")).role = role
    login = await client.post("/api/v1/auth/login", json={"username": "owner", "password": "test-password-1"})
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    assert (await client.get(PATH)).status_code == read_status
    assert (await client.put(PATH, json=update_body(original))).status_code == write_status


async def test_changing_settings_does_not_rewrite_saved_order_prices(client):
    order = await client.post("/api/v1/orders", json={
        "order_date": "2026-10-16", "customer_name": "fixture",
        "items": [{"product_name": "retained price", "quantity": "1", "unit_price": "123.4567", "unit_cost": "23.4567"}],
    })
    assert order.status_code == 201, order.text
    original = order.json()
    settings = (await client.get(PATH)).json()
    assert (await client.put(PATH, json=update_body(settings, filamentPerGram="9999"))).status_code == 200
    fetched = await client.get(f"/api/v1/orders/{original['id']}")
    assert fetched.json() == original


async def test_new_migration_preserves_existing_records_and_downgrades(client, database):
    from alembic.config import Config

    from alembic import command
    from tests.conftest import BACKEND_DIR

    order = await client.post("/api/v1/orders", json={
        "order_date": "2026-10-16", "customer_name": "migration fixture",
        "items": [{"product_name": "saved before migration", "quantity": "2", "unit_price": "123.4567", "unit_cost": "23.4567"}],
    })
    assert order.status_code == 201, order.text
    order_before = order.json()
    with database.session() as session:
        before = session.execute(text("SELECT id, username, password_hash FROM users")).all()
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(cfg, "0004_operations")
    command.upgrade(cfg, "head")
    with database.session() as session:
        assert session.execute(text("SELECT id, username, password_hash FROM users")).all() == before
        assert session.execute(text("SELECT version_id FROM pricing_settings")).scalar_one() == 1
        assert "STRICT" in session.execute(text("SELECT sql FROM sqlite_master WHERE name='pricing_settings'")).scalar_one()

    assert (await client.get(f"/api/v1/orders/{order_before['id']}" )).json() == order_before
