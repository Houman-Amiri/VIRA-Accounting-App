"""SPA delivery guarantees — the v1.0.5 «changes not applied» incident.

v1.0.5 installed fresh code and fresh bundles, yet the browser kept serving the
cached ``index.html`` (the shell had no ``Cache-Control``) and the installer left
the previous hashed bundles in ``{app}\\static`` — the user saw the old UI and
«بررسی به‌روزرسانی» therefore looked like it had done nothing. These tests pin
the fix: the shell is never cacheable, hashed assets are immutable, deep links
reach the SPA, API 404s stay JSON, and the build id travels with the response.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

BUILD_ID = "abc1234"
MARKERS = ("chart-stock", "job-submit")


def _dist(tmp_path: Path) -> Path:
    dist = tmp_path / "static"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head>"
        f'<meta name="vira-build" content="{BUILD_ID}" />'
        "</head><body><div id=\"root\"></div>"
        f'<script type="module" src="/assets/index-{BUILD_ID}.js"></script>'
        "</body></html>",
        encoding="utf-8",
    )
    (dist / "assets" / f"index-{BUILD_ID}.js").write_text(
        "console.log('" + " ".join(MARKERS) + "');", encoding="utf-8"
    )
    return dist


@pytest.fixture()
def spa_app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, database) -> object:
    dist = _dist(tmp_path)
    monkeypatch.setenv("VIRA_STATIC_DIR", str(dist))
    monkeypatch.setenv("VIRA_SPA_BUILD", BUILD_ID)
    from app.main import create_app

    return create_app(database.settings)


@pytest.fixture()
async def spa_client(spa_app) -> Iterator:
    from httpx import ASGITransport, AsyncClient

    transport = ASGITransport(app=spa_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_shell_is_never_cacheable(spa_client) -> None:
    r = await spa_client.get("/")
    assert r.status_code == 200
    assert "no-store" in r.headers["cache-control"]
    assert r.headers["x-vira-spa-build"] == BUILD_ID
    assert f'content="{BUILD_ID}"' in r.text


async def test_shell_ignores_conditional_requests(spa_client) -> None:
    """A 304 would hand the browser its stale copy back — never do that."""
    r = await spa_client.get("/", headers={"If-None-Match": "*"})
    assert r.status_code == 200
    assert "no-store" in r.headers["cache-control"]


async def test_hashed_assets_are_immutable(spa_client) -> None:
    r = await spa_client.get(f"/assets/index-{BUILD_ID}.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]
    for marker in MARKERS:
        assert marker in r.text


async def test_deep_link_serves_the_shell(spa_client) -> None:
    for route in ("/warehouse", "/orders", "/production"):
        r = await spa_client.get(route)
        assert r.status_code == 200
        assert f'content="{BUILD_ID}"' in r.text
        assert "no-store" in r.headers["cache-control"]


async def test_unknown_api_path_stays_json(spa_client) -> None:
    r = await spa_client.get("/api/v1/definitely-not-a-route")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


async def test_spa_build_is_reported_by_the_status_api(spa_client) -> None:
    from app.version import version_info

    assert version_info()["spa_build"] == BUILD_ID
