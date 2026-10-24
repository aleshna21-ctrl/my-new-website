<#
.SYNOPSIS
    One-command deployment script to sync and launch the AIOS Command Center
    Docker Compose stack on your Hostinger VPS (2.25.249.27).

.DESCRIPTION
    Uses built-in Windows tools (tar, scp, ssh) — no extra Windows software required:
      1. Packages application files into a clean .tar.gz bundle (excluding caches/tests).
      2. Uploads the bundle to root@2.25.249.27 via SCP.
      3. Extracts into /opt/aios, initializes .env if missing, and runs `docker compose up -d --build`.
      4. Verifies container health and probes http://127.0.0.1:5050/api/os/telemetry on the VPS.

.EXAMPLE
    .\deploy-hostinger.ps1
    .\deploy-hostinger.ps1 -DryRun
    .\deploy-hostinger.ps1 -BindIp "127.0.0.1"
#>
[CmdletBinding()]
param(
    [string]$VpsIp         = "2.25.249.27",
    [string]$VpsUser       = "root",
    [int]$SshPort          = 22,
    [string]$RemoteDir     = "/opt/aios",
    [int]$Port             = 5050,
    [string]$BindIp        = "0.0.0.0",
    [string]$KeyPassphrase = $env:SSH_KEY_PASSPHRASE,
    [switch]$Interactive,
    [switch]$InstallBackupCron,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

$TargetHost = "$VpsUser@$VpsIp"
$BundlePath = Join-Path $env:TEMP "aios-deploy-bundle.tar.gz"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " AIOS Command Center // Hostinger VPS Deployer ($TargetHost)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# 1. Create clean deployment archive using built-in tar
Write-Host "`n[1/4] Packaging project files into $BundlePath ..." -ForegroundColor Yellow
if (Test-Path $BundlePath) {
    Remove-Item $BundlePath -Force
}

$TarArgs = @(
    "-czf", $BundlePath,
    "--exclude=.git",
    "--exclude=__pycache__",
    "--exclude=*.pyc",
    "--exclude=.pytest_cache",
    "--exclude=tests",
    "--exclude=docs",
    "--exclude=state/server",
    "--exclude=*.tmp*",
    "Dockerfile",
    "compose.yml",
    ".dockerignore",
    ".env.example",
    "requirements.txt",
    "vps-backup-and-auth.sh",
    "hud_server.py",
    "app.py",
    "hud",
    "static",
    "config",
    "inbox",
    "plugins"
)

& tar.exe @TarArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create deployment archive with tar.exe"
}

$BundleSizeKB = [math]::Round((Get-Item $BundlePath).Length / 1KB, 1)
Write-Host "      Archive ready ($BundleSizeKB KB)." -ForegroundColor Green

$CronStep = if ($InstallBackupCron) { "$RemoteDir/vps-backup-and-auth.sh install-cron" } else { "echo '---> Backup helper ready at $RemoteDir/vps-backup-and-auth.sh'" }
$PubKeyPath = Join-Path (Join-Path $HOME ".ssh") "id_ed25519.pub"
$PubKeyLine = if (Test-Path $PubKeyPath) { (Get-Content $PubKeyPath -Raw).Trim() } else { "" }

# Prepare remote provisioning & Docker Compose startup script
$RemoteScript = @"
set -e
mkdir -p ~/.ssh && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys
if [ -n '$PubKeyLine' ]; then grep -qxF '$PubKeyLine' ~/.ssh/authorized_keys || echo '$PubKeyLine' >> ~/.ssh/authorized_keys; fi
echo '---> Preparing $RemoteDir on VPS...'
mkdir -p $RemoteDir/data $RemoteDir/scratch $RemoteDir/vault $RemoteDir/calendar $RemoteDir/backups
tar -xzf /tmp/aios-deploy-bundle.tar.gz -C $RemoteDir
rm -f /tmp/aios-deploy-bundle.tar.gz
sed -i 's/\r$//' $RemoteDir/vps-backup-and-auth.sh
chmod +x $RemoteDir/vps-backup-and-auth.sh

cd $RemoteDir
if [ ! -f .env ]; then
    cp .env.example .env
fi
sed -i 's/^HUD_BIND_IP=.*/HUD_BIND_IP=$BindIp/' .env
sed -i 's/^HUD_PORT=.*/HUD_PORT=$Port/' .env
echo '---> Configured .env (HUD_BIND_IP=$BindIp, HUD_PORT=$Port)'

if ! command -v docker >/dev/null 2>&1; then
    echo '---> Docker not found. Installing Docker Engine & Compose plugin...'
    apt-get update -y
    curl -fsSL https://get.docker.com | sh
    apt-get install -y docker-compose-plugin
fi

if command -v ufw >/dev/null 2>&1; then
    if ufw status | grep -q "Status: active"; then
        echo '---> Allowing TCP port $Port in UFW firewall...'
        ufw allow $Port/tcp >/dev/null || true
    fi
fi

echo '---> Building and starting AIOS Command Center container...'
docker compose up -d --build

