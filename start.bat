@echo off
setlocal
cd /d "%~dp0"

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

".venv\Scripts\python.exe" "server\dev_start.py"

echo.
echo Server stopped.
pause
