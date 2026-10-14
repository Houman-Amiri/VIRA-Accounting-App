"""Register search — FTS5 when available, LIKE fallback, RapidFuzz ranking.

Phase 4 §8: no ``pg_trgm``/GIN/external search server.  ``search_fts`` is kept
in sync by SQLite triggers (migration 0002); when the SQLite build lacks FTS5
the table is absent and every query uses parameterized ``LIKE`` instead.
RapidFuzz re-ranks candidate rows so typo-tolerant matches still surface.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..models import Account, JournalEntry

Entity = Literal["entry", "account", "all"]

_FTS_SAFE = re.compile(r'[^\w\u0600-\u06FF]+', re.UNICODE)


@dataclass
class SearchHit:
    entity: str
    ref_id: str
    title: str
    snippet: str
    score: float


def _sanitize(query: str) -> str:
    """Turn free text into a safe FTS5 MATCH expression (prefix tokens)."""
    tokens = [t for t in _FTS_SAFE.split(query.strip()) if t]
    if not tokens:
        return ""
    return " ".join(f'"{t}"*' for t in tokens)


def has_fts(session: Session) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name='search_fts'")
    ).first()
    return row is not None


def _fts_search(session: Session, query: str, entity: Entity, limit: int) -> list[SearchHit]:
    expr = _sanitize(query)
    if not expr:
        return []
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
            score=fuzz.partial_ratio(query.lower(), f"{r[2]} {r[3]}".lower()),
        )
        for r in rows
    ]
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]


def _like_search(session: Session, query: str, entity: Entity, limit: int) -> list[SearchHit]:
    pattern = f"%{query.strip()}%"
    hits: list[SearchHit] = []
    if entity in ("entry", "all"):
        entry_rows = session.execute(
            select(JournalEntry)
            .where(
                JournalEntry.description.like(pattern)
                | JournalEntry.payee.like(pattern)
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
                    score=fuzz.partial_ratio(
                        query.lower(), f"{je.description} {je.payee or ''}".lower()
                    ),
                )
            )
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
                    score=fuzz.partial_ratio(query.lower(), f"{acc.name} {acc.code}".lower()),
                )
            )
    hits.sort(key=lambda h: -h.score)
    return hits[:limit]


def search(
    session: Session,
    query: str,
    *,
    entity: Entity = "all",
    limit: int = 20,
    force_like: bool = False,
) -> list[SearchHit]:
    """Search journal entries + accounts.  FTS5 path unless unavailable/forced."""
    if not query.strip():
        return []
    if not force_like and has_fts(session):
        return _fts_search(session, query, entity, limit)
    return _like_search(session, query, entity, limit)


__all__ = ["SearchHit", "search", "has_fts"]
