"""The offline password reset changes one hash, and only after a backup.

The owner's only way to replace the login password today is
``scripts/reset_owner_password.py`` (the app itself has no change-password
screen yet). It writes straight into the books' SQLite file, so the properties
worth pinning are the boring ones: the right row, the right hash algorithm, a
backup that really holds the old bytes, and no write at all when the request is
refused.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest
from pwdlib import PasswordHash

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "reset_owner_password.py"
_hasher = PasswordHash.recommended()
USERS_DDL = """
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    totp_secret_enc TEXT,
    created_at TEXT NOT NULL
)
"""


def _load_module():
    spec = importlib.util.spec_from_file_location("reset_owner_password", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _database(tmp_path: Path) -> Path:
    database = tmp_path / "noa.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute(USERS_DDL)
    connection.execute(
        "INSERT INTO users VALUES ('u1', 'owner', ?, 'OWNER', 1, NULL, '2026-01-01T00:00:00Z')",
        (_hasher.hash("oldpassword"),),
    )
    connection.execute(
        "INSERT INTO users VALUES ('u2', 'auditor', ?, 'AUDITOR', 1, NULL, '2026-01-01T00:00:00Z')",
        (_hasher.hash("oldpassword"),),
    )
    connection.commit()
    connection.close()
    return database


def _hashes(database: Path) -> dict[str, str]:
    connection = sqlite3.connect(database)
    try:
        return dict(connection.execute("SELECT username, password_hash FROM users"))
    finally:
        connection.close()


def _backups(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("*.before-password-change-*.bak"))


def test_it_rehashes_only_the_named_user(tmp_path, capsys) -> None:
    database = _database(tmp_path)
    module = _load_module()

    assert module.main(["--database", str(database), "--password", "brandnewpw9"]) == 0

    after = _hashes(database)
    assert _hasher.verify("brandnewpw9", after["owner"])
    assert not _hasher.verify("oldpassword", after["owner"])
    # an unrelated account is untouched, not re-hashed
    assert after["auditor"] == _hashes(database)["auditor"]
    assert _hasher.verify("oldpassword", after["auditor"])
    output = capsys.readouterr().out
    assert "رمز تغییر کرد" in output
    # the new password is never echoed
    assert "brandnewpw9" not in output


def test_the_backup_holds_the_previous_hash(tmp_path) -> None:
    database = _database(tmp_path)
    before = _hashes(database)
    module = _load_module()

    module.main(["--database", str(database), "--password", "brandnewpw9"])

    backups = _backups(tmp_path)
    assert len(backups) == 1
    restored = tmp_path / "restored.sqlite3"
    restored.write_bytes(backups[0].read_bytes())
    assert _hashes(restored) == before


def test_an_unknown_user_is_refused_without_writing_anything(tmp_path) -> None:
    database = _database(tmp_path)
    before = _hashes(database)
    module = _load_module()

    with pytest.raises(SystemExit) as raised:
        module.main(["--database", str(database), "--username", "nobody", "--password", "brandnewpw9"])

    assert raised.value.code == 1
    assert _hashes(database) == before
    assert _backups(tmp_path) == []


def test_a_short_password_is_refused_without_writing_anything(tmp_path) -> None:
    database = _database(tmp_path)
    before = _hashes(database)
    module = _load_module()

    with pytest.raises(SystemExit) as raised:
        module.main(["--database", str(database), "--password", "short"])

    assert raised.value.code == 1
    assert _hashes(database) == before
    assert _backups(tmp_path) == []


def test_it_refuses_while_the_server_still_holds_the_database(tmp_path) -> None:
    database = _database(tmp_path)
    before = _hashes(database)
    database.with_name(database.name + "-wal").write_bytes(b"")
    module = _load_module()

    with pytest.raises(SystemExit):
        module.main(["--database", str(database), "--password", "brandnewpw9"])

    assert _hashes(database) == before
