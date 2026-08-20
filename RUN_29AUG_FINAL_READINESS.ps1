$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw $Message
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$RootPython = Join-Path $Root ".venv\Scripts\python.exe"
$BackendPython = Join-Path $Backend ".venv\Scripts\python.exe"
if (Test-Path $RootPython) { $Python = $RootPython }
elseif (Test-Path $BackendPython) { $Python = $BackendPython }
else { $Python = "python" }

Write-Host "HeatShield AI - 29 Aug Final Readiness Gate" -ForegroundColor Green
Write-Host "Python: $Python"

Push-Location $Backend

Step "Running complete pytest regression suite"
& $Python -m pytest -q
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Pytest regression suite failed." }

$Smokes = @(
    "scripts.day10_dashboard_smoke_test",
    "scripts.day11_live_analysis_smoke_test",
    "scripts.day12_live_decision_smoke_test",
    "scripts.day13_live_context_priority_smoke_test",
    "scripts.day14_live_copilot_smoke_test",
    "scripts.day15_live_scenario_smoke_test",
    "scripts.build15_1_demo_reliability_smoke_test",
    "scripts.build16_final_ai_evaluation",
    "scripts.build16_release_smoke_test"
)

foreach ($Smoke in $Smokes) {
    Step "Running $Smoke"
    & $Python -m $Smoke
    if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "Final readiness smoke failed: $Smoke" }
}

Step "Checking local Qwen router when available"
try {
    & $Python -m scripts.day14_live_qwen_smoke_test
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Local Qwen smoke did not pass. Deterministic grounding is still verified; fix Ollama before demonstrating local routing."
    }
} catch {
    Write-Warning "Local Ollama/Qwen unavailable. Deterministic grounded assistant remains verified."
}

Pop-Location

Step "Checking dashboard JavaScript syntax when Node.js is available"
$Node = Get-Command node -ErrorAction SilentlyContinue
if ($Node) {
    & node --check (Join-Path $Root "frontend\dashboard\app.js")
    if ($LASTEXITCODE -ne 0) { Fail "Dashboard JavaScript syntax check failed." }
} else {
    Write-Warning "Node.js is not installed; JavaScript syntax check skipped. Frontend pytest contracts still passed."
}

Step "Checking whitespace"
Push-Location $Root
git diff --check
if ($LASTEXITCODE -ne 0) { Pop-Location; Fail "git diff --check failed." }
Pop-Location

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "FINAL READINESS: PASS" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "Generated AI metrics:" -ForegroundColor Cyan
Write-Host "  backend\data\processed\build16_final_ai_evaluation.json"
Write-Host "  backend\data\processed\build16_final_ai_evaluation.md"
Write-Host ""
Write-Host "Next: perform and record three successful demo rehearsals." -ForegroundColor Yellow
