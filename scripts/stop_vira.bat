@echo off
REM VIRA Accounting — stop the running backend (and optional Vite dev server).
setlocal
echo [VIRA] Stopping VIRA processes...
taskkill /FI "WINDOWTITLE eq VIRA*" /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :8787 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do taskkill /PID %%p /F >nul 2>&1
echo [VIRA] Stopped.
endlocal
