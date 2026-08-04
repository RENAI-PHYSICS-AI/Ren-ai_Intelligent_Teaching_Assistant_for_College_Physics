$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot
if (-not (Test-Path ".venv\Scripts\streamlit.exe")) {
    uv venv --python 3.13 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}
& ".venv\Scripts\streamlit.exe" run app.py --server.port 8503 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
