@echo off
REM VIRA Accounting — start backend (and serve built SPA when present).
REM Binds to 127.0.0.1 by default. Set VIRA_BIND_HOST/PORT to change.
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
  echo [VIRA] Virtual environment missing. Run scripts\setup_windows.ps1 first.
  exit /b 1
)

if not defined SQLITE_DATABASE_PATH set "SQLITE_DATABASE_PATH=%LOCALAPPDATA%\VIRA\data\vira.sqlite3"
if not defined SESSION_SECRET set "SESSION_SECRET=change-me-in-windows-credential-manager"

echo [VIRA] Starting backend on http://127.0.0.1:8787 (DB: %SQLITE_DATABASE_PATH%)
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787
endlocal
