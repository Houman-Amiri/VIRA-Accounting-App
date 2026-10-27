"""Private installed Source21 transaction, stdlib only, outside replaced runtime.

Selected only by the real updater's explicit private CI branch. The archive SHA
and old/target anchors are external inputs, not self-certified ZIP metadata.
Public startup/update selection and release gates remain unchanged.
"""

from __future__ import annotations

import argparse
import bz2
import hashlib
import json
import os
import runpy
import secrets
import shutil
import subprocess
import time
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

MAX_FILE = 256 * 1024 * 1024
MAX_TOTAL = 2 * 1024 * 1024 * 1024
ROOTS = {"app", "backend", "python", "scripts", "site-packages", "static", "tools"}
TOP = {"version.json", "start_vira.cmd", "vira-updater.exe", "private-utf8-process-manifest.json"}


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(raw: bytes) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate transaction JSON key")
            result[key] = value
        return result

    value = json.loads(raw.decode("utf-8-sig"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("Transaction JSON object required")
    return value


def no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (
            item.exists() and getattr(item.stat(), "st_file_attributes", 0) & 0x400
        ):
            raise ValueError("Transaction reparse/symlink rejected")


def relative(name: str) -> str:
    if not isinstance(name, str) or not name or name.startswith("/"):
        raise ValueError("Relative payload path required")
    for part in name.split("/"):
        if (
            not part
            or part in {".", ".."}
            or part[-1:] in {".", " "}
            or any(ord(c) < 32 or c in '\\:*?"<>|' for c in part)
            or part.split(".")[0].upper()
            in {
                "CON",
                "PRN",
                "AUX",
                "NUL",
                *(f"COM{i}" for i in range(1, 10)),
                *(f"LPT{i}" for i in range(1, 10)),
            }
        ):
            raise ValueError("Unsafe Windows payload path")
    if not (
        name in TOP
        or (name.split("/")[0] in ROOTS and "/" in name)
        or name.startswith("native/pdf/")
    ):
        raise ValueError("Non-application path rejected")
    return name


def manifest(raw: bytes, digest: str) -> dict[str, dict]:
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("External manifest digest differs")
    doc = read(raw)
    result = {}
    folded = set()
    for entry in doc["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size"}:
            raise ValueError("Exact manifest entry schema required")
        name = relative(entry["path"])
        h, size = entry["sha256"], entry["size"]
        if (
            name.casefold() in folded
            or type(size) is not int
            or not 0 <= size <= MAX_FILE
            or not isinstance(h, str)
            or len(h) != 64
            or any(c not in "0123456789abcdef" for c in h)
        ):
            raise ValueError("Ambiguous/invalid manifest entry")
        folded.add(name.casefold())
        result[name] = entry
    if sum(e["size"] for e in result.values()) > MAX_TOTAL:
        raise ValueError("Private payload exceeds byte budget")
    return result


def verify(root: Path, files: dict[str, dict]) -> None:
    no_links(root)
    actual = set()
    for path in root.rglob("*"):
        no_links(path)
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(files) | {"install_manifest.json"}:
        raise ValueError("Unmanifested/missing installed file")
    for name, entry in files.items():
        path = root / name
        if path.stat().st_size != entry["size"] or sha(path) != entry["sha256"]:
            raise ValueError("Installed file differs from baseline")


def patch(old: bytes, data: bytes, expected: int) -> bytes:
    # BSDIFF40 signed-magnitude int64 format; bounded streams, not arbitrary ZIP execution.
    def number(value):
        integer = int.from_bytes(value, "little")
        return -(integer & ((1 << 63) - 1)) if integer >> 63 else integer

    if len(data) < 32 or data[:8] != b"BSDIFF40":
        raise ValueError("BSDIFF40 required")
    clen, dlen, size = [number(data[n : n + 8]) for n in (8, 16, 24)]
    if min(clen, dlen, size) < 0 or size != expected or 32 + clen + dlen > len(data):
        raise ValueError("Invalid patch header")
    streams = [data[32 : 32 + clen], data[32 + clen : 32 + clen + dlen], data[32 + clen + dlen :]]
    chunks = []
    for block in streams:
        decoder = bz2.BZ2Decompressor()
        decoded = decoder.decompress(block, max_length=MAX_FILE + 1)
        if len(decoded) > MAX_FILE or not decoder.eof or decoder.unused_data:
            raise ValueError("Patch decompression budget exceeded")
        chunks.append(decoded)
    control, diff, extra = chunks
    if len(control) % 24:
        raise ValueError("Invalid patch controls")
    out = bytearray()
    oldpos = dp = ep = 0
    for pos in range(0, len(control), 24):
        x, y, z = [number(control[n : n + 8]) for n in range(pos, pos + 24, 8)]
        if min(x, y) < 0 or len(out) + x + y > size or dp + x > len(diff) or ep + y > len(extra):
            raise ValueError("Patch offsets exceed output")
        for i in range(x):
            before = old[oldpos + i] if 0 <= oldpos + i < len(old) else 0
            out.append((diff[dp + i] + before) & 255)
        out.extend(extra[ep : ep + y])
        oldpos += x + z
        dp += x
        ep += y
    if len(out) != size or dp != len(diff) or ep != len(extra):
        raise ValueError("Incomplete patch")
    return bytes(out)


def assemble(
    base: Path, archive: Path, output: Path, old: dict, target: dict, archive_sha: str
) -> tuple[dict, dict, list[str]]:
    if sha(archive) != archive_sha:
        raise ValueError("External archive digest differs")
    baseline = manifest((base / "install_manifest.json").read_bytes(), old["manifest_sha256"])
    verify(base, baseline)
    if output.exists():
        raise FileExistsError("Fresh target assembly required")
    no_links(output)
    with zipfile.ZipFile(archive) as packet:
        items = packet.infolist()
        names = [i.filename for i in items]
        if (
            len(names) != len({n.casefold() for n in names})
            or sum(i.file_size for i in items) > MAX_TOTAL
            or any(
                i.file_size > MAX_FILE or (i.external_attr >> 16) & 0o170000 == 0o120000
                for i in items
            )
        ):
            raise ValueError("Unsafe/oversized ZIP members")
        for name in names:
            if name not in {
                "update.json",
                "delete.json",
                "install_manifest.json",
                "version.json",
                "update_database.py",
                "vira-updater.exe",
                "private-source-anchor.json",
            }:
                if name.startswith("files/"):
                    relative(name[6:])
                elif name.startswith("patches/") and name.endswith(".bsdiff"):
                    relative(name[8:-7])
                else:
                    raise ValueError("Unexpected delta member")
        if (
            "private-source-anchor.json" in names
            and read(packet.read("private-source-anchor.json")) != target
        ):
            raise ValueError("Target anchor differs from externally verified ZIP")
        plan = read(packet.read("update.json"))
        target_raw = packet.read("install_manifest.json")
        final = manifest(target_raw, target["manifest_sha256"])
        if read((base / "version.json").read_bytes())["version"] != plan["base_version"]:
            raise ValueError("Wrong installed base version")
        if read(packet.read("version.json"))["version"] != plan["target_version"]:
            raise ValueError("Wrong target version")
        if old.get("schema") == 2 and old["version"] != plan["base_version"]:
            raise ValueError("Independent old anchor version differs")
        if target.get("schema") == 2 and target["version"] != plan["target_version"]:
            raise ValueError("Independent target anchor version differs")
        if target.get("schema", 1) < old.get("schema", 1):
            raise ValueError("Private anchor contract downgrade forbidden")
        changed = {n for n in set(baseline) | set(final) if baseline.get(n) != final.get(n)}
        ops = plan["operations"]
        if len(ops) != len(changed) or {o["path"] for o in ops} != changed:
            raise ValueError("Delta operations not exactly changed files")
        required = set()
        for op in ops:
            name = relative(op["path"])
            kind = op["op"]
            expected = (
                "delete" if name not in final else ("add" if name not in baseline else "replace")
            )
            if kind != expected and not (kind == "patch" and expected == "replace"):
                raise ValueError("Delta operation/base differs")
            if kind != "delete" and (
                op.get("sha256") != final[name]["sha256"] or op.get("size") != final[name]["size"]
            ):
                raise ValueError("Operation target metadata differs")
            if kind == "patch":
                member = op["patch"]
                if member != "patches/" + name + ".bsdiff":
                    raise ValueError("Patch member binding differs")
                required.add(member)
            elif kind != "delete":
                required.add("files/" + name)
        if {n for n in names if n.startswith(("files/", "patches/"))} != required:
            raise ValueError("Unchanged/extra/missing delta content")
        for member, digest in plan["hashes"].items():
            if member not in names or hashlib.sha256(packet.read(member)).hexdigest() != digest:
                raise ValueError("Member hash differs")
        if not required <= set(plan["hashes"]):
            raise ValueError("Missing delta member hashes")
        output.mkdir(parents=True)
        for name in baseline:
            destination = output / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(base / name, destination)
        for op in ops:
            name = op["path"]
            destination = output / name
            if op["op"] == "delete":
                destination.unlink()
                continue
            data = (
                patch((base / name).read_bytes(), packet.read(op["patch"]), final[name]["size"])
                if op["op"] == "patch"
                else packet.read("files/" + name)
            )
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (output / "install_manifest.json").write_bytes(target_raw)
    verify(output, final)
    return baseline, final, sorted(changed)


def atomic(path: Path, raw: bytes) -> None:
    no_links(path)
    temporary = path.with_name(path.name + ".transaction-" + secrets.token_hex(8))
    created = False
    try:
        with temporary.open("xb") as stream:
            created = True
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if created and temporary.exists():
            no_links(temporary)
            temporary.unlink()


def stop(home: Path, root: Path) -> None:
    active_path = home / "active-launch.json"
    if not active_path.exists():
        if (home / "state/.desktop.lock").exists():
            raise ValueError("Unowned desktop lifetime lock")
        return
    active = read(active_path.read_bytes())
    if active["payload_root"] != str(root) or len(active["launch_id"]) != 32:
        raise ValueError("Foreign installed process")
    launch = home / "state/launches" / active["launch_id"]
    no_links(launch)
    ready = read((launch / "ready.json").read_bytes())
    with (launch / "stop.json").open("xb") as stream:
        stream.write(json.dumps(dict(pid=ready["pid"], launch_id=active["launch_id"])).encode())
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if not active_path.exists() and (launch / "completed.json").exists():
            completed = read((launch / "completed.json").read_bytes())
            if (
                completed["graceful_shutdown"] is True
                and not (home / "state/.desktop.lock").exists()
            ):
                return
        time.sleep(0.1)
    raise TimeoutError("Old installed process did not gracefully release native runtime")


def start(home: Path, root: Path, token: str, options: dict, log: Path) -> subprocess.Popen:
    env = dict(os.environ, VIRA_PRIVATE_UPDATE_TOKEN=token)
    no_links(log)
    # Fresh transaction-owned diagnostics, never discard a rejected startup.
    # Closing the parent's handle does not close the child's inherited stream.
    with log.open("xb") as diagnostic:
        process = subprocess.Popen(
            [
                str(root / "python/python.exe"),
                "-I",
                "-S",
                "-B",
                "-X",
                "utf8",
                str(root / "app/private_installed_source.py"),
            ],
            env=env,
            cwd=home,
            stdout=diagnostic,
            stderr=subprocess.STDOUT,
        )
    deadline = time.monotonic() + 90
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Installed target exited before readiness")
            active = home / "active-launch.json"
            if active.exists():
                info = read(active.read_bytes())
                ready = home / "state/launches" / info["launch_id"] / "ready.json"
                if ready.exists():
                    receipt = read(ready.read_bytes())
                    url = f"http://127.0.0.1:{options['port']}"
                    if receipt["url"].rstrip("/") != url or info["payload_root"] != str(root):
                        raise ValueError("Foreign installed readiness receipt")
                    with urllib.request.urlopen(
                        url + "/api/v1/health/ready", timeout=3
                    ) as response:
                        health = json.load(response)
                    stamp = read((root / "version.json").read_bytes())
                    with urllib.request.urlopen(url + "/", timeout=3) as response:
                        build = response.headers.get("X-VIRA-SPA-Build")
                    if (
                        health["status"] == "ready"
                        and health.get("alembic_revision")
                        and build == stamp["spa_build"]
                    ):
                        return process
            time.sleep(0.2)
        raise TimeoutError("Installed target readiness deadline expired")
    except BaseException:
        # Only the process tree THIS transaction spawned. Never kill by image name.
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            timeout=15,
            check=False,
        )
        process.wait(timeout=15)
        # A forcibly stopped bridge cannot run finally; retain stale state rather
        # than erase an unverified app lock. Rollback will report failure safely.
        raise


def process_definitely_dead(pid: int) -> bool:
    """Windows handle query only. Unknown/inaccessible/reused live PID fails closed."""
    if os.name != "nt":
        raise ValueError("Windows process handles required")
    if type(pid) is not int or not 0 < pid < 2**32:
        raise ValueError("Positive Windows PID required")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000 | 0x00100000, False, pid)  # query + synchronize
    if not handle:
        if ctypes.get_last_error() == 87:  # Invalid parameter: no such process.
            return True
        raise RuntimeError("Process ownership/death cannot be established")
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        if result == 0:
            return True
        if result == 258:
            return False
        raise RuntimeError("Process handle state is unknown")
    finally:
        kernel.CloseHandle(handle)


