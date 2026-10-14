"""Search API — journal entries + accounts (FTS5, LIKE fallback, RapidFuzz)."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..services.search import has_fts, search
from .deps import get_db

router = APIRouter(prefix="/api/v1/search", tags=["search"])


class SearchHitOut(BaseModel):
    entity: str
    ref_id: str
    title: str
    snippet: str
    score: float


class SearchResponse(BaseModel):
    query: str
    backend: str
    hits: list[SearchHitOut]


@router.get("", response_model=SearchResponse)
def run_search(
    session: Annotated[Session, Depends(get_db)],
    q: Annotated[str, Query(min_length=1, max_length=200)],
    entity: Annotated[Literal["entry", "account", "all"], Query()] = "all",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    like: Annotated[bool, Query()] = False,
) -> SearchResponse:
    use_like = like or not has_fts(session)
    hits = search(session, q, entity=entity, limit=limit, force_like=use_like)
    return SearchResponse(
        query=q,
        backend="like" if use_like else "fts5",
        hits=[
            SearchHitOut(
                entity=h.entity,
                ref_id=h.ref_id,
                title=h.title,
                snippet=h.snippet,
                score=h.score,
            )
            for h in hits
        ],
    )
