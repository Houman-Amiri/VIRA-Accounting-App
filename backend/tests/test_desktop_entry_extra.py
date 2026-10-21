"""Additional synthetic browser/error contracts; never Windows/native proof."""

from __future__ import annotations

import logging

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
        # Synthetic-only event: actual Uvicorn startup must not close the app's
        # file handler. Before log_config=None this raises "write to closed file"
        # and prevents readiness (the native route catches it as HTML fallback).
        logging.getLogger("app.services.pdf_rendering").info(
            "synthetic_unit_lifecycle_not_native",
            extra={"pdf_document": {"event": "started", "id": "SYNTHETIC_UNIT_ONLY"}},
        )
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


def test_read_only_audit_then_lifetime_guard_before_native_activation():
    source = (basic.ROOT / "backend/app/desktop_entry.py").read_text(encoding="utf-8")
    audit = source.index('boot["prepare_private_plan"](plan)')
    guard = source.index('state_guard(root, state, boot["_no_links"]', audit)
    activate = source.index('boot["activate_private_source"](plan)', audit)
    assert audit < guard < activate
    assert 'installed_restart=options["role"] == "PRIVATE_INSTALLED_SOURCE_DESKTOP_REQUEST"' in source[guard:activate]
