"""Owner-defined pricing constants.

The seven built-in constants mirror `قیمت نهایی.xlsx` and stay fixed. These are
the ones the owner adds himself («هزینهٔ بسته‌بندی»، «کارمزد پست»، …) together
with the method that says how each becomes money. The endpoint is what the
«قیمت‌گذاری» page writes to.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.models.pricing import PricingCustomConstant

PATH = "/api/v1/settings/pricing/constants"


async def _create(client, **body) -> dict:
    payload = {"name": "هزینهٔ بسته‌بندی", "method": "PER_UNIT", "value": "1500", **body}
    response = await client.post(PATH, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


# ------------------------------------------------------------------- create ---
@pytest.mark.asyncio
async def test_a_new_constant_is_stored_and_listed(client, database) -> None:
    created = await _create(client)
    assert created["name"] == "هزینهٔ بسته‌بندی"
    assert created["method"] == "PER_UNIT"
    assert created["value"] == "1500.0000"
    assert created["is_active"] is True

    listed = await client.get(PATH)
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [created["id"]]

    with database.session() as session:
        raw = session.execute(
            text("SELECT value, typeof(value), method FROM pricing_custom_constants")
        ).one()
        # Toman × 10 (Rial) × 10 000, stored as an exact integer
        assert raw == (150000000, "integer", "PER_UNIT")
        assert session.get(PricingCustomConstant, created["id"]).value == Decimal("15000.0000")


@pytest.mark.asyncio
async def test_all_four_calculation_methods_are_accepted(client) -> None:
    for index, method in enumerate(
        ["PER_UNIT", "PER_BATCH", "PERCENT_OF_COST", "PERCENT_OF_PRICE"]
    ):
        created = await _create(client, name=f"ثابت {index}", method=method, value="10")
        assert created["method"] == method
    assert len((await client.get(PATH)).json()) == 4


@pytest.mark.asyncio
async def test_an_unknown_method_is_rejected(client) -> None:
    response = await client.post(
        PATH, json={"name": "x", "method": "PER_MAGIC", "value": "1"}
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_the_name_cannot_be_blank(client) -> None:
    response = await client.post(PATH, json={"name": "   ", "method": "PER_UNIT", "value": "1"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_two_constants_cannot_share_a_name(client) -> None:
    await _create(client)
    duplicate = await client.post(
        PATH, json={"name": "هزینهٔ بسته‌بندی", "method": "PER_UNIT", "value": "2"}
    )
    assert duplicate.status_code == 400
    assert "نام" in duplicate.json()["detail"]


@pytest.mark.asyncio
async def test_a_percent_method_cannot_exceed_one_thousand(client) -> None:
    response = await client.post(
        PATH, json={"name": "درصد بزرگ", "method": "PERCENT_OF_COST", "value": "1001"}
    )
    assert response.status_code == 422


# ------------------------------------------------------------------- update ---
@pytest.mark.asyncio
async def test_the_method_and_value_can_be_changed(client) -> None:
    created = await _create(client)
    response = await client.patch(
        f"{PATH}/{created['id']}",
        json={"method": "PERCENT_OF_PRICE", "value": "12.5"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["method"] == "PERCENT_OF_PRICE"
    assert body["value"] == "12.5000"
    # the name is untouched by a partial update
    assert body["name"] == created["name"]


@pytest.mark.asyncio
async def test_a_constant_can_be_switched_off_without_deleting_it(client) -> None:
    created = await _create(client)
    response = await client.patch(f"{PATH}/{created['id']}", json={"is_active": False})
    assert response.status_code == 200
    assert response.json()["is_active"] is False
    assert len((await client.get(PATH)).json()) == 1


@pytest.mark.asyncio
async def test_renaming_to_an_existing_name_is_refused(client) -> None:
    first = await _create(client, name="اول")
    await _create(client, name="دوم")
    response = await client.patch(f"{PATH}/{first['id']}", json={"name": "دوم"})
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_updating_an_unknown_constant_is_a_404(client) -> None:
    response = await client.patch(f"{PATH}/nope", json={"value": "1"})
    assert response.status_code == 404


# ------------------------------------------------------------------- delete ---
@pytest.mark.asyncio
async def test_a_constant_can_be_removed(client) -> None:
    created = await _create(client)
    response = await client.delete(f"{PATH}/{created['id']}")
    assert response.status_code == 204
    assert (await client.get(PATH)).json() == []


@pytest.mark.asyncio
async def test_deleting_an_unknown_constant_is_a_404(client) -> None:
    assert (await client.delete(f"{PATH}/nope")).status_code == 404


# ------------------------------------------------------------------- access ---
@pytest.mark.asyncio
async def test_the_list_requires_a_signed_in_user(anon_client) -> None:
    assert (await anon_client.get(PATH)).status_code == 401


@pytest.mark.asyncio
async def test_writes_require_a_signed_in_user(anon_client) -> None:
    response = await anon_client.post(
        PATH, json={"name": "x", "method": "PER_UNIT", "value": "1"}
    )
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
                    "WHERE event LIKE 'PRICING_CONSTANT_%' ORDER BY rowid"
                )
            ).all()
        ]
    assert events == [
        "PRICING_CONSTANT_CREATED",
        "PRICING_CONSTANT_UPDATED",
        "PRICING_CONSTANT_DELETED",
    ]
