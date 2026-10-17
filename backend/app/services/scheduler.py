"""Background job scheduler (APScheduler) for recurring journal entries.

Recurring templates (rent, subscriptions, depreciation, payroll) are stored in
``recurring_entries`` with a 5-field cron expression; the scheduler posts the
templated journal entry and records ``last_entry_id``.  The scheduler runs
in-process; jobs are executed via :meth:`run_due_jobs` (also used by tests and
by the APScheduler callback).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ids import utc_now_iso, uuid7
from ..models import RecurringEntry
from ..schemas.ledger import JournalEntryCreate, SplitCreate
from ..services.ledger import LedgerService

log = logging.getLogger(__name__)


def parse_cron(expr: str) -> CronTrigger:
    parts = expr.split()
    if len(parts) != 5:
        raise ValueError(f"cron expression must have 5 fields: {expr!r}")
    return CronTrigger(
        minute=parts[0], hour=parts[1], day=parts[2], month=parts[3], day_of_week=parts[4]
    )


def next_run_after(expr: str, after: datetime | None = None) -> str:
    trigger = parse_cron(expr)
    nxt = trigger.get_next_fire_time(None, after or datetime.now(UTC))
    return (nxt or (after or datetime.now(UTC))).isoformat()


class RecurringEntryService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, name: str, cron_expr: str, template: dict) -> RecurringEntry:
        parse_cron(cron_expr)  # validate
        data = JournalEntryCreate.model_validate(
            {
                **template,
                "transaction_date": template.get("transaction_date") or "2000-01-01",
                "splits": template["splits"],
            }
        )
        row = RecurringEntry(
            id=uuid7(),
            name=name,
            cron_expr=cron_expr,
            template_json=json.dumps(template, ensure_ascii=False),
            next_run_at=next_run_after(cron_expr),
            is_active=1,
        )
        _ = data  # template validated up-front
        self.session.add(row)
        self.session.flush()
        return row

    def run_due_jobs(self, *, now: datetime | None = None) -> list[str]:
        """Post journal entries for every due recurring template. Idempotent per run time."""
        now = now or datetime.now(UTC)
        now_iso = now.isoformat()
        executed: list[str] = []
        rows = list(
            self.session.scalars(
                select(RecurringEntry).where(
                    RecurringEntry.is_active == 1,
                    RecurringEntry.next_run_at.is_not(None),
                    RecurringEntry.next_run_at <= now_iso,
                )
            )
        )
        ledger = LedgerService(self.session)
        for row in rows:
            template = json.loads(row.template_json)
            payload = {
                **template,
                "transaction_date": template.get("transaction_date") or now.date().isoformat(),
            }
            create = JournalEntryCreate.model_validate(payload)
            entry = ledger.create_draft(create, post=True)
            row.last_run_at = utc_now_iso()
            row.last_entry_id = entry.id
            row.next_run_at = next_run_after(row.cron_expr, now)
            executed.append(entry.id)
        self.session.flush()
        return executed


class SchedulerManager:
    """Thin APScheduler wrapper (in-process)."""

    def __init__(
        self,
        session_factory: object,
        *,
        interval_seconds: int = 60,
        write_gate: Callable[[], bool] | None = None,
    ) -> None:
        self.session_factory = session_factory
        self.write_gate = write_gate
        self.scheduler = BackgroundScheduler(timezone="UTC")
        self.interval_seconds = interval_seconds

    def _tick(self) -> None:  # pragma: no cover - exercised via run_due_jobs
        if self.write_gate is not None and self.write_gate():
            return
        try:
            with self.session_factory() as session:  # type: ignore[operator]
                service = RecurringEntryService(session)
                executed = service.run_due_jobs()
                session.commit()
                if executed:
                    log.info("recurring entries posted: %s", executed)
        except Exception:
            log.exception("recurring entry tick failed")

    def start(self) -> None:
        self.scheduler.add_job(
            self._tick, "interval", seconds=self.interval_seconds, id="recurring_entries"
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)


def due_within(days: int = 1, *, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return (now + timedelta(days=days)).isoformat()


def template_preview(template: dict) -> list[SplitCreate]:
    return [SplitCreate.model_validate(s) for s in template.get("splits", [])]
