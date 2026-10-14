"""Phase 8 §10 unit tests — update engine: SemVer, manifest diff, delta plans,
selection (delta/chain/full), SHA-256 + Ed25519, bsdiff apply, rollback state
machine, latest.json parsing (incl. malformed and unknown schema versions)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.update_engine import (
    DeltaPlan,
    DeltaRef,
    FileEntry,
    FileOp,
    IllegalTransition,
    LatestManifest,
    OpKind,
    SelectionKind,
    SemVer,
    SemVerError,
    UpdateEvent,
    UpdateRun,
    UpdateSchemaError,
    UpdateState,
    VerificationError,
    apply_bsdiff,
    build_manifest,
    manifest_diff,
    manifest_sha256,
    parse_latest,
    plan_delta,
    select_update,
    sha256_bytes,
    transition,
    verify_latest_signature,
    verify_sha256,
)

# ----------------------------------------------------------------- SemVer ---


class TestSemVer:
    def test_parse_strict_with_optional_v_prefix(self) -> None:
        assert SemVer.parse("1.2.3") == SemVer(1, 2, 3)
        assert SemVer.parse("v10.0.7") == SemVer(10, 0, 7)

    @pytest.mark.parametrize("bad", ["1.2", "1.2.3.4", "01.2.3", "1.2.3-rc1", "", "v", "latest"])
    def test_rejects_non_strict(self, bad: str) -> None:
        with pytest.raises(SemVerError):
            SemVer.parse(bad)

    def test_ordering(self) -> None:
        assert SemVer.parse("1.2.3") < SemVer.parse("1.2.4") < SemVer.parse("1.3.0") < SemVer.parse("2.0.0")
        assert SemVer.parse("v9.9.9") > SemVer.parse("9.9.8")


# --------------------------------------------------------------- manifest ---


def _entry(path: str, size: int = 10, h: str = "aa") -> FileEntry:
    return FileEntry(path, h * 32, size)


class TestManifest:
    def test_build_manifest_walks_files(self, tmp_path: Path) -> None:
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_bytes(b"print(1)")
        (tmp_path / "version.json").write_bytes(b"{}")
        m = build_manifest(tmp_path, skip_names={"version.json"})
        assert set(m) == {"app/main.py"}
        assert m["app/main.py"].size == 8
        assert m["app/main.py"].sha256 == sha256_bytes(b"print(1)")

    def test_diff_detects_add_change_remove(self) -> None:
        base = {"a": _entry("a", h="aa"), "b": _entry("b", h="bb"), "c": _entry("c", h="cc")}
        target = {"a": _entry("a", h="aa"), "b": _entry("b", h="dd"), "d": _entry("d", h="ee")}
        diff = manifest_diff(base, target)
        assert diff.added == ("d",)
        assert diff.changed == ("b",)
        assert diff.removed == ("c",)
        assert diff.unchanged == ("a",)

    def test_manifest_sha_is_order_independent(self) -> None:
        a = {"x": _entry("x"), "y": _entry("y")}
        b = {"y": _entry("y"), "x": _entry("x")}
        assert manifest_sha256(a) == manifest_sha256(b)


# ------------------------------------------------------------- delta plan ---


class TestDeltaPlan:
    def test_small_files_ship_whole_large_get_patches(self) -> None:
        base = {
            "small.txt": _entry("small.txt", size=100, h="aa"),
            "big.dll": _entry("big.dll", size=600_000, h="bb"),
        }
        target = {
            "small.txt": _entry("small.txt", size=120, h="cc"),
            "big.dll": _entry("big.dll", size=610_000, h="dd"),
            "new.js": _entry("new.js", size=5, h="ee"),
            "gone.bin": _entry("gone.bin", size=1, h="ff"),
        }
        # target has gone.bin? no — it must be REMOVED, so take it out of target
        del target["gone.bin"]
        base["gone.bin"] = _entry("gone.bin", size=1, h="ff")
        plan, members = plan_delta("1.0.0", "1.1.0", base, target, patch_threshold=256 * 1024)
        kinds = {o.path: o for o in plan.operations}
        assert kinds["small.txt"].op is OpKind.REPLACE
        assert kinds["big.dll"].op is OpKind.PATCH
        assert kinds["big.dll"].patch == "patches/big.dll.bsdiff"
        assert kinds["new.js"].op is OpKind.ADD
        assert kinds["gone.bin"].op is OpKind.DELETE
        assert "files/new.js" in members
        assert "patches/big.dll.bsdiff" in members
        # deterministic op order: non-deletes first (by path), deletes last
        paths = [o.path for o in plan.operations]
        assert paths[-1] == "gone.bin"

    def test_plan_json_round_trip(self) -> None:
        plan = DeltaPlan(
            "1.0.0",
            "1.1.0",
            (
                FileOp(OpKind.ADD, "a.txt", "ab" * 32, 5),
                FileOp(OpKind.PATCH, "b.dll", "cd" * 32, 100_000, patch="patches/b.dll.bsdiff"),
                FileOp(OpKind.DELETE, "c.txt"),
            ),
        )
        again = DeltaPlan.from_json(plan.to_json())
        assert again == plan


# -------------------------------------------------------------- selection ---


def _dref(base: str, size: int = 100) -> DeltaRef:
    return DeltaRef(base, f"https://example/{base}.zip", "ab" * 32, size)


class TestSelection:
    def test_exact_base_delta_wins(self) -> None:
        choice = select_update(
            "1.0.0", "1.1.0", [_dref("1.0.0"), _dref("0.9.0")],
            full_url="https://example/setup.exe", full_size=50_000_000,
        )
        assert choice.kind is SelectionKind.DELTA
        assert choice.total_bytes == 100  # ≪ full setup — "only changed parts"

    def test_falls_back_to_full_when_base_older_than_covered(self) -> None:
        choice = select_update(
            "0.1.0", "1.1.0", [_dref("1.0.0"), _dref("0.9.0")],
            full_url="https://example/setup.exe", full_size=50_000_000,
        )
        assert choice.kind is SelectionKind.FULL
        assert choice.full_url == "https://example/setup.exe"

    def test_chain_over_intermediate_deltas(self) -> None:
        # 1.0.0 ->(1.1.0's delta from 1.0.0? no) — reachable via 1.1.0's own delta
        # then 1.1.0 -> 1.2.0: chain of two hops when releases publish matching bases
        hop1 = DeltaRef("1.0.0", "https://example/d1.zip", "ab" * 32, 100, to_version="1.1.0")
        hop2 = DeltaRef("1.1.0", "https://example/d2.zip", "cd" * 32, 200, to_version="1.2.0")
        choice = select_update(
            "1.0.0", "1.2.0", [hop1, hop2],
            full_url="https://example/setup.exe", full_size=50_000_000,
        )
        assert choice.kind is SelectionKind.DELTA_CHAIN
        assert [d.from_version for d in choice.deltas] == ["1.0.0", "1.1.0"]
        assert choice.total_bytes == 300  # still ≪ full setup

    def test_rejects_non_upgrade(self) -> None:
        with pytest.raises(ValueError):
            select_update("1.1.0", "1.1.0", [], full_url="x", full_size=1)


# ----------------------------------------------------------- verification ---


class TestVerification:
    def test_sha_ok_and_mismatch(self) -> None:
        verify_sha256(b"hello", sha256_bytes(b"hello"))
        with pytest.raises(VerificationError):
            verify_sha256(b"hello", sha256_bytes(b"goodbye"))

    def test_ed25519_signature_round_trip(self) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        raw = b'{"schema_version": 1, "version": "1.1.0"}'
        sig = key.sign(raw)
        verify_latest_signature(raw, sig, pub)
        with pytest.raises(VerificationError):
            verify_latest_signature(raw + b" ", sig, pub)

    def test_rejects_non_ed25519_key(self) -> None:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        raw = b"x"
        sig = key.sign(raw)
        with pytest.raises(VerificationError):
            verify_latest_signature(raw, sig, b"not a pem key")


# ---------------------------------------------------------------- bsdiff ---


class TestBsdiff:
    def test_apply_matches_bsdiff4_patch(self) -> None:
        bsdiff4 = pytest.importorskip("bsdiff4")
        old = bytes(range(256)) * 8
        new = old[:500] + b"NEW DATA" + old[508:] + b"tail"
        patch = bsdiff4.diff(old, new)
        assert apply_bsdiff(patch, old) == new

    def test_rejects_garbage_patch(self) -> None:
        with pytest.raises(VerificationError):
            apply_bsdiff(b"NOTABSDIFF", b"x")


# ----------------------------------------------------------- latest.json ---


def _latest_payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "version": "1.1.0",
        "pub_date": "2026-10-14T12:00:00Z",
        "min_app_version": "1.0.0",
        "notes_fa": "نسخهٔ جدید",
        "notes_en": "new release",
        "full_installer": {"url": "https://github.com/x/y/releases/download/v1.1.0/VIRA-Setup-1.1.0.exe", "sha256": "ab" * 32, "size": 50_000_000},
        "deltas": [
            {"from_version": "1.0.0", "url": "https://github.com/x/y/releases/download/v1.1.0/VIRA-1.1.0-delta-from-1.0.0.zip", "sha256": "cd" * 32, "size": 250_000}
        ],
        "files_manifest_sha256": "ef" * 32,
    }
    base.update(over)
    return base


class TestLatestJson:
    def test_valid_manifest_parses(self) -> None:
        m = parse_latest(json.dumps(_latest_payload()))
        assert isinstance(m, LatestManifest)
        assert m.version == "1.1.0"
        assert m.deltas[0].from_version == "1.0.0"

    @pytest.mark.parametrize("schema", [2, 0, None, "1"])
    def test_unknown_schema_version_refused(self, schema: object) -> None:
        raw = json.dumps(_latest_payload(schema_version=schema))
        with pytest.raises(UpdateSchemaError, match="schema_version"):
            parse_latest(raw)

    def test_malformed_json_refused(self) -> None:
        with pytest.raises(UpdateSchemaError):
            parse_latest("{not json")

    def test_bad_versions_refused(self) -> None:
        with pytest.raises(UpdateSchemaError):
            parse_latest(json.dumps(_latest_payload(version="1.2")))
        with pytest.raises(UpdateSchemaError):
            parse_latest(json.dumps(_latest_payload(deltas=[{"from_version": "x", "url": "u", "sha256": "ab" * 32, "size": 1}])))

    def test_phase6_shape_without_schema_version_refused(self) -> None:
        legacy = {"version": "1.0.0", "published_at": "x", "channel": "stable", "notes_fa": "x", "files": []}
        with pytest.raises(UpdateSchemaError):
            parse_latest(json.dumps(legacy))


# -------------------------------------------------------- state machine ---


class TestRollbackMachine:
    def test_happy_path(self) -> None:
        run = UpdateRun()
        for ev in (
            UpdateEvent.START,
            UpdateEvent.STAGED,
            UpdateEvent.SNAPSHOTTED,
            UpdateEvent.APPLIED,
            UpdateEvent.REWRITTEN,
            UpdateEvent.HEALTHY,
        ):
            run.fire(ev)
        assert run.state is UpdateState.COMMITTED
        assert run.terminal

    @pytest.mark.parametrize(
        "fail_at",
        [UpdateEvent.STAGED, UpdateEvent.SNAPSHOTTED, UpdateEvent.APPLIED, UpdateEvent.REWRITTEN, UpdateEvent.HEALTHY],
    )
    def test_failure_rolls_back_from_any_active_state(self, fail_at: UpdateEvent) -> None:
        run = UpdateRun()
        run.fire(UpdateEvent.START)
        happy = {
            UpdateEvent.STAGED: [],
            UpdateEvent.SNAPSHOTTED: [UpdateEvent.STAGED],
            UpdateEvent.APPLIED: [UpdateEvent.STAGED, UpdateEvent.SNAPSHOTTED],
            UpdateEvent.REWRITTEN: [UpdateEvent.STAGED, UpdateEvent.SNAPSHOTTED, UpdateEvent.APPLIED],
            UpdateEvent.HEALTHY: [UpdateEvent.STAGED, UpdateEvent.SNAPSHOTTED, UpdateEvent.APPLIED, UpdateEvent.REWRITTEN],
        }
        for ev in happy[fail_at]:
            run.fire(ev)
        run.fire(UpdateEvent.FAILED)
        assert run.state is UpdateState.ROLLING_BACK
        run.fire(UpdateEvent.ROLLED_BACK)
        assert run.state is UpdateState.ROLLED_BACK
        assert run.terminal

    def test_illegal_transitions_rejected(self) -> None:
        with pytest.raises(IllegalTransition):
            transition(UpdateState.IDLE, UpdateEvent.HEALTHY)
        with pytest.raises(IllegalTransition):
            transition(UpdateState.COMMITTED, UpdateEvent.FAILED)
        with pytest.raises(IllegalTransition):
            transition(UpdateState.ROLLED_BACK, UpdateEvent.START)
