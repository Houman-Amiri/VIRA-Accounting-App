"""Domain errors mapped to deterministic RFC 9457 problem codes."""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "domain_error"
    title = "Domain error"
    status = 400

    def __init__(self, detail: str, *, errors: list[dict[str, Any]] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.errors = errors or []


class UnbalancedJournalEntryError(DomainError):
    code = "unbalanced_journal_entry"
    title = "Unbalanced journal entry"
    status = 422


class InsufficientSplitsError(DomainError):
    code = "insufficient_splits"
    title = "Journal entry needs at least two split lines"
    status = 422


class PlaceholderAccountError(DomainError):
    code = "placeholder_account_posting"
    title = "Cannot post to a placeholder account"
    status = 422


class ClosedFiscalPeriodError(DomainError):
    code = "closed_fiscal_period"
    title = "Fiscal period is closed"
    status = 409


class EntryNotDraftError(DomainError):
    code = "entry_not_draft"
    title = "Journal entry is not editable in its current status"
    status = 409


class StaleVersionError(DomainError):
    code = "stale_version"
    title = "Concurrent modification detected"
    status = 409


class NotFoundError(DomainError):
    code = "not_found"
    title = "Resource not found"
    status = 404


class DuplicateBankImportError(DomainError):
    code = "duplicate_bank_import"
    title = "Bank statement line already imported"
    status = 409


class IdempotencyKeyReuseError(DomainError):
    code = "idempotency_key_reuse"
    title = "Idempotency key already used with a different request"
    status = 409


class IdempotencyConflictError(DomainError):
    code = "idempotency_conflict"
    title = "A request with this idempotency key is in flight"
    status = 409


class ReconciliationSessionClosedError(DomainError):
    code = "reconciliation_session_closed"
    title = "Reconciliation session is not open"
    status = 409


class MoneyOverflowError(DomainError):
    code = "money_overflow"
    title = "Monetary amount exceeds safe bounds"
    status = 422


class FileRejectedError(DomainError):
    code = "file_rejected"
    title = "Upload rejected"
    status = 415


class FileTooLarge(FileRejectedError):
    code = "file_too_large"
    title = "File too large"


class UnsupportedMediaType(FileRejectedError):
    code = "unsupported_media_type"
    title = "Unsupported media type"


class SudoRequiredError(DomainError):
    code = "sudo_required"
    title = "Sudo re-authentication required"
    status = 403
