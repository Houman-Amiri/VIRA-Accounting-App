"""Set a new password for an existing NOA user, from the command line.

Why this exists: the login password is chosen once, on the very first start of
NOA (``start_noa.cmd`` generates it and writes
``%LOCALAPPDATA%\\NOA\\first-run-credentials.txt``). The installed app has no
screen for changing it yet, and ``NOA_ADMIN_PASSWORD`` only seeds a *new*
database — it does not re-key an existing ``owner`` row. This script is the
supported offline way to replace that password.

Rules it follows, so it cannot corrupt the books:

* the app must be closed — writing while the server holds the database is
  refused (SQLite would still serialise it, but a half-written login is worse
  than a clear message);
* the database is backed up next to itself before a single row is touched;
* the hash is produced by the application's own ``hash_password`` (Argon2id,
  the same parameters the login verifies with), never a hand-rolled variant;
* the row is updated by SQL on the primary key, in one transaction, and the
  result is verified by reading it back and checking the new password against
  it.

Usage (from the installed folder, ``D:\\3D PRINT\\NOA-Accounting``)::

    python\\python.exe scripts\\reset_owner_password.py
    python\\python.exe scripts\\reset_owner_password.py --username owner
    python\\python.exe scripts\\reset_owner_password.py --database "C:\\path\\noa.sqlite3"

The password is asked twice and never echoed; ``NOA_NEW_PASSWORD`` in the
environment is also accepted (for a scripted run).
"""

from __future__ import annotations

import argparse
import getpass
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

MIN_LENGTH = 8
APP_DIR_NAME = "NOA"
LEGACY_APP_DIR_NAME = "VIRA"
DATABASE_FILE_NAME = "noa.sqlite3"
LEGACY_DATABASE_FILE_NAME = "vira.sqlite3"


_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def _fa(value: int | str) -> str:
    """Persian numerals, so a message the owner reads has no Latin digits."""
    return str(value).translate(_PERSIAN_DIGITS)


def _fail(message: str) -> None:
    print(f"\n[NOA] {message}")
    raise SystemExit(1)


def _find_app_root() -> Path | None:
    """Walk up from this file until a folder with the application package is found."""
    here = Path(__file__).resolve()
    for candidate in [here.parent, *here.parents]:
        if (candidate / "app" / "security" / "passwords.py").is_file():
            return candidate
    return None


def _load_hashers(app_root: Path | None):
    """The app's own Argon2id helpers, else pwdlib with the same parameters."""
    if app_root is not None:
        for path in (app_root / "site-packages", app_root):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        try:
            from app.security.passwords import hash_password, verify_password

            return hash_password, verify_password
        except Exception:  # pragma: no cover - depends on the installed payload
            pass
    try:
        from pwdlib import PasswordHash
    except Exception:
        _fail(
            "کتابخانهٔ رمزنگاری پیدا نشد. این فایل را داخل پوشهٔ نصب NOA اجرا کنید "
            "(کنار پوشهٔ python)، یا از python\\python.exe خودِ نصب استفاده کنید."
        )
    hasher = PasswordHash.recommended()

    def hash_password(password: str) -> str:
        if len(password) < MIN_LENGTH:
            raise ValueError("password must be at least 8 characters")
        return hasher.hash(password)

    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return hasher.verify(password, password_hash)
        except Exception:
            return False

    return hash_password, verify_password


def _default_databases() -> list[Path]:
    local = os.environ.get("LOCALAPPDATA")
    if not local:
        return []
    base = Path(local)
    return [
        base / APP_DIR_NAME / "data" / DATABASE_FILE_NAME,
        base / LEGACY_APP_DIR_NAME / "data" / LEGACY_DATABASE_FILE_NAME,
    ]


def _resolve_database(explicit: str | None) -> Path:
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            _fail(f"دیتابیس در این مسیر پیدا نشد: {path}")
        return path
    from_env = os.environ.get("SQLITE_DATABASE_PATH")
    if from_env and Path(from_env).is_file():
        return Path(from_env)
    candidates = _default_databases()
    for path in candidates:
        if path.is_file():
            return path
    looked = "\n".join(f"  - {p}" for p in candidates) or "  (LOCALAPPDATA تعریف نشده است)"
    _fail(f"دیتابیس NOA پیدا نشد. این مسیرها بررسی شدند:\n{looked}")
    raise AssertionError("unreachable")


