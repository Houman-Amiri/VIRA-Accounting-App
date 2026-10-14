"""Register search — FTS5 when available, LIKE fallback, RapidFuzz ranking.

Phase 7 §1: unified parameterized search across ``journal_entries.payee`` /
``description`` / ``entry_number``, ``transaction_splits.memo`` and
``accounts.code`` / ``accounts.name``.  Numeric query tokens are parsed with
``Decimal`` and compared against integer-scaled debit/credit values via the
shared ``money.to_scaled`` utility — never via float.  RapidFuzz re-ranks a
bounded candidate set.  No external search engine, ever.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from rapidfuzz import fuzz
from sqlalchemy import String, cast, select, text
from sqlalchemy.orm import Session

from ..models import Account, JournalEntry, TransactionSplit
from ..money import from_scaled, to_scaled

Entity = Literal["entry", "account", "all"]
_FTS_SAFE = re.compile(r"[\s,;]+")
_NUMERIC_TOKEN = re.compile(r"[-+]?\d[\d,]*(?:\.\d+)?")


@dataclass
class SearchHit:
    entity: str
    ref_id: str
    title: str
    snippet: str
    score: float


def _sanitize(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (prefix tokens).

    Numeric tokens stay in the expression so ``#123`` entry numbers match;
    they additionally drive exact scaled-amount matching in :func:`search`.
    """
    tokens = [t for t in _FTS_SAFE.split(query.strip()) if t]
    if not tokens:
        return ""
    return " ".join(f'"{t}"*' for t in tokens)


def has_fts(session: Session) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='search_fts'")
    ).first()
    return row is not None


def _numeric_scales(query: str) -> list[int]:
    """Parse numeric tokens with Decimal → integer-scaled amounts (Phase 7 §1)."""
    scales: list[int] = []
    for raw in _NUMERIC_TOKEN.findall(query):
        cleaned = raw.replace(",", "")
        try:
            value = Decimal(cleaned)
        except InvalidOperation:
            continue
        if value == 0 or abs(value) > Decimal("1000000000000"):
            continue
        try:
            scales.append(to_scaled(value))
        except Exception:  # noqa: BLE001 - out-of-range amounts are not searchable
            continue
    return scales


def _rank(query: str, hits: list[SearchHit], limit: int) -> list[SearchHit]:
    for h in hits:
        h.score = max(
            h.score,
            fuzz.partial_ratio(query.lower(), f"{h.title} {h.snippet}".lower()),
        )
    hits.sort(key=lambda h: -h.score)
    # bounded, de-duplicated by (entity, ref_id)
    seen: set[tuple[str, str]] = set()
    out: list[SearchHit] = []
    for h in hits:
        key = (h.entity, h.ref_id)
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
        if len(out) >= limit:
            break
    return out


def _split_memo_search(session: Session, query: str, limit: int) -> list[SearchHit]:
    """transaction_splits.memo LIKE pass — merged into both search paths."""
    pattern = f"%{query.strip()}%"
    rows = session.execute(
        select(TransactionSplit, JournalEntry)
        .join(JournalEntry, JournalEntry.id == TransactionSplit.journal_entry_id)
        .where(TransactionSplit.memo.like(pattern))
        .limit(limit)
    ).all()
    hits: list[SearchHit] = []
    for split, je in rows:
        hits.append(
            SearchHit(
                entity="entry",
                ref_id=je.id,
                title=je.description,
                snippet=f"{split.memo or ''} #{je.entry_number}"[:160],
                score=0.0,
            )
        )
    return hits


def _amount_search(session: Session, scales: list[int], limit: int) -> list[SearchHit]:
    """Exact debit/credit matches on integer-scaled amounts (Decimal-based)."""
    if not scales:
        return []
    hits: list[SearchHit] = []
    for scaled in scales[:3]:  # bounded
        rows = session.execute(
            select(TransactionSplit, JournalEntry)
            .join(JournalEntry, JournalEntry.id == TransactionSplit.journal_entry_id)
            .where(
                (TransactionSplit.debit == scaled) | (TransactionSplit.credit == scaled)
            )
            .limit(limit)
        ).all()
        for split, je in rows:
            hits.append(
                SearchHit(
                    entity="entry",
                    ref_id=je.id,
                    title=je.description,
                    snippet=f"مبلغ: {from_scaled(scaled):.4f} — {split.memo or ''}"[:160],
                    score=95.0,  # exact amount match ranks high
                )
            )
    return hits


def _fts_search(session: Session, query: str, entity: Entity, limit: int) -> list[SearchHit]:
    expr = _sanitize(query)
    hits: list[SearchHit] = []
    if expr:
        sql = (
            "SELECT entity, ref_id, title, body FROM search_fts "
            "WHERE search_fts MATCH :q"
        )
        params: dict[str, object] = {"q": expr}
        if entity != "all":
            sql += " AND entity = :entity"
            params["entity"] = entity
        rows = session.execute(text(sql), params).fetchall()
        hits = [
            SearchHit(
                entity=str(r[0]),
                ref_id=str(r[1]),
                title=str(r[2]),
                snippet=str(r[3])[:160],
                score=0.0,
            )
            for r in rows
        ]
    # FTS indexes entries+accounts only — merge memo + numeric passes (Phase 7 §1).
    if entity in ("entry", "all") and query.strip():
        hits.extend(_split_memo_search(session, query, limit))
        hits.extend(_amount_search(session, _numeric_scales(query), limit))
    return _rank(query, hits, limit)


def _like_search(session: Session, query: str, entity: Entity, limit: int) -> list[SearchHit]:
    pattern = f"%{query.strip()}%"
    hits: list[SearchHit] = []
    if entity in ("entry", "all"):
        entry_rows = session.execute(
            select(JournalEntry)
            .where(
                JournalEntry.description.like(pattern)
                | JournalEntry.payee.like(pattern)
                | cast(JournalEntry.entry_number, String).like(pattern)
            )
            .limit(limit)
        ).scalars()
        for je in entry_rows:
            hits.append(
                SearchHit(
                    entity="entry",
                    ref_id=je.id,
                    title=je.description,
                    snippet=f"{je.description} {je.payee or ''} #{je.entry_number}"[:160],
                    score=0.0,
                )
            )
        hits.extend(_split_memo_search(session, query, limit))
        hits.extend(_amount_search(session, _numeric_scales(query), limit))
    if entity in ("account", "all"):
        account_rows = session.execute(
            select(Account)
            .where(Account.name.like(pattern) | Account.code.like(pattern))
            .limit(limit)
        ).scalars()
        for acc in account_rows:
            hits.append(
                SearchHit(
                    entity="account",
                    ref_id=acc.id,
                    title=f"{acc.code} {acc.name}",
                    snippet=acc.name,
                    score=0.0,
                )
            )
    return _rank(query, hits, limit)


def search(
    session: Session,
    query: str,
    *,
    entity: Entity = "all",
    limit: int = 20,
    force_like: bool = False,
) -> list[SearchHit]:
    """Search journal entries (incl. memos/amounts) + accounts.

    FTS5 path unless unavailable/forced; both paths are parameterized and both
    merge numeric-amount and split-memo candidates (Phase 7 §1).
    """
    if not query.strip():
        return []
    if not force_like and has_fts(session):
        return _fts_search(session, query, entity, limit)
    return _like_search(session, query, entity, limit)


__all__ = ["SearchHit", "search", "has_fts"]
