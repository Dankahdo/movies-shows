Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Virtual environment not found at .venv"
}

$python = Resolve-Path ".venv\Scripts\python.exe"
& $python media_center_app.py
