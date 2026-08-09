$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot

$needsInstall = -not (Test-Path ".venv\Scripts\python.exe")
if ($needsInstall) {
    uv venv --python 3.13 .venv
}
if (-not $needsInstall) {
    & ".venv\Scripts\python.exe" -c "import aiohttp, streamlit, uvicorn"
    $needsInstall = $LASTEXITCODE -ne 0
}
if ($needsInstall) {
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}

$admin = Start-Process -FilePath ".venv\Scripts\uvicorn.exe" `
    -ArgumentList @("admin_api:app", "--host", "127.0.0.1", "--port", "8603") `
    -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru

$web = Start-Process -FilePath ".venv\Scripts\streamlit.exe" `
    -ArgumentList @("run", "app.py", "--server.port=8502", "--server.address=127.0.0.1", "--server.headless=true", "--browser.gatherUsageStats=false") `
    -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru

try {
    & ".venv\Scripts\python.exe" gateway.py
}
finally {
    if ($web -and -not $web.HasExited) {
        Stop-Process -Id $web.Id
    }
    if ($admin -and -not $admin.HasExited) {
        Stop-Process -Id $admin.Id
    }
}
