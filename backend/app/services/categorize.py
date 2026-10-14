"""Smart categorization & auto-matching for imported bank lines.

RapidFuzz string similarity over historical payees plus a lightweight local
scikit-learn classifier (MultinomialNB over character n-grams) suggest target
Expense/Income accounts and reconciliation matches.  Falls back to a pure
RapidFuzz frequency model when scikit-learn is unavailable.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from rapidfuzz import fuzz, process
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Account, BankStatementLine, JournalEntry, TransactionSplit

_TOKEN = re.compile(r"[\w\u0600-\u06FF]{2,}", re.UNICODE)


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN.findall(text or "")]


class Categorizer:
    """Trains on existing posted splits (payee/description → account)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self._history: dict[str, Counter[str]] = defaultdict(Counter)
        self._payees: list[str] = []
        self._labels: list[str] = []
        self._sklearn_model: tuple[Any, Any] | None = None
        self._load_history()
        self._train()

    def _load_history(self) -> None:
        rows = self.session.execute(
            select(JournalEntry.payee, JournalEntry.description, TransactionSplit.account_id)
            .join(TransactionSplit, TransactionSplit.journal_entry_id == JournalEntry.id)
            .where(JournalEntry.status == "POSTED")
        ).fetchall()
        for payee, description, account_id in rows:
            text = f"{payee or ''} {description or ''}".strip()
            if not text:
                continue
            self._history[text][account_id] += 1
            self._payees.append(text)
            self._labels.append(account_id)

    def _train(self) -> None:
        if not self._payees:
            return
        try:
            from sklearn.feature_extraction.text import HashingVectorizer
            from sklearn.naive_bayes import MultinomialNB

            vec = HashingVectorizer(analyzer="char_wb", n_features=2**12, alternate_sign=False)
            X = vec.fit_transform(self._payees)
            clf = MultinomialNB()
            clf.fit(X, self._labels)
            self._sklearn_model = (vec, clf)
        except Exception:
            self._sklearn_model = None  # RapidFuzz-only fallback

    def suggest_account(self, text: str) -> tuple[str | None, float]:
        """Return (account_id, confidence 0..1) for a bank line description."""
        text = (text or "").strip()
        if not text or not self._payees:
            return None, 0.0
        if self._sklearn_model is not None:
            vec, clf = self._sklearn_model  # type: ignore[misc]
            proba = clf.predict_proba(vec.transform([text]))[0]
            best = int(proba.argmax())
            return self._labels[best], float(proba[best])
        match = process.extractOne(
            text, self._payees, scorer=fuzz.token_set_ratio, score_cutoff=60
        )
        if match is None:
            return None, 0.0
        matched_text, score = match[0], match[1]
        top = self._history[matched_text].most_common(1)[0][0]
        return top, score / 100.0

    def suggest_matches(
        self, line: BankStatementLine, candidates: list[JournalEntry], *, limit: int = 5
    ) -> list[tuple[str, float]]:
        """Rank candidate journal entries for a reconciliation match."""
        line_text = f"{line.payee_raw or ''} {line.description_raw or ''}".strip()
        scored: list[tuple[str, float]] = []
        for entry in candidates:
            entry_text = f"{entry.payee or ''} {entry.description or ''}".strip()
            score = fuzz.token_set_ratio(line_text, entry_text) / 100.0
            scored.append((entry.id, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:limit]

    def categorize_line(self, line: BankStatementLine) -> None:
        text = f"{line.payee_raw or ''} {line.description_raw or ''}".strip()
        account_id, confidence = self.suggest_account(text)
        if account_id and confidence >= 0.5:
            account = self.session.get(Account, account_id)
            line.category_suggestion = account.code if account else None
            line.status = "SUGGESTED"
