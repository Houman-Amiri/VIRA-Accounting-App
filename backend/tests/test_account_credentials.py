"""Changing your own password and login name from the settings screen.

Until v1.0.16 the login password was created once, on the first start, and could
not be replaced from inside the app at all; the owner's only route was an
offline script. These tests pin the rules of the two new routes:

* the current password is required — a stolen session cookie alone changes
  nothing;
* the new password must differ from the old one and be long enough;
* the login name must be a plain identifier and must not collide with an
  existing account (case-insensitively);
* the caller's own session keeps working, and the token carries the *new* name
  immediately;
* every attempt that matters is in the security trail, without any password.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

OWNER_PASSWORD = "test-password-1"


async def _security_events(database, event: str) -> list[dict]:
    from app.models import SecurityAuditLog

    with database.session() as session:
        rows = session.scalars(
            select(SecurityAuditLog).where(SecurityAuditLog.event == event)
        ).all()
        return [{"id": row.id, "detail": row.detail} for row in rows]


async def test_the_owner_can_change_their_password_and_log_in_with_it(client, anon_client) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": "540210.321"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "owner"

    # the old password is gone, the new one works
    assert (
        await anon_client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": OWNER_PASSWORD}
        )
    ).status_code == 401
    fresh = await anon_client.post(
        "/api/v1/auth/login", json={"username": "owner", "password": "540210.321"}
    )
    assert fresh.status_code == 200, fresh.text


async def test_the_caller_stays_signed_in_after_the_change(client) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": "a-longer-password"},
    )
    assert response.status_code == 200
    # the route re-issues the session pair, so the tab that made the change keeps working
    assert response.cookies.get("noa_session")
    assert (await client.get("/api/v1/auth/me")).status_code == 200


async def test_a_wrong_current_password_changes_nothing(client) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-my-password", "new_password": "a-longer-password"},
    )
    assert response.status_code == 403
    assert response.json()["code"] == "wrong_password"
    assert "رمز فعلی" in response.json()["detail"]
    # the stored password is untouched
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": OWNER_PASSWORD},
        )
    ).status_code == 200


@pytest.mark.parametrize("new_password", ["short", "short12"])
async def test_a_short_password_is_refused_by_the_contract(client, new_password: str) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": new_password},
    )
    assert response.status_code == 422
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": OWNER_PASSWORD},
        )
    ).status_code == 200


async def test_keeping_the_same_password_is_refused(client) -> None:
    response = await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": OWNER_PASSWORD},
    )
    assert response.status_code == 400
    assert "یکسان" in response.json()["detail"]


async def test_a_stolen_session_cannot_change_the_password_without_it(client, anon_client) -> None:
    """The route is cookie-authenticated; the current password is the real lock."""
    response = await anon_client.post(
        "/api/v1/auth/password",
        json={"current_password": "guessed", "new_password": "attacker-password"},
        headers={"X-CSRF-Token": client.headers["X-CSRF-Token"]},
    )
    assert response.status_code == 403
    assert (
        await client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": OWNER_PASSWORD},
        )
    ).status_code == 200


async def test_the_new_password_is_never_written_to_the_security_trail(client, database) -> None:
    await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": "540210.321"},
    )
    await client.post(
        "/api/v1/auth/password",
        json={"current_password": "wrong-guess", "new_password": "x" * 12},
    )
    changed = await _security_events(database, "PASSWORD_CHANGED")
    failed = await _security_events(database, "PASSWORD_CHANGE_FAILED")
    assert len(changed) == 1 and len(failed) == 1
    for event in [*changed, *failed]:
        assert "540210.321" not in (event["detail"] or "")
        assert "wrong-guess" not in (event["detail"] or "")


async def test_the_owner_can_rename_the_login_to_NOA(client, anon_client) -> None:
    response = await client.put(
        "/api/v1/auth/username",
        json={"username": "NOA", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200, response.text
    assert response.json()["username"] == "NOA"
    # the header reads the session token, so it must carry the new name at once
    assert (await client.get("/api/v1/auth/me")).json()["username"] == "NOA"
    # the old name no longer signs in, the new one does with the same password
    assert (
        await anon_client.post(
            "/api/v1/auth/login", json={"username": "owner", "password": OWNER_PASSWORD}
        )
    ).status_code == 401
    assert (
        await anon_client.post(
            "/api/v1/auth/login", json={"username": "NOA", "password": OWNER_PASSWORD}
        )
    ).status_code == 200


async def test_a_rename_needs_the_current_password(client) -> None:
    response = await client.put(
        "/api/v1/auth/username",
        json={"username": "NOA", "password": "not-my-password"},
    )
    assert response.status_code == 403
    assert (await client.get("/api/v1/auth/me")).json()["username"] == "owner"


@pytest.mark.parametrize("wanted", ["a", "with space", "semi;colon", "یوزر"])
async def test_a_name_that_is_not_an_identifier_is_refused(client, wanted: str) -> None:
    response = await client.put(
        "/api/v1/auth/username",
        json={"username": wanted, "password": OWNER_PASSWORD},
    )
    assert response.status_code in (400, 422), response.text
    assert (await client.get("/api/v1/auth/me")).json()["username"] == "owner"


async def test_two_accounts_cannot_share_a_name_even_in_a_different_case(client, database) -> None:
    from app.ids import utc_now_iso, uuid7
    from app.models import User
    from app.security.passwords import hash_password

    with database.session() as session:
        session.add(
            User(
                id=uuid7(),
                username="auditor",
                password_hash=hash_password("auditor-password"),
                role="AUDITOR",
                is_active=1,
                created_at=utc_now_iso(),
            )
        )
    response = await client.put(
        "/api/v1/auth/username",
        json={"username": "AUDITOR", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 409
    assert response.json()["code"] == "username_taken"


async def test_renaming_to_your_own_name_is_harmless(client) -> None:
    response = await client.put(
        "/api/v1/auth/username",
        json={"username": "owner", "password": OWNER_PASSWORD},
    )
    assert response.status_code == 200
    assert response.json()["username"] == "owner"


async def test_both_routes_need_a_session_and_a_csrf_token(anon_client) -> None:
    password = await anon_client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": "a-longer-password"},
    )
    # csrf runs before authentication, so an anonymous write is refused by one
    # of the two guards — never accepted
    assert password.status_code in (401, 403)
    rename = await anon_client.put(
        "/api/v1/auth/username", json={"username": "NOA", "password": OWNER_PASSWORD}
    )
    assert rename.status_code in (401, 403)


async def test_the_write_routes_reject_a_missing_csrf_header(client) -> None:
    client.headers.pop("X-CSRF-Token")
    password = await client.post(
        "/api/v1/auth/password",
        json={"current_password": OWNER_PASSWORD, "new_password": "a-longer-password"},
    )
    assert password.status_code == 403
    rename = await client.put(
        "/api/v1/auth/username", json={"username": "NOA", "password": OWNER_PASSWORD}
    )
    assert rename.status_code == 403
