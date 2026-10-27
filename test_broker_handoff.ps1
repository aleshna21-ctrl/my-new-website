# test_broker_handoff.ps1
# ======================
# Standalone PowerShell tracer bullet script:
# 1. Injects a dummy task into job_ledger.db in [ INBOX ] state
# 2. Runs the Async Orchestrator Daemon single pass
# 3. Verifies that the task transitions to [ DONE ] without locking up the database or dashboard

$ErrorActionPreference = "Stop"

Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host " [TRACER BULLET - PS] Decoupled Message Broker Tracer Execution" -ForegroundColor Cyan
Write-Host "========================================================================" -ForegroundColor Cyan

$WorkspaceRoot = (Get-Item $PSScriptRoot).FullName
$PythonExe = (Get-Command python).Source

Write-Host "`n[Step 1] Invoking Python tracer bullet runner..." -ForegroundColor Yellow
& $PythonExe "$WorkspaceRoot\test_broker_handoff.py"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n[SUCCESS] PowerShell tracer bullet handoff verified successfully." -ForegroundColor Green
    exit 0
} else {
    Write-Host "`n[FAILURE] Tracer bullet handoff failed." -ForegroundColor Red
    exit 1
}
