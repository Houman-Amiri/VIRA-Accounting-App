"""Idempotent seed data — chart of accounts, currencies, opening equity, owner user.

Safe to run more than once: existing rows (matched by code/username) are kept.
Covers a small-business 3D-printing chart of accounts in the Iranian context
(Toman display / IRR storage) plus the required opening-balance equity account.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import utc_now_iso, uuid7
from .models import Account, User
from .schemas.ledger import NORMAL_BY_TYPE
from .security.passwords import hash_password

log = logging.getLogger(__name__)

#: (code, name, type, is_placeholder)
CHART: list[tuple[str, str, str, bool]] = [
    ("1000", "دارایی‌ها", "ASSET", True),
    ("1010", "صندوق", "ASSET", False),
    ("1020", "بانک", "ASSET", False),
    ("1030", "موجودی مواد و کالا", "ASSET", False),
    ("1040", "حساب‌های دریافتنی", "ASSET", False),
    ("2000", "بدهی‌ها", "LIABILITY", True),
    ("2010", "حساب‌های پرداختنی", "LIABILITY", False),
    ("3000", "سرمایه و حقوق مالکانه", "EQUITY", True),
    ("3010", "سرمایه اولیه", "EQUITY", False),
    ("3020", "سود (زیان) انباشته", "EQUITY", False),
    ("4000", "درآمدها", "INCOME", True),
    ("4010", "درآمد فروش محصولات", "INCOME", False),
    ("5000", "هزینه‌ها", "EXPENSE", True),
    ("5010", "بهای تمام شده کالای فروش رفته", "EXPENSE", False),
    ("5020", "مواد مصرفی", "EXPENSE", False),
    ("5030", "حقوق و دستمزد", "EXPENSE", False),
    ("5040", "اجاره", "EXPENSE", False),
    ("5050", "برق و انرژی", "EXPENSE", False),
    ("5060", "استهلاک تجهیزات", "EXPENSE", False),
    ("5070", "کارمزد بازارگاه (دیجی‌کالا)", "EXPENSE", False),
    ("5080", "بسته‌بندی و ارسال", "EXPENSE", False),
]


def seed_chart_of_accounts(session: Session, *, currency: str = "IRR") -> int:
    created = 0
    for code, name, acc_type, placeholder in CHART:
        existing = session.scalar(select(Account).where(Account.code == code))
        if existing is not None:
            continue
        parent_id = None
        path = code
        if "." in code:
            parent_code = code.split(".")[0]
            parent = session.scalar(select(Account).where(Account.code == parent_code))
            parent_id = parent.id if parent else None
            path = f"{parent.path}.{code}" if parent else code
        session.add(
            Account(
                id=uuid7(),
                code=code,
                name=name,
                account_type=acc_type,
                normal_balance=NORMAL_BY_TYPE[acc_type],
                currency=currency,
                parent_id=parent_id,
                path=path,
                is_placeholder=1 if placeholder else 0,
                is_active=1,
                version_id=1,
            )
        )
        created += 1
    session.flush()
    return created


def seed_owner_user(session: Session, *, username: str = "owner", password: str | None = None) -> User | None:
    existing = session.scalar(select(User).where(User.username == username))
    if existing is not None:
        return existing
    if password is None:
        import secrets

        password = secrets.token_urlsafe(12)
        log.warning("created user %s with generated password (set VIRA_ADMIN_PASSWORD)", username)
    user = User(
        id=uuid7(),
        username=username,
        password_hash=hash_password(password),
        role="OWNER",
        is_active=1,
        created_at=utc_now_iso(),
    )
    session.add(user)
    session.flush()
    return user


def seed_all(
    session: Session,
    *,
    currency: str = "IRR",
    admin_username: str = "owner",
    admin_password: str | None = None,
) -> dict[str, int]:
    accounts = seed_chart_of_accounts(session, currency=currency)
    user = seed_owner_user(session, username=admin_username, password=admin_password)
    return {"accounts_created": accounts, "users_created": 1 if user else 0}
