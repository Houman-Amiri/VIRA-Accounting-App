"""Shared test fixtures — on-disk temporary SQLite databases (per mandate).

Each test gets its own SQLite file with migrations applied and seed data.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


def run_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.upgrade(cfg, "head")


def alembic_head() -> str:
    """Current Alembic head revision (keeps provenance tests migration-proof)."""
    from alembic.script import ScriptDirectory

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg).get_current_head()


def downgrade_migrations() -> None:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    command.downgrade(cfg, "base")


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Iterator[None]:
    """Rate limiter state is process-wide — reset per test for isolation."""
    from app.security.ratelimit import limiter

    limiter.reset()
    yield


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "vira.sqlite3"
    monkeypatch.setenv("SQLITE_DATABASE_PATH", str(path))
    monkeypatch.setenv("SESSION_SECRET", "test-session-secret-that-is-long-enough-1234")
    monkeypatch.setenv("ENVIRONMENT", "development")
    return path


@pytest.fixture()
def database(db_path: Path) -> Iterator:
    run_migrations()
    # WAL so the test-session connection and the app connection don't block
    # each other between statements (readers never block writers).
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    from app.config import load_settings
    from app.db import Database

    settings = load_settings()
    db = Database(settings)
    with db.session() as session:
        # Only the owner user is seeded — tests create their own accounts so
        # code uniqueness stays under their control.  The chart of accounts is
        # covered by test_seed.py.
        from app.seed import seed_owner_user

        seed_owner_user(session, password="test-password-1")
    yield db
    db.dispose()


@pytest.fixture()
def session(database) -> Iterator:
    with database.session() as s:
        yield s


@pytest.fixture()
def app(database):
    from app.main import create_app

    return create_app(database.settings)


@pytest.fixture()
async def anon_client(app) -> Iterator:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture()
async def client(anon_client) -> Iterator:
    """Authenticated owner client with a valid CSRF token."""
    resp = await anon_client.post(
        "/api/v1/auth/login",
        json={"username": "owner", "password": "test-password-1"},
    )
    assert resp.status_code == 200, resp.text
    csrf = resp.json()["csrf_token"]
    anon_client.headers["X-CSRF-Token"] = csrf
    yield anon_client


@pytest.fixture()
def sample_accounts(client):  # async fixture chain handled in tests
    return {
        "cash": {"code": "1010", "name": "صندوق"},
        "equity": {"code": "3010", "name": "سرمایه اولیه"},
        "revenue": {"code": "4010", "name": "درآمد فروش"},
        "expense": {"code": "5040", "name": "اجاره"},
    }


@pytest.fixture()
def pdf_inspector():
    """Development-only parser shared by real native API and parser unit tests."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "pdf_native_smoke", REPO_ROOT / "scripts/pdf_native_smoke.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.inspect_pdf
