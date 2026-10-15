@echo off
REM =====================================================================
REM  V.I.R.A — installed launcher (Phase 8 / fix v1.0.3)
REM  Starts FastAPI (serving the built SPA) and opens the default browser
REM  at http://127.0.0.1:<port>. Spec: "A Start menu/launcher shortcut runs
REM  start_vira, which starts FastAPI and opens the app in the default
REM  browser at http://127.0.0.1:<port>."
REM
REM  Works from an installed payload ({app}) AND a dev checkout:
REM    1. {app}\python\python.exe   — bundled CPython (installed app)
REM    2. .venv\Scripts\python.exe  — dev checkout
REM    3. python / py -3 on PATH    — fallback
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title V.I.R.A

REM ------------------------------------------------- interpreter ----
set "VIRA_PY=%~dp0python\python.exe"
if not exist "%VIRA_PY%" if exist "%~dp0.venv\Scripts\python.exe" set "VIRA_PY=%~dp0.venv\Scripts\python.exe"
if not exist "%VIRA_PY%" (
  where python >nul 2>nul && set "VIRA_PY=python"
)
if not exist "%VIRA_PY%" (
  where py >nul 2>nul && set "VIRA_PY=py -3"
)
if not exist "%VIRA_PY%" (
  echo [VIRA] Python 3.11+ was not found. Reinstall V.I.R.A or install Python.
  pause
  exit /b 1
)

REM ------------------------------------------------- runtime env ----
if not defined SQLITE_DATABASE_PATH set "SQLITE_DATABASE_PATH=%LOCALAPPDATA%\VIRA\data\vira.sqlite3"
if not defined VIRA_PORT set "VIRA_PORT=8787"
set "PYTHONPATH=%~dp0site-packages;%~dp0"
if not exist "%LOCALAPPDATA%\VIRA\data" mkdir "%LOCALAPPDATA%\VIRA\data"
if not exist "%LOCALAPPDATA%\VIRA\logs" mkdir "%LOCALAPPDATA%\VIRA\logs"
for %%D in ("%SQLITE_DATABASE_PATH%") do if not exist "%%~dpD" mkdir "%%~dpD"

REM session secret: generate once, persist beside the data (never in the DB)
if not defined SESSION_SECRET (
  if exist "%LOCALAPPDATA%\VIRA\session.secret" (
    set /p SESSION_SECRET=<"%LOCALAPPDATA%\VIRA\session.secret"
  ) else (
    for /f "delims=" %%S in ('"%VIRA_PY%" -c "import secrets;print(secrets.token_urlsafe(48))"') do set "SESSION_SECRET=%%S"
    >"%LOCALAPPDATA%\VIRA\session.secret" echo %SESSION_SECRET%
  )
)

REM -------------------------------------- first run: owner account ----
set "VIRA_FIRST_RUN="
if not exist "%SQLITE_DATABASE_PATH%" (
  set "VIRA_FIRST_RUN=1"
  for /f "delims=" %%P in ('"%VIRA_PY%" -c "import secrets;print(secrets.token_urlsafe(12))"') do set "VIRA_ADMIN_PASSWORD=%%P"
)

REM ------------------------- safe migrations + seed (idempotent) ----
echo [VIRA] Applying database migrations...
"%VIRA_PY%" "%~dp0scripts\migrate_vira.py" || goto :fail
if defined VIRA_FIRST_RUN (
  echo [VIRA] First run — seeding chart of accounts + owner user...
  "%VIRA_PY%" -m app.seed || goto :fail
  >"%LOCALAPPDATA%\VIRA\first-run-credentials.txt" (
    echo V.I.R.A — initial login. Keep this file safe, then change the password.
    echo.
    echo username: owner
    echo password: %VIRA_ADMIN_PASSWORD%
  )
  echo.
  echo ================================================================
  echo   First run — your initial login:
  echo       username: owner
  echo       password: %VIRA_ADMIN_PASSWORD%
  echo   (also saved in %LOCALAPPDATA%\VIRA\first-run-credentials.txt)
  echo ================================================================
  echo.
)

REM --------- browser opener (waits for health) + server in this console ----
echo [VIRA] Starting server on http://127.0.0.1:%VIRA_PORT% (logs below — Ctrl+C or close to stop)
start "" powershell -NoProfile -Command ^
  "$u='http://127.0.0.1:%VIRA_PORT%/';for($i=0;$i -lt 180;$i++){try{$r=Invoke-WebRequest -UseBasicParsing ($u+'api/v1/health/live') -TimeoutSec 2;if($r.StatusCode -eq 200){Start-Process $u;exit 0}}catch{};Start-Sleep -Milliseconds 500}"
"%VIRA_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port %VIRA_PORT%
if errorlevel 1 goto :fail
exit /b 0

:fail
echo.
echo [VIRA] Startup failed — see the messages above and %LOCALAPPDATA%\VIRA\logs\.
pause
exit /b 1
