$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot

if (-not (Test-Path ".venv\Scripts\uvicorn.exe")) {
    uv venv --python 3.13 .venv
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}

$admin = Start-Process -FilePath ".venv\Scripts\uvicorn.exe" `
    -ArgumentList @("admin_api:app", "--host", "127.0.0.1", "--port", "8603") `
    -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru

try {
    & ".venv\Scripts\streamlit.exe" run app.py --server.port 8501 --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
}
finally {
    if ($admin -and -not $admin.HasExited) {
        Stop-Process -Id $admin.Id
    }
}