def inspect_recovery(
    root: Path,
    home: Path,
    attempt: Path,
    archive: Path,
    archive_sha256: str,
    old_anchor_sha256: str,
    database_fingerprint: str,
) -> dict:
    """READ ONLY eligibility, NOT recovery or permission to remove stale locks.

    Only a prepared, cold, owned schema2 transaction with independent external
    archive/old-anchor/DB fingerprints can qualify. Live/inaccessible PID, desktop
    or channel guards, terminal receipts, partial/missing backups and corruption
    are rejected. The recovery executor acquires the global mutex and repeats validation;
    this result is NOT a reusable authorization capability.
    """
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Private disposable Windows CI inspection only")
    for digest in (archive_sha256, old_anchor_sha256, database_fingerprint):
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(c not in "0123456789abcdef" for c in digest)
        ):
            raise ValueError("Independent external digest required")
    runner = Path(os.environ["RUNNER_TEMP"])
    if home != Path(os.environ["LOCALAPPDATA"]) / "VIRA/private-native-installed":
        raise ValueError("Foreign recovery profile")
    for p in (root, home, attempt, archive):
        no_links(p)
        if not p.is_absolute() or ".." in p.parts or p == runner or not p.is_relative_to(runner):
            raise ValueError("Disposable owned recovery paths required")
    for a, b in ((root, home), (root, attempt), (home, attempt)):
        if a.is_relative_to(b) or b.is_relative_to(a):
            raise ValueError("Disjoint recovery payload/state/attempt required")
    state = home / "state"
    for parent in (state, attempt):
        no_links(parent)
        for p in parent.rglob("*"):
            no_links(p)
    if read((state / "private-desktop-state.json").read_bytes()) != dict(
        schema=1,
        role="PRIVATE_SOURCE_DESKTOP_STATE",
        payload_root=str(root),
    ):
        raise ValueError("Foreign private recovery state")

    def require_offline():
        for p in (
            home / ".native-channel.lock",
            home / "active-launch.json",
            state / ".desktop.lock",
            attempt / "result.json",
        ):
            no_links(p)
            if p.exists():
                raise ValueError(
                    "Live/unknown desktop/channel or terminal transaction; refuse recovery"
                )

    require_offline()
    no_links(home / "anchor.json")
    lock_path = home / ".native-update.lock"
    no_links(lock_path)
    lock = read(lock_path.read_bytes())
    if (
        set(lock) != {"token", "pid"}
        or type(lock["pid"]) is not int
        or not 0 < lock["pid"] < 2**32
        or not isinstance(lock["token"], str)
        or len(lock["token"]) != 64
        or any(c not in "0123456789abcdef" for c in lock["token"])
    ):
        raise ValueError("Unknown native guard owner")
    token = lock["token"]
    if not process_definitely_dead(lock["pid"]):
        raise ValueError("Native controller PID is still live; no stale-lock removal")
    if (state / "data/updates/.update.lock").read_bytes() != token.encode():
        raise ValueError("Recovery write guard owner differs")
    journal = read((attempt / "journal.json").read_bytes())
    if (
        type(journal.get("schema")) is not int
        or journal.get("schema") != 1
        or journal.get("role") != "PRIVATE_NATIVE_TRANSACTION_JOURNAL"
        or journal.get("state") != "prepared"
        or journal.get("archive_sha256") != archive_sha256
        or journal.get("old_anchor_sha256") != old_anchor_sha256
        or journal.get("database_fingerprint") != database_fingerprint
        or journal.get("recovery_context")
        != dict(
            install_root=str(root),
            home=str(home),
            controller_pid=lock["pid"],
            guard_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
        )
    ):
        raise ValueError("Prepared recovery journal/external authority differs")
    old_raw = (attempt / "anchor-before.json").read_bytes()
    old = read(old_raw)
    if (
        hashlib.sha256(old_raw).hexdigest() != old_anchor_sha256
        or old.get("schema") != 2
        or old.get("role") != "PRIVATE_SOURCE_INSTALLED_ANCHOR"
    ):
        raise ValueError("Independent schema2 old anchor required")
    backup = attempt / "files-before"
    baseline = manifest((backup / "install_manifest.json").read_bytes(), old["manifest_sha256"])
    if sha(archive) != archive_sha256:
        raise ValueError("Authorized recovery archive changed")
    with zipfile.ZipFile(archive) as packet:
        names = packet.namelist()
        if len(names) != len({n.casefold() for n in names}):
            raise ValueError("Ambiguous recovery ZIP")
        for name in ("private-source-anchor.json", "install_manifest.json"):
            if packet.getinfo(name).file_size > 16 * 1024 * 1024:
                raise ValueError("Oversized recovery metadata")
        target_raw = packet.read("private-source-anchor.json")
        target = read(target_raw)
        if (
            target.get("schema") != 2
            or target.get("role") != old["role"]
            or hashlib.sha256(target_raw).hexdigest() != journal.get("target_anchor_sha256")
        ):
            raise ValueError("Authorized target anchor differs")
        final = manifest(packet.read("install_manifest.json"), target["manifest_sha256"])
    current = (home / "anchor.json").read_bytes()
    if current not in (old_raw, target_raw):
        raise ValueError("Current anchor belongs to neither authorized version")
    changed = sorted(n for n in set(baseline) | set(final) if baseline.get(n) != final.get(n))
    if journal.get("changed") != changed:
        raise ValueError("Recovery file set differs from authorized delta")
    installed = set()
    for p in root.rglob("*"):
        no_links(p)
        if p.is_file():
            installed.add(p.relative_to(root).as_posix())
    if not installed <= set(baseline) | set(final) | {"install_manifest.json"}:
        raise ValueError("Unowned files/atomic debris require separate recovery review")
    for n in set(baseline) - set(changed):
        p = root / n
        if (
            n not in installed
            or p.stat().st_size != baseline[n]["size"]
            or sha(p) != baseline[n]["sha256"]
        ):
            raise ValueError("Unchanged installed file is not recoverable from changed-file backup")
    expected = {n for n in changed if n in baseline} | {"install_manifest.json"}
    if {p.relative_to(backup).as_posix() for p in backup.rglob("*") if p.is_file()} != expected:
        raise ValueError("Incomplete/foreign cold file backup")
    for n in changed:
        if n in baseline and (
            (backup / n).stat().st_size != baseline[n]["size"]
            or sha(backup / n) != baseline[n]["sha256"]
        ):
            raise ValueError("Cold recovery file backup corrupt")
    # Execute only the independently anchored OLD stdlib-only snapshot verifier,
    # never a script from the newly downloaded or partially applied target.
    name = "scripts/update_database.py"
    tool = backup / name if name in changed else root / name
    no_links(tool)
    if tool.stat().st_size != baseline[name]["size"] or sha(tool) != baseline[name]["sha256"]:
        raise ValueError("Old database verifier is not anchored")
    bundle = attempt / "database-rollback"
    metadata = read((bundle / "metadata.json").read_bytes())
    database = state / "data/data/vira.sqlite3"
    if (
        set(metadata) != {"schema_version", "database", "sha256", "fingerprint"}
        or type(metadata["schema_version"]) is not int
        or metadata["schema_version"] != 1
        or not isinstance(metadata["database"], str)
        or Path(metadata["database"]) != database
        or metadata["fingerprint"] != database_fingerprint
    ):
        raise ValueError("Recovery database destination/fingerprint differs")
    snapshot = bundle / "database.sqlite3"
    if sha(snapshot) != metadata["sha256"]:
        raise ValueError("Cold recovery database backup corrupt")
    dbtool = runpy.run_path(str(tool))
    if dbtool["fingerprint"](snapshot) != database_fingerprint:
        raise ValueError("Independent accounting fingerprint differs")
    # Recheck guards after all slow reads; no elapsed-time/PID-file heuristic.
    require_offline()
    no_links(home / "anchor.json")
    if (home / "anchor.json").read_bytes() != current:
        raise ValueError("Recovery anchor changed during inspection")
    if (
        read(lock_path.read_bytes()) != lock
        or not process_definitely_dead(lock["pid"])
        or (state / "data/updates/.update.lock").read_bytes() != token.encode()
    ):
        raise ValueError("Recovery ownership changed during inspection")
    return dict(
        role="PRIVATE_COLD_PREPARED_RECOVERY_INSPECTION_NOT_EXECUTION",
        eligible_for_offline_recovery=True,
        independent_old_anchor_sha256=old_anchor_sha256,
        archive_sha256=archive_sha256,
        database_fingerprint=database_fingerprint,
        changed=changed,
        controller_pid=lock["pid"],
        recovery_executed=False,
        locks_released=False,
        authorization_reusable=False,
        crash_recovery_proven=False,
        phase3_complete=False,
        release_authorized=False,
    )



