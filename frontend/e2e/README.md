# Browser integration tests — disposable SQLite only

These tests use real authentication, CSRF and business APIs. The dashboard audit
creates **posted, immutable journal entries**, plus inventory, suppliers, orders
and production fixtures. It deliberately retains the financial audit trail in
the test database. **Never point this suite at an installed user's database or
at a production server.** Do not weaken the posting triggers to clean up tests.

Before starting servers, choose a NEW disposable `SQLITE_DATABASE_PATH` and
`DATA_DIR` (outside the repository). Migrate it and seed the test owner:

```sh
# Example for a POSIX development environment; use a NEW path per test run.
export DATA_DIR="$(mktemp -d)"
export SQLITE_DATABASE_PATH="$DATA_DIR/vira.sqlite3"
(cd backend && ../.venv/bin/alembic upgrade head)
VIRA_ADMIN_PASSWORD=e2e-owner-password .venv/bin/python -m app.seed
cd frontend
pnpm exec playwright install chromium
VIRA_E2E_DISPOSABLE_DATABASE=1 pnpm e2e
```

Run from the repository root initially. Make sure ports 8787/5173 are not already
serving another database: Playwright's development config reuses existing
servers. Both new servers inherit these environment variables. Set
`VIRA_E2E_USER`/`VIRA_E2E_PASSWORD` only for a dedicated test account.
`VIRA_E2E_DISPOSABLE_DATABASE=1` is an explicit acknowledgement, NOT automatic
proof that the server is disposable. CI uses `${{ runner.temp }}/vira-e2e.sqlite3`.

The dashboard audit shares the existing shell login so the real auth rate limit
is preserved. It compares six KPIs against real report APIs, renders four SVG
plots in both themes, tests container resizing and navigation, and injects only
a temporary 503 for the inventory-summary HTTP request to test error/recovery.
Normal report/operations responses are **not** mocked in this audit. The separate
update journey still mocks update download/status (not installation proof).

Screenshots are test artifacts in `frontend/test-results/`; keep these and local
sandbox browser configs out of commits. Native Windows popup acceptance and a
real in-app delta installation are separate checks, not proven by Linux E2E.

The journal journey also runs the Phase 7 operations audit, using the same real
login (no extra auth attempts): define filament and two products, receive stock,
create a two-line order with four-decimal Persian prices, create linked jobs,
reject insufficient stock without side effects, replenish, finish both jobs,
verify exact consumption/receipts and per-line readiness, reject duplicate
completion, then request the actual proforma link. The PDF signature is checked
when a native renderer is present; otherwise the printable HTML's customer and
exact total are checked. HTML fallback is not claimed as a native PDF proof.
