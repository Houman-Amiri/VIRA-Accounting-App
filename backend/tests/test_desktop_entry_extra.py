"""Additional synthetic browser/error contracts; never Windows/native proof."""

from __future__ import annotations

import httpx
import pytest

from app import desktop_entry as entry

from . import test_desktop_entry as basic


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Update in progress; candidate startup blocked", "UPDATE_LOCK"),
        ("Independent desktop manifest mismatch", "MANIFEST_DIGEST"),
        ("Independent digest mismatch", "BOOTSTRAP_DIGEST"),
        ("credential: do not echo this value", "ValueError"),
    ],
)
def test_bounded_failure_diagnostics(message, expected):
    assert entry.failure_kind(ValueError(message)) == expected
    assert (
        entry.failure_kind(FileExistsError(17, "exists", "/private/.desktop.lock"))
        == "DESKTOP_INSTANCE_LOCK"
    )


def test_browser_attempt_only_after_actual_tcp_readiness(tmp_path, monkeypatch):
    opened = []

    def browser(url):
        with httpx.Client(base_url=url, trust_env=False) as http:
            assert http.get("/api/v1/health/live").json() == {"status": "alive"}
            assert http.get("/api/v1/health/ready").json()["status"] == "ready"
        opened.append(url)
        return True

    original = basic.options

    def options(state):
        value = original(state)
        value["no_browser"] = False
        return value

    monkeypatch.setattr(entry.webbrowser, "open", browser)
    monkeypatch.setattr(basic, "options", options)
    basic.test_linux_actual_migration_seed_tcp_ready_stop_restart(tmp_path, monkeypatch)
    assert len(opened) == 2
