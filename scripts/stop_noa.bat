@echo off
REM NOA Accounting — stop the running backend (and optional Vite dev server).
setlocal
echo [NOA] Stopping NOA processes...
taskkill /FI "WINDOWTITLE eq NOA*" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8787 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
echo [NOA] Stopped.
endlocal
