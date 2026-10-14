"""Representative-local-data database benchmark (Phase 4 §8).

Seeds a temporary on-disk SQLite database with N journal entries (2 splits
each) and times the queries that must stay fast on large registers:

* keyset page fetch (journal register)
* OFFSET page fetch (for comparison — the reason keyset is mandated)
* rollup view scan (v_account_balances)
* monthly snapshot computation
* LIKE search vs FTS5 search

Usage:  python scripts/benchmark_db.py [N_ENTRIES]   (default 25 000 = 50k splits)
"""

from __future__ import annotations

import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

BENCH_DESCRIPTION = "benchmark entry {i} — خرید و فروش"


def _time(fn, rounds: int = 5) -> float:
    samples = []
    for _ in range(rounds):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return statistics.median(samples) * 1000  # ms


def main() -> None:
    n_entries = int(sys.argv[1]) if len(sys.argv) > 1 else 25_000
    tmp = tempfile.mkdtemp(prefix="vira-bench-")
    db_path = Path(tmp) / "bench.sqlite3"
    os.environ["SQLITE_DATABASE_PATH"] = str(db_path)
    os.environ.setdefault("SESSION_SECRET", "bench-secret-that-is-long-enough-12345")

    from alembic.command import upgrade
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "backend" / "alembic"))
    upgrade(cfg, "head")

    from sqlalchemy import text

    from app.config import load_settings
    from app.db import Database
    from app.ids import uuid7

    db = Database(load_settings())
    acc_ids = []
    with db.write_session() as s:
        for code, name, typ, norm in (
            [("1010", "صندوق", "ASSET", "DEBIT"), ("3010", "سرمایه", "EQUITY", "CREDIT")]
        ):
            aid = uuid7()
            acc_ids.append(aid)
            s.execute(
                text(
                    "INSERT INTO accounts (id, code, name, account_type, normal_balance,"
                    " currency, parent_id, path, is_placeholder, is_active, version_id)"
                    " VALUES (:id, :code, :name, :typ, :norm, 'IRR', NULL, :code, 0, 1, 1)"
                ),
                {"id": aid, "code": code, "name": name, "typ": typ, "norm": norm},
            )

    print(f"seeding {n_entries} entries ({n_entries * 2} splits) …")
    t0 = time.perf_counter()
    batch = 500  # short write transactions (single-writer discipline)
    for chunk_start in range(0, n_entries, batch):
        with db.write_session() as s:
            for i in range(chunk_start, min(chunk_start + batch, n_entries)):
                eid = uuid7()
                day = (i % 28) + 1
                month = (i % 12) + 1
                s.execute(
                    text(
                        "INSERT INTO journal_entries (id, entry_number, transaction_date,"
                        " posted_at, payee, description, status, reversed_entry_id,"
                        " metadata_json, version_id, created_at, updated_at)"
                        " VALUES (:id, :num, :d, :d || 'T00:00:00', 'bench payee', :desc,"
                        " 'POSTED', NULL, '{}', 1, :d || 'T00:00:00', :d || 'T00:00:00')"
                    ),
                    {
                        "id": eid,
                        "num": i + 1,
                        "d": f"2025-{month:02d}-{day:02d}",
                        "desc": BENCH_DESCRIPTION.format(i=i),
                    },
                )
                s.execute(
                    text(
                        "INSERT INTO transaction_splits (id, journal_entry_id, account_id,"
                        " memo, debit, credit, currency, exchange_rate, functional_debit,"
                        " functional_credit, reconciliation_status)"
                        " VALUES (:s1, :e, :a1, NULL, 10000, 0, 'IRR', 100000000, 10000, 0,"
                        " 'UNRECONCILED')"
                    ),
                    {"s1": uuid7(), "e": eid, "a1": acc_ids[0]},
                )
                s.execute(
                    text(
                        "INSERT INTO transaction_splits (id, journal_entry_id, account_id,"
                        " memo, debit, credit, currency, exchange_rate, functional_debit,"
                        " functional_credit, reconciliation_status)"
                        " VALUES (:s2, :e, :a2, NULL, 0, 10000, 'IRR', 100000000, 0, 10000,"
                        " 'UNRECONCILED')"
                    ),
                    {"s2": uuid7(), "e": eid, "a2": acc_ids[1]},
                )
    seed_s = time.perf_counter() - t0
    print(f"seeded in {seed_s:.1f}s")

    def keyset_page():
        with db.session() as s:
            s.execute(
                text(
                    "SELECT id, transaction_date FROM journal_entries"
                    " ORDER BY transaction_date DESC, id DESC LIMIT 51"
                )
            ).fetchall()

    def offset_page():
        with db.session() as s:
            s.execute(
                text(
                    "SELECT id, transaction_date FROM journal_entries"
                    " ORDER BY transaction_date DESC, id DESC LIMIT 50 OFFSET 10000"
                )
            ).fetchall()

    def rollup():
        with db.session() as s:
            s.execute(text("SELECT * FROM v_account_balances")).fetchall()

    def snapshots():
        with db.session() as s:
            s.execute(
                text(
                    "SELECT s.account_id, SUM(s.debit), SUM(s.credit)"
                    " FROM transaction_splits s"
                    " JOIN journal_entries je ON je.id = s.journal_entry_id"
                    " WHERE je.status='POSTED' AND je.transaction_date <= '2025-12-31'"
                    " GROUP BY s.account_id"
                )
            ).fetchall()

    def like_search():
        with db.session() as s:
            s.execute(
                text(
                    "SELECT id FROM journal_entries WHERE description LIKE '%4242%' LIMIT 20"
                )
            ).fetchall()

    def fts_search():
        with db.session() as s:
            s.execute(
                text(
                    "SELECT ref_id FROM search_fts WHERE search_fts MATCH '4242' LIMIT 20"
                )
            ).fetchall()

    cases = [
        ("keyset page (50 rows)", keyset_page),
        ("OFFSET page @10k (50 rows)", offset_page),
        ("rollup view scan", rollup),
        ("snapshot aggregation", snapshots),
        ("LIKE search", like_search),
        ("FTS5 search", fts_search),
    ]
    print(f"\n{'query':32} {'median ms':>10}")
    print("-" * 44)
    for name, fn in cases:
        print(f"{name:32} {_time(fn):10.2f}")

    print(f"\ndatabase: {db_path} ({db_path.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
