$ErrorActionPreference = "Stop"
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppRoot
$needsInstall = -not (Test-Path ".venv\Scripts\python.exe")
if ($needsInstall) {
    uv venv --python 3.13 .venv
}
if (-not $needsInstall) {
    & ".venv\Scripts\python.exe" -c "import aiohttp, sherpa_onnx, streamlit"
    $needsInstall = $LASTEXITCODE -ne 0
}
if ($needsInstall) {
    uv pip install --python .venv\Scripts\python.exe -r requirements.txt
}

function Wait-LocalHealth {
    param([string]$Uri, [System.Diagnostics.Process]$Process, [int]$TimeoutSeconds = 120)
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($Process.HasExited) {
            throw "服务启动失败：$Uri"
        }
        try {
            Invoke-RestMethod -Uri $Uri -TimeoutSec 2 | Out-Null
            return
        }
        catch {
            Start-Sleep -Milliseconds 500
        }
    }
    throw "服务健康检查超时：$Uri"
}

$asr = $null
$web = $null
try {
    & ".venv\Scripts\python.exe" download_asr_model.py
    if ($LASTEXITCODE -ne 0) {
        throw "Paraformer 流式模型准备失败。"
    }
    $asr = Start-Process -FilePath ".venv\Scripts\python.exe" `
        -ArgumentList @("-m", "uvicorn", "asr_service:app", "--host", "127.0.0.1", "--port", "8604") `
        -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru
    Wait-LocalHealth -Uri "http://127.0.0.1:8604/health" -Process $asr
    $web = Start-Process -FilePath ".venv\Scripts\streamlit.exe" `
        -ArgumentList @("run", "app.py", "--server.port=8502", "--server.address=127.0.0.1", "--server.headless=true", "--browser.gatherUsageStats=false") `
        -WorkingDirectory $AppRoot -WindowStyle Hidden -PassThru
    & ".venv\Scripts\python.exe" gateway.py
}
finally {
    if ($web -and -not $web.HasExited) {
        Stop-Process -Id $web.Id
    }
    if ($asr -and -not $asr.HasExited) {
        Stop-Process -Id $asr.Id
    }
}
