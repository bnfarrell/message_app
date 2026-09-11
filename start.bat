@echo off
setlocal
cd /d "%~dp0"

REM ---------------------------------------------------------------------------
REM Cold-starts BOTH halves of the app and opens a browser.
REM
REM   API  (Flask)  http://127.0.0.1:5200  - migrates, seeds if empty, runs the
REM                                          job worker and the SLA sweep
REM   Web  (Vite)   http://127.0.0.1:5173  - the React client you actually look at
REM
REM The API alone serves no pages: GET / returns 404 by design. The web client is
REM the surface, and it proxies /api, /ws and /a through to the API. Starting only
REM one of them looks like "nothing happens", which is why this script starts both.
REM ---------------------------------------------------------------------------

if not exist ".venv\Scripts\python.exe" (
    echo.
    echo Virtual environment not found at .venv\Scripts\python.exe
    echo Create it first, then run this again:
    echo.
    echo     python -m venv .venv
    echo     cd server ^&^& ..\.venv\Scripts\pip.exe install -e ".[dev]"
    echo.
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo Node.js was not found on PATH. The web client needs Node 20 or newer.
    echo Install it from https://nodejs.org/ then run this again.
    echo.
    pause
    exit /b 1
)

if not exist "web\node_modules" (
    echo.
    echo Installing web dependencies. This happens once and takes a minute...
    echo.
    pushd web
    call npm install
    if errorlevel 1 (
        echo.
        echo npm install failed. Fix the error above, then run this again.
        popd
        pause
        exit /b 1
    )
    popd
)

echo.
echo Starting the API on http://127.0.0.1:5200 ...
start "Harbourview API" ".venv\Scripts\python.exe" "server\dev_start.py"

echo Starting the web client on http://127.0.0.1:5173 ...
pushd web
start "Harbourview Web" cmd /k npm run dev
popd

echo.
echo Waiting for the web client to come up...

REM curl ships with Windows 10 1803 and newer. If it is missing we cannot poll,
REM so fall back to a fixed wait rather than wrongly reporting a failure.
where curl >nul 2>&1
if errorlevel 1 (
    echo    ^(curl not found - waiting 15 seconds instead of polling^)
    ping -n 16 127.0.0.1 >nul
    goto :open
)

set "READY="
for /l %%i in (1,1,60) do (
    if not defined READY (
        curl -s -o nul --max-time 2 http://127.0.0.1:5173/ && set "READY=1"
        if not defined READY ping -n 2 127.0.0.1 >nul
    )
)

if not defined READY (
    echo.
    echo The web client did not answer on http://127.0.0.1:5173 within 60 seconds.
    echo Check the "Harbourview Web" window for the real error - the usual causes
    echo are a port already in use or a failed npm install.
    echo.
    pause
    exit /b 1
)

:open
echo Ready. Opening the browser...
start "" http://127.0.0.1:5173/

echo.
echo ---------------------------------------------------------------------------
echo   App:   http://127.0.0.1:5173/
echo   Login: ava@hvh.test  /  Password123!   ^(agent - inbox^)
echo          alex@hvh.test /  Password123!   ^(admin - admin screens^)
echo.
echo   Two windows are now running: "Harbourview API" and "Harbourview Web".
echo   Close both to stop the app.
echo ---------------------------------------------------------------------------
echo.
pause
