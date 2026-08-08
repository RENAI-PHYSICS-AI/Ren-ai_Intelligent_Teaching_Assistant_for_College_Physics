$ErrorActionPreference = "Stop"

$rules = @(
    @{
        Name = "大学物理智能助教 (Streamlit 8501)"
        Description = "允许专用局域网设备访问大学物理智能助教"
        Ports = "8501"
    },
    @{
        Name = "大学物理智能助教 (可视化实验 9384-9385)"
        Description = "允许专用局域网设备访问李萨如和声速可视化实验"
        Ports = "9384-9385"
    }
)
$isAdministrator = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdministrator) {
    Write-Host "请右键此脚本，选择‘使用 PowerShell 运行’，并在管理员授权窗口中确认。" -ForegroundColor Yellow
    Write-Host "也可以在管理员 PowerShell 中执行：" -ForegroundColor Yellow
    Write-Host "  & '$PSCommandPath'" -ForegroundColor Cyan
    Read-Host "按 Enter 退出"
    exit 1
}

foreach ($rule in $rules) {
    $existing = Get-NetFirewallRule -DisplayName $rule.Name -ErrorAction SilentlyContinue
    if ($existing) {
        Set-NetFirewallRule -DisplayName $rule.Name -Enabled True -Profile Private -Direction Inbound -Action Allow
        $existing | Get-NetFirewallPortFilter | Set-NetFirewallPortFilter -Protocol TCP -LocalPort $rule.Ports
    } else {
        New-NetFirewallRule `
            -DisplayName $rule.Name `
            -Description $rule.Description `
            -Enabled True `
            -Profile Private `
            -Direction Inbound `
            -Action Allow `
            -Protocol TCP `
            -LocalPort $rule.Ports | Out-Null
    }
}
Write-Host "已配置智能助教和可视化实验的局域网防火墙规则。" -ForegroundColor Green

$addresses = Get-NetIPConfiguration |
    Where-Object { $_.NetAdapter.Status -eq "Up" -and $_.IPv4Address } |
    ForEach-Object { $_.IPv4Address.IPAddress } |
    Where-Object { $_ -notlike "127.*" -and $_ -notlike "169.254.*" }

Write-Host "局域网访问地址：" -ForegroundColor Cyan
foreach ($address in $addresses) {
    Write-Host "  http://$address`:8501"
}
Write-Host "只允许 Windows 标记为‘专用’的网络访问。" -ForegroundColor DarkGray
Read-Host "按 Enter 退出"
