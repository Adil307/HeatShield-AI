$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$RootPython = Join-Path $Root ".venv\Scripts\python.exe"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"

if (Test-Path $RootPython) {
    $Python = $RootPython
} elseif (Test-Path $BackendPython) {
    $Python = $BackendPython
} else {
    throw "HeatShield virtual environment Python was not found."
}

Write-Host "HeatShield AI - Day 12 Dashboard" -ForegroundColor Cyan
Write-Host "Dashboard: http://127.0.0.1:8000/dashboard/#live"
Write-Host "Step 1: Run FortyGuard Analysis"
Write-Host "Step 2: Enrich Hottest Tile"
Write-Host "The enrichment step may create one Environmental Parameters provider job."
Write-Host "Historical judge replay remains available and unchanged."
Write-Host "Stop server with Ctrl+C"
Write-Host ""

Start-Process "http://127.0.0.1:8000/dashboard/#live"
Set-Location $Backend
& $Python -m scripts.day10_dashboard_server