@contextmanager
def recovery_mutex():
    """Own the SAME Windows global mutex as the compiled updater, never age locks."""
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Private disposable Windows CI recovery only")
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = (wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR)
    kernel.CreateMutexW.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.ReleaseMutex.argtypes = (wintypes.HANDLE,)
    kernel.ReleaseMutex.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.CreateMutexW(None, False, "Global\\VIRA-Updater")
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    owned = False
    try:
        result = kernel.WaitForSingleObject(handle, 0)
        if result not in (0, 0x80):  # Acquired or abandoned: ALWAYS revalidate below.
            raise RuntimeError("Another updater owns the global mutex or ownership is unknown")
        owned = True
        yield
    finally:
        try:
            if owned and not kernel.ReleaseMutex(handle):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel.CloseHandle(handle)


def recover(
    root: Path, home: Path, attempt: Path, archive: Path,
    archive_sha256: str, old_anchor_sha256: str, database_fingerprint: str,
) -> dict:
    """Explicit private recovery: restore OLD bytes/DB, restart and verify, then unlock.

    No public auto-activation, stale-channel deletion, force-kill or inspection
    ticket. The global mutex is acquired BEFORE inspection; every eligibility
    check is repeated immediately before writes. Failure retains the guards.
    """
    with recovery_mutex():
        args = (root, home, attempt, archive, archive_sha256,
                old_anchor_sha256, database_fingerprint)
        proof = inspect_recovery(*args)
        lock = home / ".native-update.lock"
        owner_raw = lock.read_bytes()
        owner = read(owner_raw)
        token = owner["token"]
        guard = home / "state/data/updates/.update.lock"
        old_raw = (attempt / "anchor-before.json").read_bytes()
        old = read(old_raw)
        backup = attempt / "files-before"
        baseline = manifest((backup / "install_manifest.json").read_bytes(), old["manifest_sha256"])
        state = home / "state"
        bundle = attempt / "database-rollback"
        database_metadata = (bundle / "metadata.json").read_bytes()
        snapshot_sha256 = read(database_metadata)["sha256"]

        def assets():
            secret = state / "session.secret"
            no_links(secret)
            values = {"session.secret": sha(secret)}
            for path in (state / "data/receipts").rglob("*"):
                no_links(path)
                if path.is_file():
                    values[path.relative_to(state).as_posix()] = sha(path)
            return values

        preserved = assets()
        if inspect_recovery(*args) != proof or lock.read_bytes() != owner_raw:
            raise ValueError("Recovery eligibility changed before writes")
        # Rebuild only the authorized changed-file set, not an arbitrary tree.
        for name in proof["changed"]:
            destination = root / name
            no_links(destination)
            if name not in baseline:
                if destination.exists():
                    destination.unlink()
            else:
                data = (backup / name).read_bytes()
                if hashlib.sha256(data).hexdigest() != baseline[name]["sha256"]:
                    raise ValueError("Recovery backup changed before restore")
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic(destination, data)
        atomic(root / "install_manifest.json", (backup / "install_manifest.json").read_bytes())
        verify(root, baseline)
        if sha(root / "install_manifest.json") != old["manifest_sha256"]:
            raise ValueError("Restored old manifest digest differs")
        atomic(home / "anchor.json", old_raw)
        # Full old-tree verification ABOVE authenticates both scripts before runpy.
        dbtool = runpy.run_path(str(root / "scripts/update_database.py"))
        if ((bundle / "metadata.json").read_bytes() != database_metadata
                or sha(bundle / "database.sqlite3") != snapshot_sha256):
            raise ValueError("Recovery database snapshot changed before restore")
        dbtool["restore"](bundle)
        database = state / "data/data/vira.sqlite3"
        if dbtool["fingerprint"](database) != database_fingerprint or assets() != preserved:
            raise ValueError("Restored database/session/receipts differ")
        bridge = runpy.run_path(str(root / "app/private_installed_source.py"))
        old = bridge["anchor"](old)
        with zipfile.ZipFile(archive) as packet:
            target = bridge["anchor"](read(packet.read("private-source-anchor.json")))
        restarted = False
        try:
            start(home, root, token, old, attempt / ("recovery-startup-" + secrets.token_hex(16) + ".log"))
            restarted = True
            # The restarted app remains write-quarantined through these checks.
            verify(root, baseline)
            if (dbtool["fingerprint"](database) != database_fingerprint
                    or assets() != preserved
                    or (home / "anchor.json").read_bytes() != old_raw
                    or lock.read_bytes() != owner_raw
                    or guard.read_bytes() != token.encode()
                    or (home / ".native-channel.lock").exists()
                    or not process_definitely_dead(owner["pid"])):
                raise ValueError("Recovery health/data/ownership changed before terminal publication")
            journal = read((attempt / "journal.json").read_bytes())
            journal.update(state="rolled_back", recovery_verified=True, recovery_pid=os.getpid())
            atomic(attempt / "result.json", (json.dumps(journal, indent=2) + "\n").encode())
            result = dict(
                state="rolled_back", machine_state="rolled_back", verified=False,
                recovery_verified=True, target_version=target["version"],
                helper_pid=os.getpid(), attempt_id=attempt.name,
                log_path=str(attempt), error_fa="نسخه و دادهٔ قبلی پس از قطع تراکنش بازیابی و سلامت آن تأیید شد.",
            )
            atomic(state / "data/updates/last-result.json", (json.dumps(result) + "\n").encode())
            # Terminal receipts alone NEVER unlock writes. Recheck exact ownership.
            if lock.read_bytes() != owner_raw or guard.read_bytes() != token.encode():
                raise ValueError("Recovery guard ownership changed during publication")
            guard.unlink()
            try:
                lock.unlink()
            except BaseException:
                # A normal second-unlink I/O failure must keep the original pair.
                # Never replace an intervening foreign guard; a surviving native
                # guard alone also keeps the application's write gate closed.
                if lock.exists() and lock.read_bytes() == owner_raw and not guard.exists():
                    with guard.open("xb") as stream:
                        stream.write(token.encode())
                        stream.flush()
                        os.fsync(stream.fileno())
                raise
            return dict(
                role="PRIVATE_PREPARED_RECOVERY_EXECUTED_NOT_CRASH_ACCEPTANCE",
                recovery_executed=True, restored_old_tree=True,
                database_fingerprint=database_fingerprint, app_ready_verified=True,
                session_and_receipts_preserved=True, locks_released=True,
                crash_recovery_proven=False, phase3_complete=False, release_authorized=False,
            )
        except BaseException:
            if restarted:
                stop(home, root)  # Only this recovery's own gracefully restarted app.
            raise


