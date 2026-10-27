<#
.SYNOPSIS
    Automated deployment script to stage synthetic diode payloads on Hostinger VPS.

.DESCRIPTION
    1. Connects to Hostinger VPS (root@2.25.249.27) using SSH.
    2. Writes remote Python script `mock_vps_payload.py` to /opt/aios.
    3. The remote script generates `inbound_queue.json` containing:
       - source="hostinger_web_ui"
       - task="Extract the core requirements from this sample client inquiry"
       - priority="high"
       - unix timestamp
    4. Executes `mock_vps_payload.py` remotely so `inbound_queue.json` is staged
       and immediately ready for the local Windows diode to pull down.

.EXAMPLE
    .\deploy-vps-mock-payload.ps1
    .\deploy-vps-mock-payload.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$VpsIp     = "2.25.249.27",
    [string]$VpsUser   = "root",
    [int]$SshPort      = 22,
    [string]$RemoteDir = "/opt/aios",
    [string]$KeyPath   = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Hostinger VPS // Synthetic Diode Payload Stager" -ForegroundColor Cyan
Write-Host " Target: $VpsUser@$VpsIp ($RemoteDir)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Resolve SSH Key
if ([string]::IsNullOrEmpty($KeyPath)) {
    $Candidates = @(
        (Join-Path (Join-Path $HOME ".ssh") "id_rsa"),
        (Join-Path (Join-Path $HOME ".ssh") "id_ed25519")
    )
    foreach ($cand in $Candidates) {
        if (Test-Path $cand) {
            $KeyPath = $cand
            break
        }
    }
}

if (-not (Test-Path $KeyPath)) {
    Write-Warning "No SSH key found at $KeyPath. Default ssh agent will be attempted."
} else {
    Write-Host "[1/4] Using SSH key: $KeyPath" -ForegroundColor Green
}

$SshArgs = @("-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-p", $SshPort)
if (Test-Path $KeyPath) {
    $SshArgs += @("-i", $KeyPath)
}
$Target = "$VpsUser@$VpsIp"

if ($DryRun) {
    Write-Host "[DRY RUN] Would connect to $Target and deploy mock_vps_payload.py." -ForegroundColor Magenta
    exit 0
}

# 2. Check remote connectivity
Write-Host "`n[2/4] Testing SSH handshake to $Target ..." -ForegroundColor Yellow
$CheckOutput = & ssh.exe @SshArgs $Target "mkdir -p $RemoteDir && echo SSH_READY"
if ($LASTEXITCODE -ne 0 -or ($CheckOutput -notcontains "SSH_READY" -and $CheckOutput -ne "SSH_READY")) {
    throw "Failed to connect to Hostinger VPS ($Target)."
}
Write-Host "      Connection established." -ForegroundColor Green

# 3. Create remote mock_vps_payload.py
Write-Host "`n[3/4] Staging remote Python script: $RemoteDir/mock_vps_payload.py ..." -ForegroundColor Yellow

$RemoteScriptCode = @'
#!/usr/bin/env python3
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path

def stage_payload(target_path="/opt/aios/inbound_queue.json"):
    now_ts = time.time()
    payload = {
        "source": "hostinger_web_ui",
        "task": "Extract the core requirements from this sample client inquiry",
        "priority": "high",
        "timestamp": int(now_ts),
        "unix_timestamp": now_ts,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "staged_for_diode",
        "relay_node": "hostinger_vps_relay"
    }
    p = Path(target_path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    tmp.replace(p)

    for sub in ["data", "inbox"]:
        sub_dir = p.parent / sub
        if sub_dir.is_dir():
            sub_file = sub_dir / "inbound_queue.json"
            try:
                with open(sub_file, "w", encoding="utf-8") as f:
                    json.dump(payload, f, indent=2)
            except Exception:
                pass

    return payload

if __name__ == "__main__":
    t = sys.argv[1] if len(sys.argv) > 1 else "/opt/aios/inbound_queue.json"
    res = stage_payload(t)
    print("STAGED_SUCCESS")
    print(json.dumps(res, indent=2))
'@

# Transmit script to remote VPS using base64 to preserve exact formatting & quotes
$Base64Script = [Convert]::ToBase64String([System.Text.Encoding]::UTF8.GetBytes($RemoteScriptCode))
& ssh.exe @SshArgs $Target "echo '$Base64Script' | base64 -d > $RemoteDir/mock_vps_payload.py && chmod +x $RemoteDir/mock_vps_payload.py"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create remote mock_vps_payload.py on Hostinger VPS."
}
Write-Host "      Created $RemoteDir/mock_vps_payload.py successfully." -ForegroundColor Green

# 4. Execute remote script and verify inbound_queue.json
Write-Host "`n[4/4] Executing remote mock_vps_payload.py on Hostinger VPS ..." -ForegroundColor Yellow
$ExecOutput = & ssh.exe @SshArgs $Target "python3 $RemoteDir/mock_vps_payload.py $RemoteDir/inbound_queue.json"
if ($LASTEXITCODE -ne 0) {
    throw "Remote execution of mock_vps_payload.py failed."
}

Write-Host "      Execution complete. Reading staged inbound_queue.json ..." -ForegroundColor Green
$StagedJson = & ssh.exe @SshArgs $Target "cat $RemoteDir/inbound_queue.json"
Write-Host $StagedJson -ForegroundColor White

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " [PASS] Staged synthetic payload at $RemoteDir/inbound_queue.json" -ForegroundColor Cyan
Write-Host " Diode ready for local Windows synchronization." -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
