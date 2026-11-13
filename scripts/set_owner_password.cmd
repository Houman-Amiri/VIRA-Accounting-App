@echo off
REM =====================================================================
REM  NOA - set the login password (no typing of paths, no terminal)
REM
REM  1. Close NOA completely (its black console window).
REM  2. Double-click this file. Notepad opens.
REM  3. Type your password on one line, save (Ctrl+S) and close Notepad.
REM  4. Start NOA again and sign in with that password (username: owner,
REM     or whatever you renamed it to).
REM
REM  Whatever this file holds is applied on EVERY start, so this is also
REM  the way back in when the password is forgotten.
REM =====================================================================
setlocal
set "NOA_DATA=%LOCALAPPDATA%\NOA"
set "NOA_FILE=%NOA_DATA%\owner-password.txt"
if not exist "%NOA_DATA%" mkdir "%NOA_DATA%"
if not exist "%NOA_FILE%" (
  >"%NOA_FILE%" echo.
)
echo [NOA] %NOA_FILE%
echo [NOA] Write the password you want on the first line, save, and close Notepad.
start "" notepad "%NOA_FILE%"
echo.
echo [NOA] After saving, start NOA again. The password is applied on every start.
pause
