"""v1.0.3 release fixes — installed-layout regressions that CI smoke now covers.

* ``spa_static_dir`` must find the SPA in the installed payload AND the dev
  checkout (the shortcut/launch fix is useless if "/" 404s).
* ``gen_delta`` must pack ``install_manifest.json`` + ``version.json`` — the
  updater rewrites them after apply; without them the next delta diffs against
  a stale baseline.
"""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

from app.main import spa_static_dir

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_spa_static_dir_installed_and_dev_layouts(tmp_path: Path) -> None:
    # installed payload: {app}/app/main.py → {app}/static
    inst = tmp_path / "VIRA"
    (inst / "app").mkdir(parents=True)
    (inst / "static").mkdir()
    main_py = inst / "app" / "main.py"
    main_py.write_text("")
    assert spa_static_dir(main_py) == inst / "static"

    # dev checkout: <repo>/backend/app/main.py → <repo>/frontend/dist
    dev = tmp_path / "repo"
    (dev / "backend" / "app").mkdir(parents=True)
    (dev / "frontend" / "dist").mkdir(parents=True)
    dev_main = dev / "backend" / "app" / "main.py"
    dev_main.write_text("")
    assert spa_static_dir(dev_main) == dev / "frontend" / "dist"

    # nothing built → no mount
    bare = tmp_path / "bare"
    (bare / "app").mkdir(parents=True)
    bare_main = bare / "app" / "main.py"
    bare_main.write_text("")
    assert spa_static_dir(bare_main) is None


def test_gen_delta_packs_updater_manifest_pair(tmp_path: Path) -> None:
    base_dir, target_dir = tmp_path / "base", tmp_path / "target"
    for d in (base_dir, target_dir):
        (d / "app").mkdir(parents=True)
        (d / "app" / "main.py").write_text("print('v1')\n")
    (target_dir / "app" / "main.py").write_text("print('v2')\n")
    (target_dir / "version.json").write_text(
        json.dumps({"version": "9.9.9", "built_at": "2026-10-15T00:00:00Z"})
    )

    def manifest_for(d: Path) -> Path:
        out = tmp_path / f"{d.name}-manifest.json"
        subprocess.run(  # noqa: S603
            [sys.executable, str(REPO_ROOT / "scripts" / "build_manifest.py"), str(d), "-o", str(out)],
            check=True,
            capture_output=True,
            timeout=60,
        )
        return out

    base_manifest = manifest_for(base_dir)
    out_dir = tmp_path / "out"
    subprocess.run(  # noqa: S603
        [
            sys.executable,
            str(REPO_ROOT / "scripts" / "gen_delta.py"),
            "--base-manifest", str(base_manifest),
            "--base-dir", str(base_dir),
            "--target-dir", str(target_dir),
            "--base-version", "9.9.8",
            "--target-version", "9.9.9",
            "--out", str(out_dir),
        ],
        check=True,
        capture_output=True,
        timeout=60,
    )
    zips = list(out_dir.glob("*.zip"))
    assert len(zips) == 1
    with zipfile.ZipFile(zips[0]) as zf:
        names = set(zf.namelist())
        assert {"update.json", "delete.json", "install_manifest.json", "version.json"} <= names
        packed = json.loads(zf.read("install_manifest.json"))
        assert packed["files_manifest_sha256"]
        assert any(n.startswith("files/") or n.startswith("patches/") for n in names)


def test_single_source_of_version_keeps_lock_and_persian_notes_aligned():
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    pyproject = re.search(r'^version = "([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    locked = re.search(r'\[\[package\]\]\nname = "vira-accounting"\nversion = "([^"]+)"', (root / "uv.lock").read_text(encoding="utf-8")).group(1)
    assert pyproject == locked, "uv.lock drifted from the project version"
    assert (root / f"docs/releases/v{pyproject}-fa.md").is_file(), "Persian notes must exist before tagging"
    workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "--target-version $env:VIRA_VERSION" in workflow
    assert "Refuse unsigned tagged publication" in workflow


def test_delta_coverage_requirement_follows_the_version_instead_of_a_frozen_list():
    from pathlib import Path

    smoke = (Path(__file__).resolve().parents[2] / "scripts/windows_smoke_test.ps1").read_text(encoding="utf-8")
    assert "$multiBase = $false" in smoke and "\\d+" in smoke
    assert "$exercisedBases.Count -ne 3" in smoke
    # A frozen allow-list is what silently reduced coverage for every new version.
    assert '$v -in @("1.0.9", "1.0.10")' not in smoke
    assert '$v -notin @("1.0.9", "1.0.10")' not in smoke


def test_native_in_app_update_smoke_is_not_gated_to_one_version():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # A version-pinned step condition silently skipped the whole real updater test
    # for every release after 1.0.10.
    assert "env.VIRA_VERSION == '1.0.10'" not in workflow
    assert "!startsWith(env.VIRA_VERSION, '0.0.0')" in workflow
    assert "keep its delta baseline in the window" in workflow
    assert 'if key(version) > (1, 0, 10)' in workflow


def test_compiled_updater_install_retries_a_transient_gallery_failure_only():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text(encoding="utf-8")
    step = workflow[workflow.index("Compile vira-updater.exe"):]
    step = step[:step.index("- name:", 10)]
    assert "$attempt -le 3" in step
    assert "ps2exe could not be installed after 3 real attempts" in step
    assert "throw" in step


def test_in_app_updater_failure_text_is_uploaded_not_only_annotated():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    harness = (root / "scripts/update_native_smoke.py").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'in-app-audit-failure-{' in harness and 'encoding="utf-8"' in harness
    assert "in-app-updater-diagnostics" in workflow
    assert "reports/in-app-audit-failure-*.txt" in workflow
