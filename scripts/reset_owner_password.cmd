@echo off
REM =====================================================================
REM  NOA - set a new password for an existing user (offline, app closed)
REM  Double-click this file. It uses the Python bundled with the install,
REM  next to reset_owner_password.py, and leaves a backup of the database.
REM =====================================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0.."
title NOA - change password

set "NOA_PY=%~dp0..\python\python.exe"
if not exist "%NOA_PY%" if exist "%~dp0..\.venv\Scripts\python.exe" set "NOA_PY=%~dp0..\.venv\Scripts\python.exe"
if not exist "%NOA_PY%" where python >nul 2>nul && set "NOA_PY=python"
if not exist "%NOA_PY%" (
  echo [NOA] Python 3.11+ was not found. Run this file from the NOA install folder.
  pause
  exit /b 1
)

set "PYTHONPATH=%~dp0..\site-packages;%~dp0.."
"%NOA_PY%" "%~dp0reset_owner_password.py" %*
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo [NOA] The password was NOT changed. See the message above.
pause
exit /b %RC%
