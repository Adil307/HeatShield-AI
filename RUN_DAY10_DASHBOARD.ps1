$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Backend = Join-Path $Root "backend"

if (-not (Test-Path $Python)) { throw "Project virtual environment Python not found: $Python" }
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Write-Warning "Ollama is not on PATH. Dashboard evidence will work, but local-Qwen Copilot may not."
}

Write-Host "HeatShield AI - Day 10 Judge Dashboard"
Write-Host "Dashboard: http://127.0.0.1:8000/dashboard/"
Write-Host "Stop server with Ctrl+C"
Write-Host ""

Start-Process "http://127.0.0.1:8000/dashboard/"
Set-Location $Backend
& $Python -m scripts.day10_dashboard_server
