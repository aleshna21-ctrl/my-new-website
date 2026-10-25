<#
.SYNOPSIS
    Synchronizes the local Obsidian vault to the Hostinger VPS server via rsync over SSH.

.DESCRIPTION
    Preserves full directory structure, timestamps, and metadata while performing
    differential incremental transfers (only sending modified or new files).

.EXAMPLE
    .\sync-vault.ps1
    .\sync-vault.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$VpsHost   = "root@2.25.249.27",
    [string]$RemoteDir = "/opt/aios/vault/",
    [string]$VaultPath = "G:\My Drive\second-brain",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Obsidian Vault // Rsync over SSH Synchronizer" -ForegroundColor Cyan
Write-Host " Source : $VaultPath" -ForegroundColor Cyan
Write-Host " Target : ${VpsHost}:${RemoteDir}" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path -LiteralPath $VaultPath)) {
    throw "Source Obsidian vault not found at: $VaultPath"
}

$DryRunFlag = if ($DryRun) { "--dry-run" } else { "" }

$BashCmd = @"
set -e
mkdir -p /mnt/g
mount -t drvfs G: /mnt/g 2>/dev/null || true
mkdir -p /root/.ssh
cp /mnt/c/Users/alesh/.ssh/id_rsa /root/.ssh/id_rsa
chmod 600 /root/.ssh/id_rsa

echo '===> Executing differential rsync transfer over SSH...'
rsync -avzu --human-readable --stats $DryRunFlag \
  -e "ssh -i /root/.ssh/id_rsa -o StrictHostKeyChecking=no" \
  "/mnt/g/My Drive/second-brain/" \
  "${VpsHost}:${RemoteDir}"
"@

wsl -u root sh -c "$BashCmd"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`nVault sync completed successfully." -ForegroundColor Green
} else {
    throw "Rsync failed with exit code $LASTEXITCODE"
}
