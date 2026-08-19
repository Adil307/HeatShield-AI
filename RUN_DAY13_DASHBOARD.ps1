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
Write-Host "Starting HeatShield Day 13 dashboard..." -ForegroundColor Cyan
Write-Host "Open: http://127.0.0.1:8000/dashboard/#live" -ForegroundColor Green
& $Python -m scripts.day10_dashboard_server
