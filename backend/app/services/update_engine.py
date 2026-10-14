"""Update engine — pure logic for Phase 8 (installer releases & delta updates).

Everything here is side-effect-light and unit-testable on any platform:

- strict SemVer ``MAJOR.MINOR.PATCH`` comparison
- per-file install manifests (``path``, SHA-256, ``size``) + canonical hashing
- manifest diffing and delta package planning (``update.json`` operations)
- client-side update selection: matching delta → delta chain → full installer
- SHA-256 verification and Ed25519 signature verification of ``latest.json``
- bsdiff4 patch application (``apply_bsdiff``; used for large-file patches)
- the transactional updater's rollback state machine (§6)

No network I/O lives here — the GitHub check is in ``app.services.update``.
"""

from __future__ import annotations

import bz2
import hashlib
import json
import re
import struct
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

# ---------------------------------------------------------------------------
# SemVer — strict MAJOR.MINOR.PATCH (§2 tags are ``vX.Y.Z``)
# ---------------------------------------------------------------------------

_SEMVER_RE = re.compile(r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)$")


class SemVerError(ValueError):
    """Raised for anything that is not strict SemVer MAJOR.MINOR.PATCH."""


@dataclass(frozen=True, order=True)
class SemVer:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> SemVer:
        m = _SEMVER_RE.match(text.strip())
        if not m:
            raise SemVerError(f"not a strict SemVer MAJOR.MINOR.PATCH: {text!r}")
        return cls(int(m["major"]), int(m["minor"]), int(m["patch"]))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# ---------------------------------------------------------------------------
# File manifests (§5) — install_manifest.json baseline
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileEntry:
    path: str  # forward-slash relative path
    sha256: str
    size: int


class ManifestError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(root: Path, *, skip_names: Iterable[str] = ()) -> dict[str, FileEntry]:
    """Walk ``root`` and build ``path -> FileEntry`` with forward-slash keys."""
    skip = set(skip_names)
    out: dict[str, FileEntry] = {}
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root).as_posix()
        if rel in skip or p.name in skip:
            continue
        out[rel] = FileEntry(rel, sha256_file(p), p.stat().st_size)
    return out


