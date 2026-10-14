# VIRA-Accounting-App

**V.I.R.A** — Persian-only (fa-IR, RTL) accounting & operations app for a small 3D-printing business: warehouse (filaments & produced models), customer orders, production, pricing engine, live landing page, and a fully dynamic dashboard — on a strict double-entry ledger with **SQLite** and **FastAPI + React/TypeScript**. Windows-native (no Docker), installed with **Inno Setup**, updated in-app from GitHub releases (delta updates).

## Documentation

| File | Purpose |
|---|---|
| [`project brief.md`](project%20brief.md) | Consistent-context brief: selected stack + non-negotiable constraints + status |
| [`MASTER_PROMPT.md`](MASTER_PROMPT.md) | Compiled master prompt (all requirements, phases 1–8) |
| [`VIRA_SQLite_No_Docker.md`](VIRA_SQLite_No_Docker.md) | Original request document |
| [`docs/product-spec.md`](docs/product-spec.md) | Phase 1 product specification (modules, landing page, dashboard, pricing model) |
| [`docs/data-model.md`](docs/data-model.md) | Phase 1 core entities, fields, relationships |
| `قیمت نهایی.xlsx` | Source workbook for the Sales Price Calculations page |

## Development quickstart (no Docker)

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export SQLITE_DATABASE_PATH=/path/outside/repo/vira.sqlite3   # default: platform data dir
cd backend && ../.venv/bin/python -m alembic upgrade head
../.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

API docs: `http://127.0.0.1:8787/api/docs` · Health: `/api/v1/health/ready`.
Tests: `python -m pytest` · Lint/types: `ruff check backend/` · `mypy backend/app`.
Windows: `scripts/setup_windows.ps1`, `scripts/start_vira.bat`, `scripts/stop_vira.bat`, `scripts/backup_vira.ps1`.

## Status

Phase 1 (planning) and Phase 2 (back-end core: double-entry ledger, SQLite/STRICT + Alembic, FastAPI, bank imports, reports, FX, receipts/PDF/OCR, scheduling, auth, backups) complete. Phase 3 (React SPA) starts on the user's "proceed".