def crash_checkpoint(selected: str | None, point: str, attempt: Path, token: str, applied: int) -> None:
    """Private CI process cut at a durable boundary; never normal rollback/success."""
    if selected != point:
        return
    if (point not in {"FIRST_FILE", "AFTER_APPLY"} or os.name != "nt"
            or os.environ.get("GITHUB_ACTIONS") != "true"):
        raise ValueError("Explicit private Windows crash checkpoint required")
    atomic(attempt / "process-cut.json", (json.dumps(dict(
        role="PRIVATE_CONTROLLER_ABRUPT_EXIT_73", point=point, pid=os.getpid(),
        applied_file_count=applied, guard_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )) + "\n").encode())
    os._exit(73)  # Deliberately bypass except/finally; the external client must recover.


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("install-root", "archive", "attempt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--target-anchor", type=Path)
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--old-anchor-sha256")
    parser.add_argument("--database-fingerprint")
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--force-failure-after-apply", action="store_true")
    parser.add_argument("--crash-point", choices=("FIRST_FILE", "AFTER_APPLY"))
    args = parser.parse_args()
    if args.recover:
        if (not args.old_anchor_sha256 or not args.database_fingerprint
                or args.force_failure_after_apply or args.crash_point or args.target_anchor is not None):
            parser.error("Explicit recovery needs independent old-anchor/DB digests, not update options")
        if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
            raise ValueError("Private disposable Windows CI recovery only")
        result = recover(
            args.install_root,
            Path(os.environ["LOCALAPPDATA"]) / "VIRA/private-native-installed",
            args.attempt, args.archive, args.archive_sha256,
            args.old_anchor_sha256, args.database_fingerprint,
        )
        print(json.dumps(result))
        return
    if args.target_anchor is None or args.old_anchor_sha256 or args.database_fingerprint:
        parser.error("Update requires target-anchor; recovery is never inferred")
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true":
        raise ValueError("Private installed native updater Windows CI only")
    root, attempt = args.install_root, args.attempt
    runner, profile = Path(os.environ["RUNNER_TEMP"]), Path(os.environ["LOCALAPPDATA"])
    for path in (root, attempt, profile, args.archive, args.target_anchor):
        no_links(path)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or not path.is_relative_to(runner)
            or path == runner
        ):
            raise ValueError("Disposable runner-owned paths required")
    home = profile / "VIRA/private-native-installed"
    if (
        root.is_relative_to(home)
        or home.is_relative_to(root)
        or attempt.is_relative_to(root)
        or root.is_relative_to(attempt)
        or attempt.is_relative_to(home)
    ):
        raise ValueError("Disjoint installed payload, private state and transaction required")
    pin = home / "anchor.json"
    no_links(pin)
    state = home / "state"
    no_links(state)
    for child in state.rglob("*"):
        no_links(child)
    if read((state / "private-desktop-state.json").read_bytes()) != {
        "schema": 1,
        "role": "PRIVATE_SOURCE_DESKTOP_STATE",
        "payload_root": str(root),
    }:
        raise ValueError("Private business state belongs to another installation")
    old_raw, target_raw = pin.read_bytes(), args.target_anchor.read_bytes()
    old_doc = read(old_raw)
    verify(
        root, manifest((root / "install_manifest.json").read_bytes(), old_doc["manifest_sha256"])
    )
    bridge = runpy.run_path(str(root / "app/private_installed_source.py"))
    old, target = [bridge["anchor"](read(raw)) for raw in (old_raw, target_raw)]
    if args.crash_point and (old["schema"] != 2 or target["schema"] != 2
                             or args.force_failure_after_apply):
        raise ValueError("Crash selection requires schema2 private CI and excludes forced rollback")
    attempt.mkdir(parents=True, exist_ok=False)
    token = secrets.token_hex(32)
    lock = home / ".native-update.lock"
    with lock.open("xb") as stream:
        stream.write(json.dumps(dict(token=token, pid=os.getpid())).encode())
    stopped = mutated = False
    safe_terminal = True
    update_lock = home / "state/data/updates/.update.lock"
    try:
        assembled = attempt / "VIRA هدف فارسی ! &"
        baseline, final, changed = assemble(
            root, args.archive, assembled, old, target, args.archive_sha256
        )
        subprocess.run(
            [
                str(assembled / "python/python.exe"),
                "-I",
                "-S",
                "-B",
                "-X",
                "utf8",
                str(assembled / "app/private_installed_source.py"),
                "--verify",
                str(args.target_anchor),
            ],
            check=True,
            timeout=120,
            cwd=home,
        )
        stop(home, root)
        stopped = True
        safe_terminal = False
        update_lock.parent.mkdir(parents=True, exist_ok=True)
        with update_lock.open("xb") as stream:
            stream.write(token.encode())
        dbtool = runpy.run_path(str(root / "scripts/update_database.py"))
        database = home / "state/data/data/vira.sqlite3"
        snapshot = dbtool["snapshot"](database, attempt / "database-rollback")
        backup = attempt / "files-before"
        for name in changed + ["install_manifest.json"]:
            if (root / name).exists():
                destination = backup / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(root / name, destination)
        atomic(attempt / "anchor-before.json", old_raw)
        for name in changed + ["install_manifest.json"]:
            if (backup / name).exists() and sha(backup / name) != sha(root / name):
                raise ValueError("Cold file backup differs")
        journal = dict(
            schema=1,
            role="PRIVATE_NATIVE_TRANSACTION_JOURNAL",
            old_anchor_sha256=hashlib.sha256(old_raw).hexdigest(),
            target_anchor_sha256=hashlib.sha256(target_raw).hexdigest(),
            archive_sha256=args.archive_sha256,
            changed=changed,
            database_fingerprint=snapshot["fingerprint"],
            recovery_context=dict(
                install_root=str(root),
                home=str(home),
                controller_pid=os.getpid(),
                guard_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
            ),
            state="prepared",
        )
        atomic(attempt / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        mutated = True
        for applied, name in enumerate(changed, 1):
            destination = root / name
            no_links(destination)
            if name not in final:
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic(destination, (assembled / name).read_bytes())
            if applied == 1:
                crash_checkpoint(args.crash_point, "FIRST_FILE", attempt, token, applied)
        atomic(root / "install_manifest.json", (assembled / "install_manifest.json").read_bytes())
        verify(root, final)
        atomic(pin, target_raw)
        crash_checkpoint(args.crash_point, "AFTER_APPLY", attempt, token, len(changed))
        if args.force_failure_after_apply:
            raise RuntimeError("Forced private failure after actual file operations")
        start(home, root, token, target, attempt / "target-startup.log")
        journal["state"] = "committed"
        atomic(attempt / "result.json", (json.dumps(journal, indent=2) + "\n").encode())
        safe_terminal = True
    except BaseException:
        if mutated:
            stop(home, root)
            for name in changed:
                if name not in baseline:
                    if (root / name).exists():
                        (root / name).unlink()
                else:
                    atomic(root / name, (backup / name).read_bytes())
            atomic(root / "install_manifest.json", (backup / "install_manifest.json").read_bytes())
            verify(root, baseline)
            atomic(pin, old_raw)
            dbtool["restore"](attempt / "database-rollback")
        if stopped:
            start(home, root, token, old, attempt / "rollback-startup.log")
        if mutated:
            journal["state"] = "rolled_back"
            atomic(attempt / "result.json", (json.dumps(journal, indent=2) + "\n").encode())
        safe_terminal = True
        raise
    finally:
        if safe_terminal and update_lock.exists() and update_lock.read_bytes() == token.encode():
            update_lock.unlink()
        if read(lock.read_bytes()) != dict(token=token, pid=os.getpid()):
            raise RuntimeError("Transaction lock ownership changed")
        if safe_terminal:
            lock.unlink()


if __name__ == "__main__":
    main()