def manifest_from_json(raw: Mapping[str, object]) -> dict[str, FileEntry]:
    files = raw.get("files")
    if not isinstance(files, list):
        raise ManifestError("manifest missing 'files' array")
    out: dict[str, FileEntry] = {}
    for item in files:
        if not isinstance(item, dict):
            raise ManifestError("manifest entry is not an object")
        try:
            entry = FileEntry(
                path=str(item["path"]).replace("\\", "/"),
                sha256=str(item["sha256"]).lower(),
                size=int(item["size"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ManifestError(f"bad manifest entry: {item!r}") from exc
        out[entry.path] = entry
    return out


def manifest_to_json(manifest: Mapping[str, FileEntry]) -> dict[str, object]:
    return {
        "files": [
            {"path": e.path, "sha256": e.sha256, "size": e.size}
            for e in sorted(manifest.values(), key=lambda e: e.path)
        ]
    }


def manifest_sha256(manifest: Mapping[str, FileEntry]) -> str:
    """Canonical hash of the manifest itself (stable across dict order)."""
    canonical = json.dumps(manifest_to_json(manifest), sort_keys=True, separators=(",", ":"))
    return sha256_bytes(canonical.encode("utf-8"))


# ---------------------------------------------------------------------------
# Manifest diff + delta plan (§5)
# ---------------------------------------------------------------------------

PATCH_THRESHOLD = 256 * 1024  # large files above this get bsdiff patches


@dataclass(frozen=True)
class ManifestDiff:
    added: tuple[str, ...]
    changed: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]


def manifest_diff(
    base: Mapping[str, FileEntry], target: Mapping[str, FileEntry]
) -> ManifestDiff:
    added = tuple(sorted(set(target) - set(base)))
    removed = tuple(sorted(set(base) - set(target)))
    changed = tuple(
        sorted(
            p
            for p in set(base) & set(target)
            if base[p].sha256 != target[p].sha256
        )
    )
    unchanged = tuple(
        sorted(
            p
            for p in set(base) & set(target)
            if base[p].sha256 == target[p].sha256
        )
    )
    return ManifestDiff(added, changed, removed, unchanged)


class OpKind(StrEnum):
    ADD = "add"
    REPLACE = "replace"
    PATCH = "patch"  # bsdiff member in patches/
    DELETE = "delete"


@dataclass(frozen=True)
class FileOp:
    op: OpKind
    path: str
    sha256: str = ""  # target hash (empty for delete)
    size: int = 0  # target size
    patch: str = ""  # member name in patches/ when op == PATCH


@dataclass(frozen=True)
class DeltaPlan:
    base_version: str
    target_version: str
    operations: tuple[FileOp, ...]

    def to_json(self) -> dict[str, object]:
        return {
            "base_version": self.base_version,
            "target_version": self.target_version,
            "operations": [
                {
                    "op": o.op.value,
                    "path": o.path,
                    **({"sha256": o.sha256} if o.op is not OpKind.DELETE else {}),
                    **({"size": o.size} if o.op is not OpKind.DELETE else {}),
                    **({"patch": o.patch} if o.op is OpKind.PATCH else {}),
                }
                for o in self.operations
            ],
        }

    @classmethod
    def from_json(cls, raw: Mapping[str, object]) -> DeltaPlan:
        try:
            ops_raw = raw["operations"]
            base_v = str(raw["base_version"])
            target_v = str(raw["target_version"])
        except KeyError as exc:
            raise ManifestError(f"update.json missing key: {exc}") from exc
        if not isinstance(ops_raw, list):
            raise ManifestError("update.json operations must be a list")
        ops: list[FileOp] = []
        for item in ops_raw:
            if not isinstance(item, dict):
                raise ManifestError("update.json op is not an object")
            try:
                ops.append(
                    FileOp(
                        op=OpKind(str(item["op"])),
                        path=str(item["path"]).replace("\\", "/"),
                        sha256=str(item.get("sha256", "")).lower(),
                        size=int(item.get("size", 0)),
                        patch=str(item.get("patch", "")),
                    )
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ManifestError(f"bad update.json op: {item!r}") from exc
        return cls(base_v, target_v, tuple(ops))


def plan_delta(
    base_version: str,
    target_version: str,
    base: Mapping[str, FileEntry],
    target: Mapping[str, FileEntry],
    *,
    patch_threshold: int = PATCH_THRESHOLD,
) -> tuple[DeltaPlan, dict[str, tuple[OpKind, str]]]:
    """Return (plan, member hints). Member hints map member name -> (kind, path).

    Small new/changed files ship whole under ``files/``; large changed files get
    a bsdiff patch under ``patches/`` (caller generates the bytes).
    """
    diff = manifest_diff(base, target)
    ops: list[FileOp] = []
    members: dict[str, tuple[OpKind, str]] = {}
    for path in diff.added:
        e = target[path]
        member = f"files/{path}"
        ops.append(FileOp(OpKind.ADD, path, e.sha256, e.size))
        members[member] = (OpKind.ADD, path)
    for path in diff.changed:
        e = target[path]
        if e.size > patch_threshold:
            member = f"patches/{path}.bsdiff"
            ops.append(FileOp(OpKind.PATCH, path, e.sha256, e.size, patch=member))
            members[member] = (OpKind.PATCH, path)
        else:
            member = f"files/{path}"
            ops.append(FileOp(OpKind.REPLACE, path, e.sha256, e.size))
            members[member] = (OpKind.REPLACE, path)
    for path in diff.removed:
        ops.append(FileOp(OpKind.DELETE, path))
    # deterministic order: add/replace/patch sorted by path, then deletes
    ops.sort(key=lambda o: (o.op is OpKind.DELETE, o.path))
    return DeltaPlan(base_version, target_version, tuple(ops)), members


# ---------------------------------------------------------------------------
# Update selection (§5 client-side) — delta → delta chain → full installer
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeltaRef:
    from_version: str
    url: str
    sha256: str
    size: int
    to_version: str = ""  # release that published this delta ("" = target)


class SelectionKind(StrEnum):
    DELTA = "delta"
    DELTA_CHAIN = "delta_chain"
    FULL = "full"


@dataclass(frozen=True)
class UpdateChoice:
    kind: SelectionKind
    deltas: tuple[DeltaRef, ...] = ()  # ordered hops (DELTA / DELTA_CHAIN)
    full_url: str = ""
    total_bytes: int = 0


def select_update(
    current: str,
    target: str,
    available: Sequence[DeltaRef],
    *,
    full_url: str,
    full_size: int,
    max_hops: int = 3,
) -> UpdateChoice:
    """Prefer one matching delta; else a bounded hop chain; else the full setup.

    ``available`` is every delta the client can see across recent releases
    (each delta upgrades an installation *from* ``from_version`` *to* the
    release that published it). A hop is legal only when its ``from_version``
    equals the running cursor and it strictly advances toward ``target`` —
    a delta never patches an installation older than its declared base, so
    installations older than every covered base must fall back to the full
    installer (Inno silent upgrade into the recorded InstallDir).
    """
    cur = SemVer.parse(current)
    tgt = SemVer.parse(target)
    if tgt <= cur:
        raise ValueError(f"target {target} is not newer than {current}")

    def to_version(d: DeltaRef) -> str:
        return d.to_version or str(tgt)

    # 1) exact base match against the target release's own deltas
    direct = [d for d in available if to_version(d) == str(tgt) and d.from_version == str(cur)]
    if direct:
        d = direct[0]
        return UpdateChoice(SelectionKind.DELTA, (d,), total_bytes=d.size)

    # 2) bounded chain over published deltas, always advancing to the newest
    #    reachable release, then to the target
    hops: list[DeltaRef] = []
    cursor = str(cur)
    for _ in range(max_hops):
        if cursor == str(tgt):
            break
        candidates = [
            d
            for d in available
            if d.from_version == cursor and tgt > SemVer.parse(to_version(d)) > SemVer.parse(cursor)
        ]
        if not candidates:
            break
        # advance as far as possible per hop (greedy)
        hop = max(candidates, key=lambda d: SemVer.parse(to_version(d)))
        hops.append(hop)
        cursor = to_version(hop)
    if cursor != str(tgt):
        # last hop: delta from the reached cursor straight to the target
        final = [d for d in available if to_version(d) == str(tgt) and d.from_version == cursor]
        if hops and final:
            hops.append(final[0])
            cursor = str(tgt)
    if hops and cursor == str(tgt):
        return UpdateChoice(
            SelectionKind.DELTA_CHAIN if len(hops) > 1 else SelectionKind.DELTA,
            tuple(hops),
            total_bytes=sum(d.size for d in hops),
        )
    # 3) full installer fallback
    return UpdateChoice(SelectionKind.FULL, full_url=full_url, total_bytes=full_size)


# ---------------------------------------------------------------------------
# SHA-256 + Ed25519 verification (§8)
# ---------------------------------------------------------------------------


class VerificationError(ValueError):
    pass


def verify_sha256(data: bytes, expected: str) -> None:
    actual = sha256_bytes(data)
    if actual != expected.lower():
        raise VerificationError(
            f"SHA-256 mismatch: expected {expected.lower()}, got {actual}"
        )


def verify_latest_signature(raw: bytes, signature: bytes, public_key_pem: bytes) -> None:
    """Ed25519 verification of the raw latest.json bytes (§8 recommended)."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    try:
        key = serialization.load_pem_public_key(public_key_pem)
    except Exception as exc:  # noqa: BLE001 - normalize crypto errors
        raise VerificationError(f"invalid public key: {exc}") from exc
    if not isinstance(key, Ed25519PublicKey):
        raise VerificationError("public key is not Ed25519")
    try:
        key.verify(signature, raw)
    except InvalidSignature as exc:
        raise VerificationError("latest.json signature invalid") from exc


# ---------------------------------------------------------------------------
# bsdiff4 apply (BSDIFF40 format) — large-file patches (§5)
# ---------------------------------------------------------------------------

_BSDIFF_MAGIC = b"BSDIFF40"


def apply_bsdiff(patch: bytes, old: bytes) -> bytes:
    """Apply a BSDIFF40 (bsdiff4) patch to ``old`` and return the new bytes."""
    if len(patch) < 32 or not patch.startswith(_BSDIFF_MAGIC):
        raise VerificationError("not a BSDIFF40 patch")

    def offt(buf: bytes) -> int:
        y = struct.unpack("<Q", buf)[0]
        sign = -1 if buf[7] & 0x80 else 1
        return sign * (y & 0x00FFFFFFFFFFFFFF)

    ctrl_len = offt(patch[8:16])
    diff_len = offt(patch[16:24])
    new_size = offt(patch[24:32])
    ctrl = bz2.decompress(patch[32 : 32 + ctrl_len])
    diff = bz2.decompress(patch[32 + ctrl_len : 32 + ctrl_len + diff_len])
    extra = bz2.decompress(patch[32 + ctrl_len + diff_len :])

    out = bytearray()
    old_pos, ctrl_pos, diff_pos, extra_pos = 0, 0, 0, 0
    while len(out) < new_size:
        if ctrl_pos + 24 > len(ctrl):
            raise VerificationError("corrupt bsdiff control stream")
        # control triples are offt-encoded (sign-magnitude) like the header
        add_x = offt(ctrl[ctrl_pos : ctrl_pos + 8])
        copy_y = offt(ctrl[ctrl_pos + 8 : ctrl_pos + 16])
        seek_z = offt(ctrl[ctrl_pos + 16 : ctrl_pos + 24])
        ctrl_pos += 24
        if diff_pos + add_x > len(diff):
            raise VerificationError("corrupt bsdiff diff stream")
        for i in range(add_x):
            old_byte = old[old_pos + i] if old_pos + i < len(old) else 0
            out.append((old_byte + diff[diff_pos + i]) & 0xFF)
        diff_pos += add_x
        old_pos += add_x
        if extra_pos + copy_y > len(extra):
            raise VerificationError("corrupt bsdiff extra stream")
        out.extend(extra[extra_pos : extra_pos + copy_y])
        extra_pos += copy_y
        old_pos += seek_z
        if old_pos < 0:
            raise VerificationError("corrupt bsdiff seek")
    return bytes(out[:new_size])


# ---------------------------------------------------------------------------
# latest.json (§3) — Zod on the frontend, pydantic here
# ---------------------------------------------------------------------------

LATEST_SCHEMA_VERSION = 1


class UpdateSchemaError(ValueError):
    """Unknown schema_version or malformed latest.json (§8: refuse)."""


class PackageRef(BaseModel):
    url: str
    sha256: str
    size: int


class DeltaAsset(BaseModel):
    from_version: str
    url: str
    sha256: str
    size: int


class LatestManifest(BaseModel):
    schema_version: int = Field(ge=1)
    version: str
    pub_date: str
    min_app_version: str
    notes_fa: str = ""
    notes_en: str = ""
    full_installer: PackageRef
    deltas: list[DeltaAsset] = Field(default_factory=list)
    files_manifest_sha256: str = ""


def parse_latest(raw: bytes | str) -> LatestManifest:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UpdateSchemaError(f"latest.json is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateSchemaError("latest.json must be an object")
    schema_version = data.get("schema_version")
    if schema_version != LATEST_SCHEMA_VERSION:
        raise UpdateSchemaError(
            f"unknown latest.json schema_version: {schema_version!r} "
            f"(supported: {LATEST_SCHEMA_VERSION}) — manual install required"
        )
    try:
        manifest = LatestManifest.model_validate(data)
        # versions must themselves be strict SemVer
        SemVer.parse(manifest.version)
        SemVer.parse(manifest.min_app_version)
        for d in manifest.deltas:
            SemVer.parse(d.from_version)
    except (ValidationError, SemVerError) as exc:
        raise UpdateSchemaError(f"invalid latest.json: {exc}") from exc
    return manifest


# ---------------------------------------------------------------------------
# Rollback state machine (§6) — the updater helper's transaction
# ---------------------------------------------------------------------------

class UpdateState(StrEnum):
    IDLE = "idle"
    STAGING = "staging"  # downloading + verifying package into updates/<v>/
    SNAPSHOTTING = "snapshotting"  # copying files scheduled to change → rollback/prev/
    APPLYING = "applying"  # copies + patches + deletes
    REWRITING = "rewriting"  # install_manifest.json + version.json
    HEALTH_CHECK = "health_check"  # first /health/ready + accounting invariants
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"


class UpdateEvent(StrEnum):
    START = "start"
    STAGED = "staged"
    SNAPSHOTTED = "snapshotted"
    APPLIED = "applied"
    REWRITTEN = "rewritten"
    HEALTHY = "healthy"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


_TRANSITIONS: dict[tuple[UpdateState, UpdateEvent], UpdateState] = {
    (UpdateState.IDLE, UpdateEvent.START): UpdateState.STAGING,
    (UpdateState.STAGING, UpdateEvent.STAGED): UpdateState.SNAPSHOTTING,
    (UpdateState.SNAPSHOTTING, UpdateEvent.SNAPSHOTTED): UpdateState.APPLYING,
    (UpdateState.APPLYING, UpdateEvent.APPLIED): UpdateState.REWRITING,
    (UpdateState.REWRITING, UpdateEvent.REWRITTEN): UpdateState.HEALTH_CHECK,
    (UpdateState.HEALTH_CHECK, UpdateEvent.HEALTHY): UpdateState.COMMITTED,
    # failure from any active state → rollback → rolled back
    (UpdateState.STAGING, UpdateEvent.FAILED): UpdateState.ROLLING_BACK,
    (UpdateState.SNAPSHOTTING, UpdateEvent.FAILED): UpdateState.ROLLING_BACK,
    (UpdateState.APPLYING, UpdateEvent.FAILED): UpdateState.ROLLING_BACK,
    (UpdateState.REWRITING, UpdateEvent.FAILED): UpdateState.ROLLING_BACK,
    (UpdateState.HEALTH_CHECK, UpdateEvent.FAILED): UpdateState.ROLLING_BACK,
    (UpdateState.ROLLING_BACK, UpdateEvent.ROLLED_BACK): UpdateState.ROLLED_BACK,
}


class IllegalTransition(ValueError):
    pass


def transition(state: UpdateState, event: UpdateEvent) -> UpdateState:
    key = (state, event)
    if key not in _TRANSITIONS:
        raise IllegalTransition(f"no transition {state.value} + {event.value}")
    return _TRANSITIONS[key]


def is_failure_terminal(state: UpdateState) -> bool:
    return state is UpdateState.ROLLED_BACK


def is_success_terminal(state: UpdateState) -> bool:
    return state is UpdateState.COMMITTED


@dataclass
class UpdateRun:
    """Drives the state machine for one update attempt (testable driver)."""

    state: UpdateState = UpdateState.IDLE
    log: list[str] = field(default_factory=list)

    def fire(self, event: UpdateEvent) -> UpdateState:
        self.state = transition(self.state, event)
        self.log.append(f"{event.value} -> {self.state.value}")
        return self.state

    @property
    def terminal(self) -> bool:
        return is_success_terminal(self.state) or is_failure_terminal(self.state)
