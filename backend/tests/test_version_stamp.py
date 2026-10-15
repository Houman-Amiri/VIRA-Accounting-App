"""Build provenance (System & Operations «نسخه/کامیت») — installed-payload path.

The installed app has no distribution metadata and no ``.git``, so the shipped
``version.json`` must win. Regression test for the v1.0.5 fix that removed
«نسخه: 0.0.0-unknown / کامیت: unknown» from a real installation.
"""

from __future__ import annotations

import importlib
import json

import pytest


def _reload(monkeypatch: pytest.MonkeyPatch, tmp_path, **env: str) -> object:
    for key in ("VIRA_VERSION", "VIRA_GIT_COMMIT", "VIRA_BUILT_AT", "VIRA_APP_DIR"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = importlib.import_module("app.version")
    module = importlib.reload(module)
    return module


def test_version_json_stamp_wins_in_installed_payload(monkeypatch, tmp_path) -> None:
    app_dir = tmp_path / "VIRA"
    app_dir.mkdir()
    (app_dir / "version.json").write_text(
        json.dumps({"version": "1.0.5", "commit": "abc1234", "built_at": "2026-10-15T00:00:00Z"}),
        encoding="utf-8",
    )
    module = _reload(monkeypatch, tmp_path, VIRA_APP_DIR=str(app_dir))
    info = module.version_info()
    assert info["version"] == "1.0.5"
    assert info["commit"] == "abc1234"
    assert info["built_at"] == "2026-10-15T00:00:00Z"


def test_env_beats_stamp(monkeypatch, tmp_path) -> None:
    app_dir = tmp_path / "VIRA"
    app_dir.mkdir()
    (app_dir / "version.json").write_text(
        json.dumps({"version": "1.0.5", "commit": "abc1234"}), encoding="utf-8"
    )
    module = _reload(
        monkeypatch,
        tmp_path,
        VIRA_APP_DIR=str(app_dir),
        VIRA_VERSION="9.9.9",
        VIRA_GIT_COMMIT="deadbee",
    )
    info = module.version_info()
    assert info["version"] == "9.9.9"
    assert info["commit"] == "deadbee"


def test_no_stamp_never_crashes(monkeypatch, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(empty)
    module = _reload(monkeypatch, tmp_path, VIRA_APP_DIR=str(empty))
    info = module.version_info()
    assert isinstance(info["version"], str) and info["version"]
    assert isinstance(info["commit"], str) and info["commit"]


def test_broken_stamp_is_ignored(monkeypatch, tmp_path) -> None:
    app_dir = tmp_path / "VIRA"
    app_dir.mkdir()
    (app_dir / "version.json").write_text("{ not json", encoding="utf-8")
    monkeypatch.chdir(app_dir)
    module = _reload(monkeypatch, tmp_path, VIRA_APP_DIR=str(app_dir))
    info = module.version_info()
    assert info["version"]  # falls back to metadata/unknown, never raises
    assert info["commit"]
