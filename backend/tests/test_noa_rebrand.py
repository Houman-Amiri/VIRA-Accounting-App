"""The NOA rebrand: visible names, on-disk migration, and no leftover brand.

The rename touched the brand, the environment prefix and the data folder at the
same time, so these tests pin the three things that could silently lose the
owner's data or break an upgrade: the printed name, the one-time copy of the old
data folder, and the frozen names of already-published releases.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.config import (
    LEGACY_APP_DIR_NAME,
    LEGACY_CSRF_COOKIE_NAME,
    LEGACY_DATABASE_FILENAME,
    LEGACY_SESSION_COOKIE_NAME,
    Settings,
    migrate_legacy_data_dir,
)
from app.security.session import LEGACY_SESSION_SALT

ROOT = Path(__file__).resolve().parents[2]
# Self-reported version of the pre-rename native PDF source build (frozen artifact).
FROZEN_NATIVE_SOURCE_VERSION = "1.58.0-vira-local-source"


def _legacy_tree(root: Path) -> Path:
    """A pre-rename data folder with a ledger database and a receipt."""
    legacy = root / LEGACY_APP_DIR_NAME
    (legacy / "data").mkdir(parents=True)
    (legacy / "data" / LEGACY_DATABASE_FILENAME).write_bytes(b"SQLite format 3\x00ledger")
    (legacy / "data" / f"{LEGACY_DATABASE_FILENAME}-wal").write_bytes(b"wal")
    (legacy / "receipt_storage").mkdir()
    (legacy / "receipt_storage" / "receipt.bin").write_bytes(b"receipt bytes")
    (legacy / "updates").mkdir()
    (legacy / "updates" / "last-result.json").write_text('{"state": "committed"}', encoding="utf-8")
    return legacy


def test_legacy_data_is_copied_under_the_new_folder_and_database_name(tmp_path: Path) -> None:
    legacy = _legacy_tree(tmp_path)
    target = tmp_path / "NOA"

    assert migrate_legacy_data_dir(target) == legacy

    assert (target / "data" / "noa.sqlite3").read_bytes() == b"SQLite format 3\x00ledger"
    assert (target / "data" / "noa.sqlite3-wal").read_bytes() == b"wal"
    assert (target / "receipt_storage" / "receipt.bin").read_bytes() == b"receipt bytes"
    assert (target / "updates" / "last-result.json").is_file()
    # The old folder is the owner's safety net: never modified, never deleted.
    assert (legacy / "data" / LEGACY_DATABASE_FILENAME).is_file()
    assert (legacy / "receipt_storage" / "receipt.bin").is_file()


def test_existing_new_data_is_never_overwritten(tmp_path: Path) -> None:
    _legacy_tree(tmp_path)
    target = tmp_path / "NOA"
    (target / "data").mkdir(parents=True)
    (target / "data" / "noa.sqlite3").write_bytes(b"the database already in use")

    assert migrate_legacy_data_dir(target) is None
    assert (target / "data" / "noa.sqlite3").read_bytes() == b"the database already in use"


def test_nothing_happens_without_a_legacy_folder(tmp_path: Path) -> None:
    target = tmp_path / "NOA"
    assert migrate_legacy_data_dir(target) is None
    assert not target.exists()


def test_migration_is_idempotent(tmp_path: Path) -> None:
    _legacy_tree(tmp_path)
    target = tmp_path / "NOA"
    assert migrate_legacy_data_dir(target) is not None
    assert migrate_legacy_data_dir(target) is None  # second run is a no-op
    assert sorted(p.name for p in target.iterdir()) == ["data", "receipt_storage", "updates"]


def test_default_settings_use_the_new_folder_without_touching_an_explicit_path(
    tmp_path: Path,
) -> None:
    legacy = _legacy_tree(tmp_path)
    settings = Settings(environment="development", data_dir=tmp_path / "explicit")
    assert settings.data_dir == tmp_path / "explicit"
    # An explicit data_dir must not trigger the machine-wide migration.
    assert (legacy / "data" / LEGACY_DATABASE_FILENAME).is_file()
    assert not (tmp_path / "NOA").exists()


def test_printed_documents_carry_the_new_name_and_not_the_old_one() -> None:
    from app.services.pdf import render_html

    html = render_html(
        "invoice.html",
        {
            "invoice": {
                "kind": "sale",
                "buyer": "خریدار",
                "lines": [
                    {"title": "قطعه", "quantity": "1.0000", "unit_price": "1000.0000",
                     "line_total": "1000.0000"}
                ],
                "total": "1000.0000",
            },
            "entry_number": 1,
            "transaction_date": "2026-11-01",
            "company": {"name": "NOA", "tagline": "چاپ سه‌بعدی و فروش محصولات"},
        },
    )
    assert '<div class="brand-name">NOA</div>' in html
    assert "V.I.R.A" not in html


def test_no_user_visible_string_still_says_the_old_brand() -> None:
    """Runtime code must not print the retired name anywhere the owner can see."""
    suspects = [
        *sorted((ROOT / "backend/app").rglob("*.py")),
        *sorted((ROOT / "backend/app/templates").rglob("*.html")),
        *sorted((ROOT / "frontend/src").rglob("*.ts")),
        *sorted((ROOT / "frontend/src").rglob("*.tsx")),
        *sorted((ROOT / "frontend/src/locales").rglob("*.json")),
        (ROOT / "frontend/index.html"),
    ]
    offenders: list[str] = []
    for path in suspects:
        text = path.read_text(encoding="utf-8")
        # The historical identifiers are deliberately kept (see config.py).
        text = text.replace(LEGACY_DATABASE_FILENAME, "").replace(LEGACY_APP_DIR_NAME, "")
        # The private native PDF kit is a real compiled artifact published before
        # the rename; its self-reported version string cannot be changed without
        # invalidating the recorded native audit, so it keeps the old spelling.
        text = text.replace(FROZEN_NATIVE_SOURCE_VERSION, "")
        # The pre-rename root file names must still be named, because the upgrade
        # package has to delete exactly them (see update_staging.INSTALL_FILES).
        text = text.replace("start_vira.cmd", "").replace("vira-updater.exe", "")
        # The retired cookie names are read once, for the upgrade (see config.py).
        text = text.replace(LEGACY_SESSION_COOKIE_NAME, "").replace(LEGACY_CSRF_COOKIE_NAME, "")
        # ... and the retired signing salt, so an open session keeps working.
        text = text.replace(LEGACY_SESSION_SALT, "")
        text = text.replace("VIRA-Accounting-App", "")  # the GitHub slug, unrenamed
        if re.search(r"V\.I\.R\.A|VIRA|Vira|vira|ویرا(?!ی)", text):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []


def test_the_installer_moves_to_the_new_folder_and_keeps_upgrade_identity() -> None:
    iss = (ROOT / "installer/noa.iss").read_text(encoding="utf-8")
    assert 'OutputBaseFilename=NOA-Setup-{#AppVersion}' in iss
    assert "DefaultDirName=D:\\3D PRINT\\NOA-Accounting" in iss
    # Without this, Inno quietly reuses the pre-rename folder and the move fails.
    assert "UsePreviousAppDir=no" in iss
    # Same product identity: one entry in Add/Remove Programs, not two apps.
    assert "AppId={{B7E4C2A1-9F3D-4E8B-A6C5-1D2E3F405968}" in iss
    assert 'AppName "NOA"' in iss


def test_published_releases_keep_their_original_asset_names() -> None:
    """A pinned historical client is still downloadable by its published name."""
    import importlib
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    harness = importlib.import_module("scripts.update_native_smoke")
    urls = harness.published_base_urls("owner/repo")
    assert any("/NOA-v1.0.9-app.zip" not in url and "noa-v1.0.9-app.zip" in url for url in urls)
    assert any("vira-v1.0.9-app.zip" in url for url in urls)

    deltas = (ROOT / "scripts/build_deltas.ps1").read_text(encoding="utf-8")
    assert "vira-v$BaseV-app.zip" in deltas and "noa-v$BaseV-app.zip" in deltas


def _delta_fixture(tmp_path: Path, *extra: str) -> dict:
    """Build a real delta ZIP with the real generator, as the release pipeline does."""
    import json
    import subprocess
    import sys

    from app.services.update_engine import build_manifest, manifest_to_json

    base, target = tmp_path / "base", tmp_path / "target"
    for root, version in ((base, "1.0.14"), (target, "1.0.15")):
        (root / "app").mkdir(parents=True)
        (root / "app" / "module.py").write_bytes(b"print('x')\n" * 40)
        (root / "version.json").write_text(json.dumps({"version": version}), encoding="utf-8")
        (root / "noa-updater.exe").write_bytes(b"MZ-fixture-helper")
    manifest = base / "install_manifest.json"
    manifest.write_text(json.dumps(manifest_to_json(build_manifest(base))), encoding="utf-8")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "gen_delta.py"),
            "--base-manifest", str(manifest),
            "--base-dir", str(base),
            "--target-dir", str(target),
            "--base-version", "1.0.14",
            "--target-version", "1.0.15",
            "--out", str(tmp_path),
            "--patch-threshold", "100",
            *extra,
        ],
        check=True,
        capture_output=True,
    )
    import zipfile

    with zipfile.ZipFile(tmp_path / "NOA-v1.0.15-delta-from-v1.0.14.zip") as zf:
        return {"names": set(zf.namelist()), "doc": json.loads(zf.read("update.json"))}


def test_delta_carries_the_helper_under_both_names_for_pre_rename_clients(tmp_path: Path) -> None:
    """A 1.0.14 client refuses a package without vira-updater.exe; same bytes, both names."""
    built = _delta_fixture(tmp_path, "--compat-helper")
    assert "noa-updater.exe" in built["names"] and "vira-updater.exe" in built["names"]
    assert built["doc"]["hashes"]["noa-updater.exe"] == built["doc"]["hashes"]["vira-updater.exe"]


def test_delta_without_the_compat_flag_ships_only_the_current_helper(tmp_path: Path) -> None:
    built = _delta_fixture(tmp_path)
    assert "noa-updater.exe" in built["names"]
    assert "vira-updater.exe" not in built["names"]


def test_pre_rename_deltas_are_built_but_never_advertised() -> None:
    """A v1.0.14 client cannot install a renamed payload, so it must get the setup.

    Its own allowlist only accepts start_vira.cmd / vira-updater.exe, so the delta
    from those bases is still built (the release gates need a real package) but it
    is never written into latest.json — otherwise the client downloads a package it
    is guaranteed to reject.
    """
    text = (ROOT / "scripts/build_deltas.ps1").read_text(encoding="utf-8")
    assert '$FirstRenamedClient = [version]"1.0.15"' in text
    assert "if ([version]$baseV -ge $FirstRenamedClient) {" in text
    assert "NOT ADVERTISED" in text
    # Building is still mandatory: the gates and the Windows smoke need the ZIPs.
    assert "$built -eq 0 -and $probeHit" in text


def test_helper_can_travel_inside_a_package_built_for_a_pre_rename_target(tmp_path: Path) -> None:
    """A pre-rename target cannot hold the renamed helper at its root.

    The pinned 1.0.9/1.0.10 clients reject any operation on a renamed root file,
    so the compiled helper is supplied with --helper-file and travels as a package
    member the old client installs under its own name.
    """
    import json
    import subprocess
    import sys
    import zipfile

    from app.services.update_engine import build_manifest, manifest_to_json

    base, target = tmp_path / "base", tmp_path / "target"
    (base / "app").mkdir(parents=True)
    (base / "app" / "main.py").write_bytes(b"old\n" * 60)
    (base / "version.json").write_text(json.dumps({"version": "1.0.9"}), encoding="utf-8")
    (base / "start_vira.cmd").write_bytes(b"@echo off\nold\n")
    manifest = base / "install_manifest.json"
    manifest.write_text(json.dumps(manifest_to_json(build_manifest(base))), encoding="utf-8")
    (target / "app").mkdir(parents=True)
    (target / "app" / "main.py").write_bytes(b"new\n" * 60)
    (target / "version.json").write_text(json.dumps({"version": "1.0.15"}), encoding="utf-8")
    (target / "start_vira.cmd").write_bytes(b"@echo off\nnew\n")
    helper = tmp_path / "helper.exe"
    helper.write_bytes(b"MZ-real-compiled-helper")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "gen_delta.py"),
            "--base-manifest", str(manifest),
            "--base-dir", str(base),
            "--target-dir", str(target),
            "--base-version", "1.0.9",
            "--target-version", "1.0.15",
            "--out", str(tmp_path / "out"),
            "--compat-helper",
            "--helper-file", str(helper),
        ],
        check=True,
        capture_output=True,
    )
    with zipfile.ZipFile(tmp_path / "out" / "NOA-v1.0.15-delta-from-v1.0.9.zip") as zf:
        doc = json.loads(zf.read("update.json"))
        assert zf.read("vira-updater.exe") == b"MZ-real-compiled-helper"
        assert zf.read("noa-updater.exe") == b"MZ-real-compiled-helper"
    assert doc["hashes"]["vira-updater.exe"] == doc["hashes"]["noa-updater.exe"]
    # Nothing at the target root carries the renamed name, so an old client accepts it.
    assert not any(op["path"] == "noa-updater.exe" for op in doc["operations"])
    assert "start_noa.cmd" not in {op["path"] for op in doc["operations"]}


def test_the_helper_restarts_a_pre_rename_launcher_after_upgrade_or_rollback() -> None:
    """The relaunched old launcher must not abort on its own update lock.

    A pre-rename client's launcher exits with "Update in progress" unless ITS
    restart variable is set, and it reads its own port variable. Both are set, so
    an upgrade of such an install (and a rollback to it) really starts the app.
    """
    text = (ROOT / "scripts/noa_updater.ps1").read_text(encoding="utf-8")
    assert '$env:VIRA_UPDATE_RESTART = "1"' in text
    assert '$env:NOA_UPDATE_RESTART = "1"' in text
    assert 'elseif ($env:VIRA_PORT)' in text
    # and it must fall back to the old launcher name when the new one is absent
    assert 'Join-Path $InstallDir "start_vira.cmd"' in text


def test_a_delta_that_renames_an_existing_install_passes_the_shipped_validator(
    tmp_path: Path,
) -> None:
    """The package that removes start_vira.cmd / vira-updater.exe must be valid.

    Pre-rename installs hold those two files at their root, so the upgrade package
    deletes them. The shipped staging validator has to accept exactly those names
    (and still refuse anything else outside the application folders).
    """
    import json
    import subprocess
    import sys
    import zipfile

    from app.services.update_engine import build_manifest, manifest_to_json
    from app.services.update_staging import extract_delta

    base, target = tmp_path / "base", tmp_path / "target"
    (base / "app").mkdir(parents=True)
    (base / "app" / "main.py").write_bytes(b"old\n" * 60)
    (base / "version.json").write_text(json.dumps({"version": "1.0.14"}), encoding="utf-8")
    (base / "start_vira.cmd").write_bytes(b"@echo off\nold launcher\n")
    (base / "vira-updater.exe").write_bytes(b"MZ-old-helper")
    manifest = base / "install_manifest.json"
    manifest.write_text(json.dumps(manifest_to_json(build_manifest(base))), encoding="utf-8")
    (target / "app").mkdir(parents=True)
    (target / "app" / "main.py").write_bytes(b"new\n" * 60)
    (target / "version.json").write_text(json.dumps({"version": "1.0.15"}), encoding="utf-8")
    (target / "start_noa.cmd").write_bytes(b"@echo off\nnew launcher\n")
    (target / "noa-updater.exe").write_bytes(b"MZ-new-helper")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "gen_delta.py"),
            "--base-manifest", str(manifest),
            "--base-dir", str(base),
            "--target-dir", str(target),
            "--base-version", "1.0.14",
            "--target-version", "1.0.15",
            "--out", str(tmp_path / "out"),
            "--compat-helper",
        ],
        check=True,
        capture_output=True,
    )
    archive = tmp_path / "out" / "NOA-v1.0.15-delta-from-v1.0.14.zip"
    with zipfile.ZipFile(archive) as zf:
        ops = json.loads(zf.read("update.json"))["operations"]
    deleted = {op["path"] for op in ops if op["op"] == "delete"}
    assert {"start_vira.cmd", "vira-updater.exe"} <= deleted
    # The shipped validator accepts it; nothing is written outside the app folders.
    extract_delta(archive, tmp_path / "payload", "1.0.14", "1.0.15")
    assert (tmp_path / "payload" / "files" / "start_noa.cmd").is_file()


def test_an_existing_session_survives_the_rename(database) -> None:
    """The upgrade must not log the owner out: the old cookie carries the same token."""
    from fastapi.testclient import TestClient

    from app.config import LEGACY_CSRF_COOKIE_NAME, LEGACY_SESSION_COOKIE_NAME
    from app.main import create_app

    app = create_app(database.settings)  # conftest seeds the owner account
    with TestClient(app) as client:
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "owner", "password": "test-password-1"},
        )
        assert login.status_code == 200
        token = client.cookies.get(database.settings.session_cookie_name)
        csrf = login.json()["csrf_token"]
        assert token

    # The pre-rename client would present the same values under the old names.
    legacy_cookies = {LEGACY_SESSION_COOKIE_NAME: token, LEGACY_CSRF_COOKIE_NAME: csrf}
    with TestClient(app, cookies=legacy_cookies) as legacy:
        who = legacy.get("/api/v1/auth/me")
        assert who.status_code == 200, who.text
        assert who.json()["username"] == "owner"
        legacy.headers["X-CSRF-Token"] = csrf
        assert legacy.post("/api/v1/auth/logout").status_code in (200, 204)

    # A token the pre-rename app signed (old salt AND old cookie name) still works.
    from itsdangerous import URLSafeTimedSerializer

    legacy_token = URLSafeTimedSerializer(
        database.settings.session_secret, salt=LEGACY_SESSION_SALT
    ).dumps({"uid": who.json()["user_id"], "username": "owner", "role": "OWNER"})
    with TestClient(app, cookies={LEGACY_SESSION_COOKIE_NAME: legacy_token}) as old_client:
        assert old_client.get("/api/v1/auth/me").status_code == 200

    # The tab no longer needs the old names: the next response re-issues the new
    # pair, which is what the renamed SPA reads its CSRF token from.
    with TestClient(app, cookies=legacy_cookies) as promoted:
        page = promoted.get("/")
        issued = {c.split("=", 1)[0]: c for c in page.headers.get_list("set-cookie")}
        assert database.settings.session_cookie_name in issued
        assert database.settings.csrf_cookie_name in issued
        assert "HttpOnly" in issued[database.settings.session_cookie_name]
        assert "HttpOnly" not in issued[database.settings.csrf_cookie_name]
        assert promoted.get("/api/v1/auth/me").status_code == 200

    with TestClient(app, cookies={LEGACY_SESSION_COOKIE_NAME: "not-a-signed-token"}) as stranger:
        assert stranger.get("/api/v1/auth/me").status_code == 401
