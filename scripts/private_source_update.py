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


def start(home: Path, root: Path, token: str, options: dict) -> subprocess.Popen:
    env = dict(os.environ, VIRA_PRIVATE_UPDATE_TOKEN=token)
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
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("install-root", "archive", "target-anchor", "attempt"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--force-failure-after-apply", action="store_true")
    args = parser.parse_args()
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
            state="prepared",
        )
        atomic(attempt / "journal.json", (json.dumps(journal, indent=2) + "\n").encode())
        mutated = True
        for name in changed:
            destination = root / name
            no_links(destination)
            if name not in final:
                destination.unlink()
            else:
                destination.parent.mkdir(parents=True, exist_ok=True)
                atomic(destination, (assembled / name).read_bytes())
        atomic(root / "install_manifest.json", (assembled / "install_manifest.json").read_bytes())
        verify(root, final)
        atomic(pin, target_raw)
        if args.force_failure_after_apply:
            raise RuntimeError("Forced private failure after actual file operations")
        update_lock.unlink()
        start(home, root, token, target)
        safe_terminal = True
        journal["state"] = "committed"
        atomic(attempt / "result.json", (json.dumps(journal, indent=2) + "\n").encode())
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
        if update_lock.exists() and update_lock.read_bytes() == token.encode():
            update_lock.unlink()
        if stopped:
            start(home, root, token, old)
        safe_terminal = True
        if mutated:
            journal["state"] = "rolled_back"
            atomic(attempt / "result.json", (json.dumps(journal, indent=2) + "\n").encode())
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
