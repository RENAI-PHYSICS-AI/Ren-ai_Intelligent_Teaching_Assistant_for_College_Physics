$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot

if (-not (Test-Path ".venv\Scripts\uvicorn.exe")) {
    uv venv --python 3.13 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}

& ".venv\Scripts\uvicorn.exe" admin_api:app --host 127.0.0.1 --port 8603
