"""Fast checks for the release gate; not a substitute for the Windows journey."""

from __future__ import annotations

import hashlib
import importlib
import json
import zipfile
from pathlib import Path

import pytest


@pytest.fixture
def harness(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2]))
    return importlib.import_module("scripts.update_native_smoke")


def payload(root: Path, name: str = "app/main.py") -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(b"immutable client bytes")
    (root / "install_manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "path": name,
                        "size": file.stat().st_size,
                        "sha256": hashlib.sha256(file.read_bytes()).hexdigest(),
                    }
                ]
            }
        )
    )
    return file


def test_shipped_payload_verified_without_rebuilding(tmp_path, harness):
    file = payload(tmp_path)
    harness.verify_payload(tmp_path)
    file.write_bytes(b"changed client")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path)


@pytest.mark.parametrize(
    "relative",
    ["../outside.py", "/outside.py", r"C:\outside.py", "C:outside.py", r"app\..\outside.py"],
)
def test_manifest_escape_rejected(tmp_path, harness, relative):
    (tmp_path / "install_manifest.json").write_text(json.dumps({"files": [{"path": relative}]}))
    with pytest.raises(ValueError, match="unsafe"):
        harness.verify_payload(tmp_path)


def test_runtime_cache_exception_is_not_a_source_file_exception(tmp_path, harness):
    cached = payload(tmp_path, "app/__pycache__/module.pyc")
    cached.write_bytes(b"regenerated after boot")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path)
    harness.verify_payload(tmp_path, runtime=True)
    source = payload(tmp_path, "app/main.py")
    source.write_bytes(b"bad source after boot")
    with pytest.raises(ValueError, match="hash mismatch"):
        harness.verify_payload(tmp_path, runtime=True)


def test_public_asset_digest_cannot_be_substituted(tmp_path, harness):
    base = tmp_path / "base-1.0.9"
    base.mkdir()
    (tmp_path / "base-1.0.9.zip").write_bytes(b"not the public payload")
    with pytest.raises(ValueError, match="ZIP digest mismatch"):
        harness.PublishedUpgrade(base, tmp_path / "packages").validate()


def test_failure_diagnostics_survive_windows_code_page(tmp_path, harness, monkeypatch):
    import io

    file = tmp_path / "server.log"
    file.write_bytes("خطای راه‌اندازی — 100%\r\nnext".encode())
    buffer = io.BytesIO()
    stdout = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(harness.sys, "stdout", stdout)
    harness.emit_diagnostic(file)
    text = buffer.getvalue().decode("ascii")
    assert "::error title=phase8 server.log::" in text
    assert r"\u062e" in text
    assert r"\u2014" in text
    assert "100%25%0Anext" in text


def test_published_client_is_seeded_on_its_own_revision_not_the_repo_head():
    from pathlib import Path

    source = (Path(__file__).resolve().parents[2] / "scripts/update_native_smoke.py").read_text(encoding="utf-8")
    published = source.index("    if published:\n        # The installed public client must start on ITS revision")
    head_migrator = source.index('run(sys.executable, str(ROOT / "scripts/migrate_vira.py")')
    assert published < head_migrator, "the repo migrator must not seed a published client"
    block = source[published:head_migrator]
    assert 'str(install / "scripts/migrate_vira.py")' in block
    # A real upgrade migrates the released schema; byte equality would be wrong there.
    assert "target did not migrate the released schema" in source
    assert "new schema table missing after real upgrade" in source
    # Before the commit the released schema must still be the released revision.
    assert "database migrated before the update completed" in source
    # A restore is proven by SQL fingerprint, exactly like the shipped updater.
    assert "restored released database differs" in source


def published_zip(tmp_path: Path, *, nested: bool = True) -> Path:
    """A published-looking payload ZIP; the real asset is digest-pinned."""
    root = tmp_path / "zip-root" / ("vira-1.0.9" if nested else "")
    payload(root)
    archive = tmp_path / "published.zip"
    outer = root.parent if nested else root
    with zipfile.ZipFile(archive, "w") as bundle:
        for file in root.rglob("*"):
            if file.is_file():
                bundle.write(file, file.relative_to(outer))
    return archive