def _app_is_running(database: Path) -> bool:
    """A live server keeps a -wal or -shm beside the database and holds it open."""
    for suffix in ("-wal", "-shm"):
        sidecar = database.with_name(database.name + suffix)
        if sidecar.exists():
            return True
    return False


def _read_new_password(cli_password: str | None) -> str:
    password = cli_password or os.environ.get("NOA_NEW_PASSWORD")
    if password is None:
        print("[NOA] رمز تازه را وارد کنید (چیزی نمایش داده نمی‌شود).")
        password = getpass.getpass("رمز تازه: ")
        if password != getpass.getpass("تکرار رمز تازه: "):
            _fail("دو رمزی که وارد کردید یکسان نیستند؛ چیزی تغییر نکرد.")
    if len(password) < MIN_LENGTH:
        _fail("رمز باید حداقل " + _fa(MIN_LENGTH) + " نویسه باشد؛ چیزی تغییر نکرد.")
    return password


def _backup(database: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = database.with_name(f"{database.name}.before-password-change-{stamp}.bak")
    shutil.copy2(database, backup)
    return backup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Set a new password for an existing NOA user.")
    parser.add_argument("--database", help="مسیر فایل دیتابیس (پیش‌فرض: %%LOCALAPPDATA%%\\NOA\\data\\noa.sqlite3)")
    parser.add_argument("--username", default="owner", help="کاربری که رمزش عوض می‌شود (پیش‌فرض: owner)")
    parser.add_argument("--password", help="رمز تازه (اگر ندهید، پرسیده می‌شود)")
    parser.add_argument(
        "--allow-running",
        action="store_true",
        help="حتی اگر برنامه باز باشد ادامه بده (توصیه نمی‌شود)",
    )
    args = parser.parse_args(argv)

    database = _resolve_database(args.database)
    if _app_is_running(database) and not args.allow_running:
        _fail(
            "به‌نظر می‌رسد برنامه باز است (فایل‌های ‎-wal/-shm‎ کنار دیتابیس هست). "
            "اول NOA را ببندید (پنجرهٔ کنسولش را ببندید) و بعد این اسکریپت را دوباره اجرا کنید. "
            "اگر مطمئنید باز نیست، با --allow-running اجرا کنید."
        )

    app_root = _find_app_root()
    hash_password, verify_password = _load_hashers(app_root)
    password = _read_new_password(args.password)

    try:
        new_hash = hash_password(password)
    except ValueError as exc:
        _fail(f"{exc}؛ چیزی تغییر نکرد.")

    # Read first: a request for a user that does not exist must not even leave a
    # backup behind, and must never be the reason a row is written.
    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            "SELECT id, role FROM users WHERE username = ?", (args.username,)
        ).fetchone()
        if row is None:
            connection.rollback()
            _fail(f"کاربری با نام «{args.username}» در این دیتابیس نیست؛ چیزی تغییر نکرد.")
        user_id, role = row
        connection.rollback()
    finally:
        connection.close()

    backup = _backup(database)
    print(f"[NOA] نسخهٔ پشتیبان ساخته شد: {backup}")

    connection = sqlite3.connect(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id)
        )
        connection.commit()
        stored = connection.execute(
            "SELECT password_hash FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    except sqlite3.DatabaseError as exc:
        connection.rollback()
        _fail(f"نوشتن در دیتابیس ناموفق بود: {exc}")
    finally:
        connection.close()

    if stored is None or not verify_password(password, stored[0]):
        _fail(
            "رمز نوشته شد ولی بررسی دوباره موفق نبود. "
            f"نسخهٔ پشتیبان سالم است؛ آن را جای فایل اصلی برگردانید: {backup}"
        )

    print("\n[NOA] رمز تغییر کرد و بررسی شد.")
    print(f"[NOA] کاربر: {args.username}  (نقش: {role})")
    print(f"[NOA] دیتابیس: {database}")
    print("[NOA] نشست‌هایی که همین حالا در مرورگر بازند تا پایان عمرشان معتبر می‌مانند؛")
    print("      برای اینکه همه‌جا از حساب خارج شوید، برنامه را ببندید و فایل")
    print("      %LOCALAPPDATA%\\NOA\\session.secret را پاک کنید، بعد دوباره باز کنید.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