echo '---> Waiting 3 seconds for container startup...'
sleep 3
docker compose ps

echo '---> Probing live telemetry endpoint on VPS loopback...'
python3 -c "import urllib.request, json; r=urllib.request.urlopen('http://127.0.0.1:$Port/api/os/telemetry', timeout=5); d=json.loads(r.read()); print('VPS Telemetry OK: HTTP', r.status, '| ts=', d.get('ts'), '| hash=', d.get('hash'))"
$CronStep
"@

if ($DryRun) {
    Write-Host "`n[DRY RUN] Would upload $BundlePath ($BundleSizeKB KB) to ${TargetHost}:/tmp/aios-deploy-bundle.tar.gz" -ForegroundColor Magenta
    Write-Host "[DRY RUN] Would execute on ${TargetHost}:" -ForegroundColor Magenta
    Write-Host $RemoteScript -ForegroundColor Gray
    exit 0
}

# 2. Pre-flight TCP check & Upload archive via SCP
Write-Host "`n[2/4] Checking TCP connectivity to ${VpsIp}:${SshPort} (4s timeout) ..." -ForegroundColor Yellow
$TcpClient = New-Object System.Net.Sockets.TcpClient
try {
    $ConnectAsync = $TcpClient.BeginConnect($VpsIp, $SshPort, $null, $null)
    $Completed = $ConnectAsync.AsyncWaitHandle.WaitOne(4000, $false)
    if (-not $Completed) {
        throw "Timed out after 4000ms"
    }
    $TcpClient.EndConnect($ConnectAsync)
} catch {
    $TcpClient.Close()
    throw "TCP connection to ${VpsIp}:${SshPort} failed ($($_.Exception.Message)). Ensure VPS is running and port $SshPort is open."
}
$TcpClient.Close()

$KeyPath = Join-Path (Join-Path $HOME ".ssh") "id_ed25519"
$AskPassBat = $null

if ($Interactive -and [string]::IsNullOrEmpty($KeyPassphrase)) {
    Write-Host "`n      [Interactive Auth] Testing if key is already unlocked..." -ForegroundColor Cyan
    & ssh.exe -i $KeyPath -p $SshPort -o ConnectTimeout=5 -o BatchMode=yes $TargetHost "echo OK" 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        $SecPass = Read-Host -Prompt "      Enter passphrase for $KeyPath (or password for $TargetHost)" -AsSecureString
        $Bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecPass)
        try {
            $KeyPassphrase = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($Bstr)
        } finally {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($Bstr)
        }
    }
}

if (-not [string]::IsNullOrEmpty($KeyPassphrase)) {
    $AskPassBat = Join-Path $env:TEMP ("aios_keypass_" + [guid]::NewGuid().ToString("N") + ".cmd")
    Set-Content -Path $AskPassBat -Value "@echo off`r`necho $KeyPassphrase" -Encoding ASCII
    $env:SSH_ASKPASS = $AskPassBat
    $env:SSH_ASKPASS_REQUIRE = "force"
    $env:DISPLAY = "127.0.0.1:0.0"
}

try {
    $BatchOpt = if ($AskPassBat -or $Interactive) { "BatchMode=no" } else { "BatchMode=yes" }
    Write-Host "      Uploading archive to ${TargetHost}:/tmp/aios-deploy-bundle.tar.gz (SSH port $SshPort) ..." -ForegroundColor Yellow
    & scp.exe -i $KeyPath -P $SshPort -o ConnectTimeout=10 -o $BatchOpt $BundlePath "${TargetHost}:/tmp/aios-deploy-bundle.tar.gz"
    if ($LASTEXITCODE -ne 0) {
        throw "SCP upload failed. Verify SSH key access (or -KeyPassphrase) for ${TargetHost}:$SshPort."
    }

    # 3. Execute remote extraction, build, and launch via SSH
    Write-Host "`n[3/4] Extracting and launching Docker Compose stack on $TargetHost ..." -ForegroundColor Yellow
    $CleanRemoteScript = $RemoteScript -replace "`r`n", "`n"
    & ssh.exe -i $KeyPath -p $SshPort -o ConnectTimeout=10 -o $BatchOpt $TargetHost $CleanRemoteScript
    if ($LASTEXITCODE -ne 0) {
        throw "Remote deployment command failed on $TargetHost."
    }
} finally {
    if ($AskPassBat -and (Test-Path $AskPassBat)) {
        Remove-Item $AskPassBat -Force -ErrorAction SilentlyContinue
    }
    Remove-Item Env:\SSH_ASKPASS -ErrorAction SilentlyContinue
    Remove-Item Env:\SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
}

# 4. Done
Write-Host "`n[4/4] Deployment complete!" -ForegroundColor Green
if ($BindIp -eq "0.0.0.0") {
    Write-Host "      Live Dashboard URL: http://${VpsIp}:${Port}/" -ForegroundColor Cyan
} else {
    Write-Host "      Bound to VPS loopback (127.0.0.1:${Port}) for Nginx Reverse Proxy." -ForegroundColor Cyan
}
