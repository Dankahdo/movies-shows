@echo off
setlocal
cd /d "%~dp0"

set "VENV_PY=%~dp0.venv\Scripts\python.exe"

if not exist "%VENV_PY%" (
    echo Virtual environment not found at .venv
    echo Create it with: py -m venv .venv
    pause
    exit /b 1
)

"%VENV_PY%" "%~dp0media_center_app.py"

if errorlevel 1 (
    echo.
    echo The app exited with an error.
    pause
)
