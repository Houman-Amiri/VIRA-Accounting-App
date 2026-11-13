"""Idempotent seed data — chart of accounts, currencies, opening equity, owner user.

Safe to run more than once: existing rows (matched by code/username) are kept.
Covers a small-business 3D-printing chart of accounts in the Iranian context
(Toman display / IRR storage) plus the required opening-balance equity account.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import utc_now_iso, uuid7
from .models import Account, Currency, User
from .schemas.ledger import NORMAL_BY_TYPE
from .security.passwords import hash_password, verify_password

log = logging.getLogger(__name__)

#: (code, name, type, is_placeholder) — small-business (3D-printing) chart.
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
    ("3900", "تراز افتتاحی", "EQUITY", False),
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

#: (code, name, type, is_placeholder) — personal-finance chart.
PERSONAL_CHART: list[tuple[str, str, str, bool]] = [
    ("1000", "دارایی‌ها", "ASSET", True),
    ("1010", "صندوق و کیف پول", "ASSET", False),
    ("1020", "بانک و کارت", "ASSET", False),
    ("1030", "پس‌انداز", "ASSET", False),
    ("2000", "بدهی‌ها", "LIABILITY", True),
    ("2010", "بدهی به دیگران", "LIABILITY", False),
    ("2020", "کارت اعتباری", "LIABILITY", False),
    ("3000", "سرمایه شخصی", "EQUITY", True),
    ("3010", "سرمایه اولیه", "EQUITY", False),
    ("3900", "تراز افتتاحی", "EQUITY", False),
    ("4000", "درآمدها", "INCOME", True),
    ("4010", "حقوق و درآمد", "INCOME", False),
    ("4020", "درآمد جانبی", "INCOME", False),
    ("5000", "هزینه‌ها", "EXPENSE", True),
    ("5010", "خوراک و سوپرمارکت", "EXPENSE", False),
    ("5020", "حمل‌ونقل", "EXPENSE", False),
    ("5030", "مسکن و اجاره", "EXPENSE", False),
    ("5040", "قبض‌ها", "EXPENSE", False),
    ("5050", "درمان", "EXPENSE", False),
    ("5060", "آموزش", "EXPENSE", False),
    ("5070", "تفریح", "EXPENSE", False),
]

#: Supported currencies (Phase 4 §10).  IRR is the base/storage unit; the UI
#: displays Toman (1 Toman = 10 Rials, applied exactly once at presentation).
SUPPORTED_CURRENCIES: list[tuple[str, str, bool]] = [
    ("IRR", "ریال ایران (نمایش: تومان)", True),
    ("USD", "دلار آمریکا", False),
    ("EUR", "یورو", False),
    ("AED", "درهم امارات", False),
    ("TRY", "لیر ترکیه", False),
    ("GBP", "پوند انگلیس", False),
]

CHARTS = {"business": CHART, "personal": PERSONAL_CHART}


def seed_chart_of_accounts(
    session: Session, *, currency: str = "IRR", chart: str = "business"
) -> int:
    created = 0
    entries = CHARTS[chart]
    for code, name, acc_type, placeholder in entries:
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
        log.warning("created user %s with generated password (set NOA_OWNER_PASSWORD)", username)
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


def ensure_owner_user(
    session: Session,
    *,
    username: str = "owner",
    password: str | None = None,
    rotate: bool = False,
) -> dict[str, Any]:
    """Make sure the owner can sign in, and optionally pin the password.

    Two states used to be unrecoverable from the app itself:

    * the database exists but has **no** user row (an interrupted first launch,
      or a database copied from a pre-rename install whose seeding never ran) —
      every password is refused and nothing in the UI can create an account;
    * the owner forgot the password that was generated on the first run.

    ``rotate=True`` writes ``password`` over the stored hash, so the launcher can
    apply a password the owner pinned in a local file on every start. Passing no
    password only repairs a missing account.
    """
    existing = session.scalar(select(User).where(User.username == username))
    if existing is None:
        seed_owner_user(session, username=username, password=password)
        return {
            "created": True,
            "rotated": False,
            "username": username,
            "generated": password is None,
        }
    if existing.role != "OWNER":
        existing.role = "OWNER"
    if existing.is_active != 1:
        existing.is_active = 1
    rotated = False
    if password and rotate and not verify_password(password, existing.password_hash):
        existing.password_hash = hash_password(password)
        rotated = True
        log.warning("owner password re-applied from the pinned credential file")
    session.flush()
    return {
        "created": False,
        "rotated": rotated,
        "username": existing.username,
        "generated": False,
    }


def seed_currencies(session: Session) -> int:
    created = 0
    for code, name, is_base in SUPPORTED_CURRENCIES:
        existing = session.get(Currency, code)
        if existing is not None:
            continue
        session.add(
            Currency(code=code, name=name, is_base=1 if is_base else 0, is_active=1)
        )
        created += 1
    session.flush()
    return created


def seed_all(
    session: Session,
    *,
    currency: str = "IRR",
    chart: str = "business",
    admin_username: str = "owner",
    admin_password: str | None = None,
    pin_owner_password: bool = False,
) -> dict[str, int]:
    from sqlalchemy import func

    currencies = seed_currencies(session)
    accounts = seed_chart_of_accounts(session, currency=currency, chart=chart)
    users_before = session.scalar(select(func.count()).select_from(User)) or 0
    # No password at all → still create the account (a database without a user
    # is a locked door nobody can open from the UI).
    outcome = ensure_owner_user(
        session,
        username=admin_username,
        password=admin_password,
        rotate=pin_owner_password,
    )
    users_after = session.scalar(select(func.count()).select_from(User)) or 0
    return {
        "currencies_created": currencies,
        "accounts_created": accounts,
        "users_created": int(users_after - users_before),
        "owner_created": int(bool(outcome["created"])),
        "owner_password_rotated": int(bool(outcome["rotated"])),
    }


def main() -> None:
    """CLI: `python -m app.seed` (idempotent, run on every start).

    Environment:

    * ``NOA_OWNER_PASSWORD`` — the password the owner pinned in
      ``%LOCALAPPDATA%\\NOA\\owner-password.txt``; **applied on every start**, so
      a forgotten password is replaced by the pinned one instead of locking the
      owner out.
    * ``NOA_ADMIN_PASSWORD`` — legacy: used only when the owner is created.
    * ``NOA_CHART`` selects the chart (`business` default, or `personal`).
    """
    import json as _json
    import os

    from .config import Settings
    from .db import Database

    settings = Settings()
    db = Database(settings)
    pinned = read_pinned_password(settings)
    if pinned is None:
        # Notepad may save the pinned file as UTF-8 with a BOM and with a
        # trailing newline; neither belongs to the password.
        pinned = (os.environ.get("NOA_OWNER_PASSWORD") or "").strip() or None
    if pinned is not None and len(pinned) < 8:
        raise SystemExit(
            "owner-password.txt: the password must be at least 8 characters "
            "(رمز فایل owner-password.txt باید حداقل ۸ نویسه باشد)"
        )
    initial = pinned or (os.environ.get("NOA_ADMIN_PASSWORD") or None)
    generated: str | None = None
    if initial is None:
        import secrets

        generated = secrets.token_urlsafe(12)
        initial = generated
    chart = os.environ.get("NOA_CHART", "business")
    if chart not in CHARTS:
        raise SystemExit(f"NOA_CHART must be one of {sorted(CHARTS)}, got {chart!r}")
    with db.write_session() as session:
        result = seed_all(
            session,
            currency=settings.base_currency,
            chart=chart,
            admin_password=initial,
            pin_owner_password=pinned is not None,
        )
    if generated is not None and result.get("owner_created"):
        target = write_pinned_password(settings, generated)
        print(
            f"[NOA] First login: username=owner password={generated}\n"
            f"[NOA] The password is saved in {target} — edit that file to change it."
        )
    print(_json.dumps(result))



# ----------------------------------------------------------- pinned password ---
# The login password lives in a file the owner can open with Notepad:
#     %LOCALAPPDATA%\NOA\owner-password.txt
# Whatever it holds is applied on every start (see apply_pinned_owner_password),
# which is what makes a forgotten password recoverable without a terminal — and
# what the owner asked for: one fixed password, always the same.
PINNED_PASSWORD_FILENAME = "owner-password.txt"


def pinned_password_path(settings: Any) -> Path:
    data_dir = getattr(settings, "data_dir", None)
    if data_dir is None:
        raise ValueError("settings.data_dir is required to locate the pinned password")
    return Path(data_dir) / PINNED_PASSWORD_FILENAME


def read_pinned_password(settings: Any) -> str | None:
    """The pinned password, or ``None``. Notepad may add a BOM/blank lines."""
    import os

    path = pinned_password_path(settings)
    if path.is_file():
        try:
            text = path.read_text(encoding="utf-8-sig").strip()
        except OSError:
            text = ""
        if text:
            return text
    env = (os.environ.get("NOA_OWNER_PASSWORD") or "").strip()
    return env or None


def write_pinned_password(settings: Any, password: str) -> Path:
    """Persist the password where the owner can read and edit it."""
    path = pinned_password_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password + "\n", encoding="utf-8")
    return path


def apply_pinned_owner_password(settings: Any, database: Any = None) -> dict[str, Any]:
    """Make the owner account usable at application startup.

    * no owner row  → create one; the password is the pinned one, else a fresh
      random one that is written to the pinned file and logged once;
    * pinned file   → whatever it holds becomes the password (the recovery
      path the owner asked for);
    * pinned file absent, owner present → the stored password is left alone, so
      an upgrade never silently changes somebody's working password.
    """
    import secrets

    pinned = read_pinned_password(settings)
    owned = database is None
    if database is None:
        from .db import Database

        database = Database(settings)
    try:
        with database.write_session() as session:
            existing = session.scalar(select(User).where(User.username == "owner"))
            if existing is None:
                password = pinned or secrets.token_urlsafe(12)
                outcome = ensure_owner_user(session, password=password, rotate=True)
                if pinned is None:
                    write_pinned_password(settings, password)
                log.warning(
                    "no owner account existed; created one — the password is in %s",
                    pinned_password_path(settings),
                )
                outcome["password_written"] = pinned is None
                return outcome
            if pinned is None:
                return {"created": False, "rotated": False, "username": existing.username}
            outcome = ensure_owner_user(session, password=pinned, rotate=True)
            return outcome
    finally:
        if owned:
            database.dispose()


if __name__ == "__main__":
    main()
