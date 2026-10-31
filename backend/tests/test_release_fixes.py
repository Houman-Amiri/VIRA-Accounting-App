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

import pytest

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
    assert "./scripts/install_ps2exe.ps1" in step
    assert "refusing to build without a compiled updater" in step


def test_in_app_updater_failure_text_is_uploaded_not_only_annotated():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    harness = (root / "scripts/update_native_smoke.py").read_text(encoding="utf-8")
    workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'in-app-audit-failure-{' in harness and 'encoding="utf-8"' in harness
    assert "in-app-updater-diagnostics" in workflow
    assert "reports/in-app-audit-failure-*.txt" in workflow


def test_ps2exe_installation_retries_in_one_shared_place():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    helper = (root / "scripts/install_ps2exe.ps1").read_text(encoding="utf-8")
    assert "param([int]$Attempts = 3)" in helper
    assert "Install-Module ps2exe" in helper and "throw" in helper
    for name in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
        text = (root / name).read_text(encoding="utf-8")
        assert "./scripts/install_ps2exe.ps1" in text
        assert text.count("Install-Module ps2exe") == 0, f"{name} still installs ps2exe inline"


def test_windows_smoke_transcript_is_kept_and_emitted_on_failure():
    from pathlib import Path

    workflow = (Path(__file__).resolve().parents[2] / ".github/workflows/release.yml").read_text(encoding="utf-8")
    step = workflow[workflow.index("Windows install/upgrade/rollback smoke test"):]
    step = step[:step.index("- name:", 10)]
    assert "Tee-Object -FilePath $log" in step
    assert "smoke-output-" in step and "::error title=" in step
    assert "throw \"windows smoke test failed\"" in step
    helper = (Path(__file__).resolve().parents[2] / "scripts/install_ps2exe.ps1").read_text(encoding="utf-8")
    assert "exit 0" not in helper, "a module helper must not terminate the caller's shell"


def test_in_app_audit_assertion_is_its_own_annotation():
    from pathlib import Path

    harness = (Path(__file__).resolve().parents[2] / "scripts/update_native_smoke.py").read_text(encoding="utf-8")
    assert "::error title=in-app-audit-assertion-" in harness
    assert ".replace(\"%\", \"%25\")" in harness


def test_in_app_audit_records_status_reads_instead_of_orphan_promises():
    from pathlib import Path

    audit = (Path(__file__).resolve().parents[2] / "scripts/audit_in_app_update.cjs").read_text(encoding="utf-8")
    assert "recordStatusReads(page)" in audit
    assert 'page.waitForResponse((r) => r.url().endsWith("/api/v1/system/status")' not in audit
    assert 'process.on("unhandledRejection"' in audit


def _native_smoke_module():
    import importlib.util

    path = REPO_ROOT / "scripts/update_native_smoke.py"
    spec = importlib.util.spec_from_file_location("vira_native_smoke_under_test", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses need a registered module
    spec.loader.exec_module(module)
    return module


def test_tagged_version_is_normalized_before_comparing_with_version_json():
    """A tag says v1.0.11 while packaging writes 1.0.11; that broke the tag run."""
    normalize = _native_smoke_module().normalize_target_version
    assert normalize("v1.0.11") == "1.0.11"
    assert normalize("1.0.11") == "1.0.11"
    assert normalize(" v1.0.11 ") == "1.0.11"
    assert normalize("V1.0.11") == "1.0.11"
    for bad in ("", "v", "1.0", "vv1.0.11", "1.0.11x", "1.0.11.1", "latest"):
        with pytest.raises(SystemExit):
            normalize(bad)


def test_release_workflow_normalizes_the_target_version_for_the_updater_audit():
    workflow = (REPO_ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "update_native_smoke.py" in workflow
    assert "type=normalize_target_version" in (REPO_ROOT / "scripts/update_native_smoke.py").read_text(encoding="utf-8")


def test_committed_openapi_contract_matches_the_ci_regeneration_bytes(app):
    """The contract job dumps `json.dump(..., indent=2)` — bytes, not just JSON.

    v1.0.13's release run failed here because a regenerated file carried one
    trailing newline the CI dump never writes; the schema was otherwise in sync.
    Comparing the exact bytes keeps the release job from failing on whitespace.
    """
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    expected = json.dumps(app.openapi(), indent=2, ensure_ascii=False)
    actual = (root / "backend/openapi.json").read_text(encoding="utf-8")
    assert actual == expected, "backend/openapi.json must equal the CI regeneration byte for byte"