def test_missing_published_base_is_restored_from_the_pinned_asset(tmp_path, harness):
    archive = published_zip(tmp_path)
    cache = tmp_path / "vira-delta-base"
    restored = harness.ensure_published_base(
        cache, url=archive.as_uri(), archive_sha256=harness.sha(archive)
    )
    assert restored == cache / "base-1.0.9"
    assert (restored / "install_manifest.json").is_file()
    # The digest check in PublishedUpgrade.validate() reads the sibling archive.
    assert harness.sha(cache / "base-1.0.9.zip") == harness.sha(archive)
    harness.verify_payload(restored)
    # Second call reuses the cache instead of re-downloading.
    reused = harness.ensure_published_base(
        cache, url="file:///nonexistent.zip", archive_sha256=harness.sha(archive)
    )
    assert reused == restored


def test_restored_published_base_rejects_a_different_digest(tmp_path, harness):
    archive = published_zip(tmp_path)
    with pytest.raises(ValueError, match="ZIP digest mismatch"):
        harness.ensure_published_base(
            tmp_path / "cache", url=archive.as_uri(), archive_sha256="0" * 64
        )
    assert not (tmp_path / "cache" / "base-1.0.9.zip").exists()


def test_published_asset_with_an_escaping_member_is_refused(tmp_path, harness):
    archive = tmp_path / "hostile.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("../outside.txt", "escape")
    with pytest.raises(ValueError, match="unsafe published ZIP member"):
        harness.ensure_published_base(
            tmp_path / "cache", url=archive.as_uri(), archive_sha256=harness.sha(archive)
        )
    assert not (tmp_path / "outside.txt").exists()


def test_real_upgrade_fixture_no_longer_depends_on_the_delta_window():
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    workflow = (root / ".github/workflows/release.yml").read_text(encoding="utf-8")
    # build_deltas.ps1 keeps three tags, so a pinned 1.0.9 base is gone by 1.0.13.
    assert "--fetch-published-base $baseRoot" in workflow
    assert "reports/in-app-step-output.txt" in workflow
    assert "reports/in-app-crash-report.txt" in workflow


def test_gate_delta_outside_the_shipped_assets_satisfies_the_pinned_upgrade(tmp_path, harness):
    base = tmp_path / "vira-delta-base/base-1.0.9"
    payload(base)
    (base / "version.json").write_text(
        json.dumps(dict(version="1.0.9", commit="7d78720abc", spa_build="x"))
    )
    manifest = json.loads((base / "install_manifest.json").read_text())
    manifest["files"].append(
        dict(path="version.json", size=(base / "version.json").stat().st_size,
             sha256=harness.sha(base / "version.json"))
    )
    (base / "install_manifest.json").write_text(json.dumps(manifest))
    archive = tmp_path / "vira-delta-base/base-1.0.9.zip"
    archive.write_bytes(b"pinned public payload")
    packages = tmp_path / "dist-release"
    (packages / "app").mkdir(parents=True)
    (packages / "app/version.json").write_text(json.dumps(dict(version="1.0.13")))
    gate = tmp_path / "vira-gate-delta/VIRA-v1.0.13-delta-from-v1.0.9.zip"
    gate.parent.mkdir()
    gate.write_bytes(b"gate only delta")
    # The release keeps three direct deltas, so nothing from 1.0.9 is shipped.
    published = harness.PublishedUpgrade(
        base, packages, target_version="1.0.13", archive_sha256=harness.sha(archive)
    )
    with pytest.raises(ValueError, match="mandatory direct delta missing"):
        published.validate()
    harness.PublishedUpgrade(
        base,
        packages,
        target_version="1.0.13",
        archive_sha256=harness.sha(archive),
        gate_delta=gate,
    ).validate()


def test_workflow_builds_the_gate_delta_outside_the_shipped_assets():
    from pathlib import Path

    workflow = (
        Path(__file__).resolve().parents[2] / ".github/workflows/release.yml"
    ).read_text(encoding="utf-8")
    step = workflow[workflow.index("Published 1.0.9 client ->"):]
    step = step[: step.index("- name:", 10)]
    assert "--published-delta $gateDelta" in step
    assert "scripts/gen_delta.py" in step and "--base-version 1.0.9" in step
    assert '$gateDeltaDir = Join-Path $env:RUNNER_TEMP "vira-gate-delta"' in step
    assert "$gateDeltaDir *>&1" in step, "the gate delta must never be written into dist-release"
