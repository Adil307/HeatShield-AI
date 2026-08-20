$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$RootPython = Join-Path $Root ".venv\Scripts\python.exe"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (Test-Path $RootPython) { $Python = $RootPython }
elseif (Test-Path $BackendPython) { $Python = $BackendPython }
else { $Python = "python" }

Set-Location $Backend
Write-Host "Starting HeatShield AI final judge dashboard..." -ForegroundColor Cyan
Write-Host "Dashboard:       http://127.0.0.1:8000/dashboard/" -ForegroundColor Green
Write-Host "Live Analysis:   http://127.0.0.1:8000/dashboard/#live" -ForegroundColor Green
Write-Host "Assistant:       http://127.0.0.1:8000/dashboard/#copilot" -ForegroundColor Green
Write-Host "Scenario Studio: http://127.0.0.1:8000/dashboard/#scenario" -ForegroundColor Green
& $Python -m scripts.day10_dashboard_server
