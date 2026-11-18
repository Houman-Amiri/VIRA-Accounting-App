"""Owner-defined pricing variables.

A constant is an amount he sets once; a variable is a number he re-enters per
job («نرخ دلار امروز»، «اجرت پرسنل»). Each variable says *how* it lands on the
price:

* جزیی (`PER_UNIT`) — on every piece;
* کلی (`PER_ORDER`) — once on the order, either added to the total
  (`ONE_TIME`) or spread over the quantity (`SPLIT`).

The settings page writes here; the calculator reads the defaults and lets the
owner retype the value for the job at hand.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.pricing import PricingVariable

PATH = "/api/v1/settings/pricing/variables"


async def _create(client, **body) -> dict:
    payload = {"name": "نرخ دلار", "scope": "PER_UNIT", "value": "1000", **(body or {})}
    response = await client.post(PATH, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- create ---
@pytest.mark.asyncio
async def test_a_new_variable_is_stored_and_listed(client, database) -> None:
    created = await _create(client)
    assert created["name"] == "نرخ دلار"
    assert created["scope"] == "PER_UNIT"
    assert created["basis"] == "AMOUNT"
    assert created["value"] == "1000.0000"
    assert created["is_active"] is True
    # a per-piece variable is always spread over the pieces
    assert created["allocation"] == "SPLIT"

    listed = await client.get(PATH)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [created["id"]]

    with database.session() as session:
        raw = session.execute(
            text("SELECT value, typeof(value), scope FROM pricing_variables")
        ).one()
        # Toman × 10 (Rial) × 10 000, stored as an exact integer
        assert raw == (100000000, "integer", "PER_UNIT")
        assert session.get(PricingVariable, created["id"]).value == Decimal("10000.0000")


@pytest.mark.asyncio
async def test_a_percent_variable_is_stored_exactly_as_given(client, database) -> None:
    created = await _create(client, name="درصد ضایعات", basis="PERCENT_OF_COST", value="4.5")
    assert created["value"] == "4.5000"
    with database.session() as session:
        assert session.get(PricingVariable, created["id"]).value == Decimal("4.5")


@pytest.mark.asyncio
async def test_a_whole_order_variable_keeps_the_chosen_allocation(client) -> None:
    one_time = await _create(
        client, name="مالیات", scope="PER_ORDER", basis="PERCENT_OF_PRICE",
        allocation="ONE_TIME", value="9",
    )
    split = await _create(
        client, name="اجرت پرسنل", scope="PER_ORDER", allocation="SPLIT", value="200000"
    )
    assert one_time["allocation"] == "ONE_TIME"
    assert split["allocation"] == "SPLIT"


@pytest.mark.asyncio
async def test_an_unknown_scope_or_basis_is_rejected(client) -> None:
    assert (
        await client.post(PATH, json={"name": "x", "scope": "PER_TEN", "value": "1"})
    ).status_code == 422
    assert (
        await client.post(
            PATH, json={"name": "x", "scope": "PER_UNIT", "basis": "MAGIC", "value": "1"}
        )
    ).status_code == 422


@pytest.mark.asyncio
async def test_the_name_cannot_be_blank(client) -> None:
    assert (
        await client.post(PATH, json={"name": "   ", "scope": "PER_UNIT", "value": "1"})
    ).status_code == 422


@pytest.mark.asyncio
async def test_two_variables_cannot_share_a_name(client) -> None:
    await _create(client)
    duplicate = await client.post(
        PATH, json={"name": "نرخ دلار", "scope": "PER_UNIT", "value": "2"}
    )
    assert duplicate.status_code == 400
    assert "نام" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_a_percent_variable_cannot_exceed_one_thousand(client) -> None:
    response = await client.post(
        PATH,
        json={"name": "درصد بزرگ", "scope": "PER_ORDER", "basis": "PERCENT_OF_PRICE", "value": "1001"},
    )
    assert response.status_code == 422


# ------------------------------------------------------------------- update ---
@pytest.mark.asyncio
async def test_the_value_and_scope_can_be_changed(client) -> None:
    created = await _create(client)
    response = await client.patch(
        f"{PATH}/{created['id']}", json={"value": "2500", "scope": "PER_ORDER"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["value"] == "2500.0000"
    assert body["scope"] == "PER_ORDER"
    assert body["name"] == created["name"]


@pytest.mark.asyncio
async def test_switching_a_variable_to_percent_reinterprets_the_value(client) -> None:
    created = await _create(client, value="50")
    body = (
        await client.patch(
            f"{PATH}/{created['id']}", json={"basis": "PERCENT_OF_PRICE", "value": "12.5"}
        )
    ).json()
    assert body["basis"] == "PERCENT_OF_PRICE"
    assert body["value"] == "12.5000"
    # and back again, without losing precision
    back = (await client.patch(f"{PATH}/{created['id']}", json={"basis": "AMOUNT"})).json()
    assert back["value"] == "12.5000"


@pytest.mark.asyncio
async def test_a_percentage_cannot_be_pushed_over_the_limit_by_a_patch(client) -> None:
    created = await _create(client, basis="PERCENT_OF_COST", value="10")
    response = await client.patch(f"{PATH}/{created['id']}", json={"value": "2000"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_a_variable_can_be_switched_off_without_deleting_it(client) -> None:
    created = await _create(client)
    response = await client.patch(f"{PATH}/{created['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert len((await client.get(PATH)).json()) == 1


@pytest.mark.asyncio
async def test_renaming_to_an_existing_name_is_refused(client) -> None:
    first = await _create(client, name="اول")
    await _create(client, name="دوم")
    assert (await client.patch(f"{PATH}/{first['id']}", json={"name": "دوم"})).status_code == 400


@pytest.mark.asyncio
async def test_updating_an_unknown_variable_is_a_404(client) -> None:
    assert (await client.patch(f"{PATH}/nope", json={"value": "1"})).status_code == 404


# ------------------------------------------------------------------- delete ---
@pytest.mark.asyncio
async def test_a_variable_can_be_removed(client) -> None:
    created = await _create(client)
    assert (await client.delete(f"{PATH}/{created['id']}")).status_code == 204
    assert (await client.get(PATH)).json() == []


@pytest.mark.asyncio
async def test_deleting_an_unknown_variable_is_a_404(client) -> None:
    assert (await client.delete(f"{PATH}/nope")).status_code == 404


# ------------------------------------------------------------------- access ---
@pytest.mark.asyncio
async def test_the_list_requires_a_signed_in_user(anon_client) -> None:
    assert (await anon_client.get(PATH)).status_code == 401


@pytest.mark.asyncio
async def test_writes_require_a_signed_in_user(anon_client) -> None:
    response = await anon_client.post(PATH, json={"name": "x", "scope": "PER_UNIT", "value": "1"})
    # CSRF runs before authentication on mutations
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_every_write_is_audited(client, database) -> None:
    created = await _create(client)
    await client.patch(f"{PATH}/{created['id']}", json={"value": "2"})
    await client.delete(f"{PATH}/{created['id']}")
    with database.session() as session:
        events = [
            row[0]
            for row in session.execute(
                text(
                    "SELECT event FROM security_audit_logs "
                    "WHERE event LIKE 'PRICING_VARIABLE_%' ORDER BY rowid"
                )
            ).all()
        ]
    assert events == [
        "PRICING_VARIABLE_CREATED",
        "PRICING_VARIABLE_UPDATED",
        "PRICING_VARIABLE_DELETED",
    ]
