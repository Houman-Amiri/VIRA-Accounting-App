"""Installation calendar preference: durable append-only settings without DDL."""

import json
import sqlite3

import pytest
from sqlalchemy import select, text

from app.api.calendar import _read
from app.models import User

PATH = "/api/v1/settings/calendar"


async def test_calendar_defaults(client):
    response = await client.get("/api/v1/settings/calendar")
    assert response.status_code == 200
    assert response.json() == {
        "calendar": "jalali",
        "version_id": 0,
        "timezone": "Asia/Tehran",
        "scope": "installation",
    }


async def test_persist_restart_and_backup_without_revision_or_data_rewrite(
    client, database, tmp_path
):
    schema = None
    with database.session() as s:
        schema = s.execute(text("SELECT sql FROM sqlite_master ORDER BY name")).all()
        before = s.execute(text("SELECT * FROM users")).all()
    saved = await client.put(PATH, json={"calendar": "gregorian", "version_id": 0})
    assert saved.status_code == 200
    assert saved.json()["version_id"] == 1
    # Brand-new engine/session, not a process-local or browser preference.
    from app.db import Database

    other = Database(database.settings)
    with other.session() as s:
        assert _read(s).calendar == "gregorian"
        assert s.execute(text("SELECT sql FROM sqlite_master ORDER BY name")).all() == schema
        assert s.execute(text("SELECT * FROM users")).all() == before
        assert (
            s.execute(text("SELECT version_num FROM alembic_version")).scalar()
            == "0005_pricing_settings"
        )
    other.dispose()
    backup = tmp_path / "copy.sqlite3"
    with (
        sqlite3.connect(database.settings.sqlite_database_path) as src,
        sqlite3.connect(backup) as dst,
    ):
        src.backup(dst)
        detail = dst.execute(
            "SELECT detail FROM security_audit_logs WHERE event='CALENDAR_PREFERENCE_UPDATED'"
        ).fetchone()[0]
        assert json.loads(detail) == {"calendar": "gregorian", "version_id": 1}
        assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert dst.execute("PRAGMA foreign_key_check").fetchall() == []


async def test_cas_noop_and_multiple_revisions(client):
    assert (await client.put(PATH, json={"calendar": "jalali", "version_id": 0})).json()[
        "version_id"
    ] == 0
    assert (
        await client.put(PATH, json={"calendar": "gregorian", "version_id": 0})
    ).status_code == 200
    assert (await client.put(PATH, json={"calendar": "jalali", "version_id": 0})).status_code == 409
    assert (await client.get(PATH)).json()["calendar"] == "gregorian"
    assert (await client.put(PATH, json={"calendar": "jalali", "version_id": 1})).json()[
        "version_id"
    ] == 2


@pytest.mark.parametrize(
    "body",
    [
        {"calendar": "unknown", "version_id": 0},
        {"calendar": "jalali", "version_id": -1},
        {"calendar": "jalali", "version_id": True},
        {"calendar": "jalali", "version_id": "0"},
        {"calendar": "jalali", "version_id": 0, "timezone": "UTC"},
    ],
)
async def test_invalid_no_write(client, body):
    assert (await client.put(PATH, json=body)).status_code == 422
    assert (await client.get(PATH)).json()["version_id"] == 0


async def test_auth_csrf(anon_client, client):
    del client.headers["X-CSRF-Token"]
    assert (
        await client.put(PATH, json={"calendar": "gregorian", "version_id": 0})
    ).status_code == 403
    client.cookies.clear()
    assert (await client.get(PATH)).status_code == 401


@pytest.mark.parametrize(
    "role,read,write", [("BOOKKEEPER", 200, 200), ("AUDITOR", 200, 403), ("INGEST_API", 403, 403)]
)
async def test_roles(client, database, role, read, write):
    with database.session() as s:
        s.scalar(select(User).where(User.username == "owner")).role = role
    result = await client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "test-password-1"}
    )
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    assert (await client.get(PATH)).status_code == read
    assert (
        await client.put(PATH, json={"calendar": "gregorian", "version_id": 0})
    ).status_code == write


async def test_corruption_not_masked(client, database):
    from app.services.security_audit import record_security_event

    with database.session() as s:
        record_security_event(s, "CALENDAR_PREFERENCE_UPDATED", detail="corrupt")
    assert (await client.get(PATH)).status_code == 503
    assert (
        await client.put(PATH, json={"calendar": "gregorian", "version_id": 0})
    ).status_code == 503


async def test_concurrent_process_sessions_only_one_cas_wins(client, database):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.api.calendar import update_calendar
    from app.schemas.calendar import CalendarUpdate
    from app.security.session import SessionUser
    from app.services.errors import StaleVersionError

    with database.session() as s:
        owner = s.scalar(select(User).where(User.username == "owner"))
        actor = SessionUser(owner.id, owner.username, owner.role)
    barrier = Barrier(2)

    def write():
        barrier.wait(timeout=10)
        try:
            with database.session() as s:
                return update_calendar(
                    CalendarUpdate(calendar="gregorian", version_id=0), s, actor
                ).version_id
        except StaleVersionError:
            return "stale"

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: write(), range(2)))
    assert sorted(map(str, outcomes)) == ["1", "stale"]
    assert (await client.get(PATH)).json()["version_id"] == 1


@pytest.mark.parametrize(
    "details",
    [
        [{"calendar": "gregorian", "version_id": 2}],
        [{"calendar": "gregorian", "version_id": 1}, {"calendar": "jalali", "version_id": 1}],
        [{"calendar": "gregorian", "version_id": 2147483647}],
    ],
)
async def test_revision_gap_or_duplicate_fails_closed(client, database, details):
    from app.services.security_audit import record_security_event

    with database.session() as s:
        for detail in details:
            record_security_event(s, "CALENDAR_PREFERENCE_UPDATED", detail=detail)
    assert (await client.get(PATH)).status_code == 503


async def test_preference_does_not_rewrite_operational_records(client, database):
    from tests.test_security_phase5 import _accounts, _entry_payload

    a, b = await _accounts(client)
    entry = await client.post("/api/v1/journal-entries", json=_entry_payload(a, b, "1234.5678"))
    assert entry.status_code == 201, entry.text
    entry = await client.post(f"/api/v1/journal-entries/{entry.json()['id']}/post")
    assert entry.status_code == 200, entry.text
    order = await client.post(
        "/api/v1/orders",
        json={
            "order_date": "2026-10-14",
            "customer_name": "calendar sample",
            "items": [
                {
                    "product_name": "sample",
                    "quantity": "2",
                    "unit_price": "1234.5678",
                    "unit_cost": "111.1111",
                }
            ],
        },
    )
    assert order.status_code == 201, order.text
    tables = ["journal_entries", "transaction_splits", "orders", "order_items", "fiscal_periods"]
    with database.session() as s:
        # Full values including immutable posted/creation metadata and scaled money.
        before = {t: s.execute(text(f"SELECT * FROM {t} ORDER BY id")).all() for t in tables}
    for calendar, version in [("gregorian", 0), ("jalali", 1)]:
        assert (
            await client.put(PATH, json={"calendar": calendar, "version_id": version})
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/journal-entries/{entry.json()['id']}")
        ).json() == entry.json()
        assert (await client.get(f"/api/v1/orders/{order.json()['id']}")).json() == order.json()
    with database.session() as s:
        assert {
            t: s.execute(text(f"SELECT * FROM {t} ORDER BY id")).all() for t in tables
        } == before
