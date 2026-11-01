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
    LEGACY_DATABASE_FILENAME,
    Settings,
    migrate_legacy_data_dir,
)

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
