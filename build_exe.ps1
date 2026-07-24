param(
    [string]$AppName = "LocalMediaCenter"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found at .venv. Create it first, then install requirements."
}

$python = Resolve-Path ".venv\Scripts\python.exe"

& $python -m pip install --upgrade pip
& $python -m pip install -r requirements.txt pyinstaller

& $python -m PyInstaller `
    --noconfirm `
    --windowed `
    --name $AppName `
    --collect-submodules PySide6.QtMultimedia `
    --collect-submodules PySide6.QtMultimediaWidgets `
    media_center_app.py

Write-Host "Build complete. EXE output: dist\$AppName\$AppName.exe"
