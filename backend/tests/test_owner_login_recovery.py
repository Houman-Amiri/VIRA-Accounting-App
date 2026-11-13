"""The owner can always sign in.

The reported symptom was "there is no password and nothing I type works". Two
real states produced it:

* the database exists but has **no** user row (an interrupted first launch, or
  data carried over from a pre-rename install whose seeding never ran) — every
  password is refused and nothing in the interface can create an account;
* the owner forgot the generated password, and the only copy lived in a console
  banner from the very first run.

The fix is a pinned password file, ``%LOCALAPPDATA%\\NOA\\owner-password.txt``:
whatever it holds is applied on every application start, so the owner can close
NOA, put their own password in that file, start it again, and be certain it is
the password. The launcher itself is untouched (its bytes are pinned by the
Phase-2 evidence test).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import User
from app.security.passwords import verify_password
from app.seed import (
    PINNED_PASSWORD_FILENAME,
    apply_pinned_owner_password,
    ensure_owner_user,
    read_pinned_password,
    seed_all,
    write_pinned_password,
)


def _owner(session) -> User:
    row = session.scalar(select(User).where(User.username == "owner"))
    assert row is not None
    return row


def _settings_with_data_dir(settings, data_dir: Path):
    return settings.model_copy(update={"data_dir": data_dir})


def test_a_database_without_a_user_still_gets_an_owner(session) -> None:
    """The locked-door state: tables exist, no account to sign in with."""
    session.query(User).delete()
    session.flush()
    outcome = ensure_owner_user(session, password="pinned-pass-1", rotate=True)
    assert outcome["created"] is True
    assert verify_password("pinned-pass-1", _owner(session).password_hash)


def test_the_pinned_password_is_applied_over_a_forgotten_one(session) -> None:
    """owner-password.txt wins on every start, which is the recovery path."""
    session.query(User).delete()
    session.flush()
    ensure_owner_user(session, password="forgotten-pass", rotate=True)
    assert verify_password("forgotten-pass", _owner(session).password_hash)

    outcome = ensure_owner_user(session, password="540210.321", rotate=True)
    assert outcome["rotated"] is True
    assert verify_password("540210.321", _owner(session).password_hash)
    assert not verify_password("forgotten-pass", _owner(session).password_hash)


def test_the_same_pinned_password_is_not_rehashed_on_every_start(session) -> None:
    session.query(User).delete()
    session.flush()
    ensure_owner_user(session, password="540210.321", rotate=True)
    before = _owner(session).password_hash
    outcome = ensure_owner_user(session, password="540210.321", rotate=True)
    assert outcome["rotated"] is False
    assert _owner(session).password_hash == before


def test_a_disabled_or_demoted_owner_is_repaired(session) -> None:
    session.query(User).delete()
    session.flush()
    ensure_owner_user(session, password="pinned-pass-1", rotate=True)
    row = _owner(session)
    row.is_active = 0
    row.role = "AUDITOR"
    session.flush()
    ensure_owner_user(session, password="pinned-pass-1", rotate=True)
    row = _owner(session)
    assert row.is_active == 1 and row.role == "OWNER"


def test_seed_all_reports_what_it_did_and_keeps_the_pin(session) -> None:
    session.query(User).delete()
    session.flush()
    result = seed_all(session, admin_password="540210.321", pin_owner_password=True)
    assert result["owner_created"] == 1
    assert result["owner_password_rotated"] == 0
    assert verify_password("540210.321", _owner(session).password_hash)

    again = seed_all(session, admin_password="540210.321", pin_owner_password=True)
    assert again["owner_created"] == 0 and again["owner_password_rotated"] == 0


# ------------------------------------------------------------ the pinned file ---
def test_the_file_is_read_with_a_bom_and_trailing_blank_lines(database, tmp_path) -> None:
    """Notepad writes UTF-8 with a BOM; the BOM is not part of the password."""
    settings = _settings_with_data_dir(database.settings, tmp_path)
    (tmp_path / PINNED_PASSWORD_FILENAME).write_bytes(
        "\ufeff540210.321\n\n".encode("utf-8")
    )
    assert read_pinned_password(settings) == "540210.321"


def test_an_empty_file_falls_back_to_the_environment(database, tmp_path, monkeypatch) -> None:
    settings = _settings_with_data_dir(database.settings, tmp_path)
    (tmp_path / PINNED_PASSWORD_FILENAME).write_text("\n", encoding="utf-8")
    monkeypatch.setenv("NOA_OWNER_PASSWORD", "from-the-environment")
    assert read_pinned_password(settings) == "from-the-environment"
    monkeypatch.delenv("NOA_OWNER_PASSWORD")
    assert read_pinned_password(settings) is None


def test_startup_rotates_to_the_pinned_file(database, tmp_path) -> None:
    settings = _settings_with_data_dir(database.settings, tmp_path)
    write_pinned_password(settings, "540210.321")  # what the owner typed in Notepad

    outcome = apply_pinned_owner_password(settings)

    assert outcome["rotated"] is True
    with database.session() as session:
        assert verify_password("540210.321", _owner(session).password_hash)
        assert not verify_password("test-password-1", _owner(session).password_hash)


def test_startup_creates_a_missing_owner_and_records_the_password(database, tmp_path) -> None:
    settings = _settings_with_data_dir(database.settings, tmp_path)
    with database.session() as session:
        session.query(User).delete()
    assert not (tmp_path / PINNED_PASSWORD_FILENAME).exists()

    outcome = apply_pinned_owner_password(settings)

    assert outcome["created"] is True
    saved = (tmp_path / PINNED_PASSWORD_FILENAME).read_text(encoding="utf-8").strip()
    assert len(saved) >= 8
    with database.session() as session:
        assert verify_password(saved, _owner(session).password_hash)


def test_startup_leaves_a_working_password_alone_when_no_file_exists(database, tmp_path) -> None:
    """An upgrade must never silently replace a password that still works."""
    settings = _settings_with_data_dir(database.settings, tmp_path)

    outcome = apply_pinned_owner_password(settings)

    assert outcome == {"created": False, "rotated": False, "username": "owner"}
    with database.session() as session:
        assert verify_password("test-password-1", _owner(session).password_hash)
    assert not (tmp_path / PINNED_PASSWORD_FILENAME).exists()


# ----------------------------------------------------------------- end to end ---
@pytest.mark.asyncio
async def test_the_running_app_applies_the_file_before_the_first_login_attempt(
    database, tmp_path
) -> None:
    """The real path: start the app with the pinned file present, then log in."""
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    settings = _settings_with_data_dir(database.settings, tmp_path)
    write_pinned_password(settings, "540210.321")
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            rejected = await client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "test-password-1"},
            )
            assert rejected.status_code == 401
            accepted = await client.post(
                "/api/v1/auth/login",
                json={"username": "owner", "password": "540210.321"},
            )
            assert accepted.status_code == 200, accepted.text


def test_the_helper_opens_the_pinned_file_without_typing_a_path() -> None:
    """A non-technical route to the password: double-click, type, save, restart."""
    helper = (Path(__file__).resolve().parents[2] / "scripts" / "set_owner_password.cmd")
    text = helper.read_text(encoding="utf-8")
    assert 'set "NOA_DATA=%LOCALAPPDATA%\\NOA"' in text
    assert "set \"NOA_FILE=%NOA_DATA%\\owner-password.txt\"" in text
    assert 'start "" notepad' in text
    # it must not put a placeholder in the file: an empty file means "no pin",
    # while a template string would silently become the password
    assert "password=" not in text.lower()
