<#
.SYNOPSIS
    Configures passwordless Ed25519 SSH key authentication for your Hostinger VPS (root@2.25.249.27).

.DESCRIPTION
    1. Generates ~/.ssh/id_ed25519 if it does not already exist.
    2. Installs the public key into /root/.ssh/authorized_keys on root@2.25.249.27 (prompts for password once).
    3. Adds a 'hostinger-aios' host entry to ~/.ssh/config if not present.
    4. Tests passwordless login with BatchMode=yes.

.EXAMPLE
    .\setup-ssh-key.ps1
    .\setup-ssh-key.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$VpsIp       = "2.25.249.27",
    [string]$VpsUser     = "root",
    [int]$SshPort        = 22,
    [string]$VpsPassword = $env:VPS_SSH_PASSWORD,
    [switch]$Interactive,
    [switch]$DeployAfterSetup,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"
$SshDir  = Join-Path $HOME ".ssh"
$KeyPath = Join-Path $SshDir "id_ed25519"
$PubPath = "$KeyPath.pub"
$CfgPath = Join-Path $SshDir "config"
$Target  = "$VpsUser@$VpsIp"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " AIOS // Passwordless SSH Key Setup for $Target" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $SshDir)) {
    New-Item -ItemType Directory -Path $SshDir -Force | Out-Null
}

# 1. Ensure Ed25519 SSH Key Exists
if (-not (Test-Path $PubPath)) {
    Write-Host "`n[1/4] Generating new Ed25519 SSH key at $KeyPath ..." -ForegroundColor Yellow
    if (-not $DryRun) {
        & ssh-keygen.exe -t ed25519 -C "aios-deploy@$env:COMPUTERNAME" -f $KeyPath -N '""'
        if ($LASTEXITCODE -ne 0) {
            throw "ssh-keygen failed."
        }
    } else {
        Write-Host "      [DRY RUN] Would run: ssh-keygen -t ed25519 -f $KeyPath" -ForegroundColor Magenta
    }
} else {
    Write-Host "`n[1/4] Found existing Ed25519 public key: $PubPath" -ForegroundColor Green
}

$PubKey = if (Test-Path $PubPath) { (Get-Content $PubPath -Raw).Trim() } else { "ssh-ed25519 AAAA... (generated on run)" }
Write-Host "      Public Key: $PubKey" -ForegroundColor Gray

# 2. Configure ~/.ssh/config alias (without forcing IdentitiesOnly before key is installed)
Write-Host "`n[2/4] Checking local SSH config ($CfgPath) ..." -ForegroundColor Yellow
$AliasBlock = @"

Host hostinger-aios $VpsIp
    HostName $VpsIp
    User $VpsUser
    IdentityFile ~/.ssh/id_ed25519
"@

if (Test-Path $CfgPath) {
    $RawCfg = Get-Content $CfgPath -Raw
    if ($RawCfg -match "IdentitiesOnly yes") {
        $RawCfg = $RawCfg -replace "\r?\n\s*IdentitiesOnly yes", ""
        Set-Content -Path $CfgPath -Value $RawCfg -Encoding UTF8
    }
}

$HasConfig = (Test-Path $CfgPath) -and ((Get-Content $CfgPath -Raw) -match [regex]::Escape($VpsIp))
if (-not $HasConfig) {
    if (-not $DryRun) {
        Add-Content -Path $CfgPath -Value $AliasBlock -Encoding UTF8
        Write-Host "      Added SSH config entry for $VpsIp (alias: hostinger-aios)." -ForegroundColor Green
    } else {
        Write-Host "      [DRY RUN] Would append Host entry for $VpsIp to $CfgPath" -ForegroundColor Magenta
    }
} else {
    Write-Host "      SSH config already contains an entry for $VpsIp." -ForegroundColor Green
}

# 3. Pre-flight TCP reachability check & public key installation on root@2.25.249.27
$RemoteCmd = "umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; grep -qxF '$PubKey' ~/.ssh/authorized_keys || echo '$PubKey' >> ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; echo '---> Authorized key installed on' `$(hostname)"

if ($DryRun) {
    Write-Host "`n[3/4] [DRY RUN] Would install public key on $Target via:" -ForegroundColor Magenta
    Write-Host "      ssh $Target `"$RemoteCmd`"" -ForegroundColor Gray
    Write-Host "`n[4/4] [DRY RUN] Would verify passwordless login with:" -ForegroundColor Magenta
    Write-Host "      ssh -o BatchMode=yes $Target `"echo OK`"" -ForegroundColor Gray
    exit 0
}

Write-Host "`n[3/4] Checking TCP connectivity to ${VpsIp}:${SshPort} (4s timeout)..." -ForegroundColor Yellow
& icacls.exe $KeyPath /inheritance:r /grant:r "$($env:USERNAME):(R,W)" | Out-Null
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
Write-Host "      TCP port $SshPort is open on $VpsIp. Testing non-interactive SSH authentication..." -ForegroundColor Green

& ssh.exe -i $KeyPath -p $SshPort -o BatchMode=yes -o ConnectTimeout=5 -o StrictHostKeyChecking=accept-new $Target $RemoteCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "      [Diagnostic] Testing private key decryption and ssh -vvv for $KeyPath ..." -ForegroundColor Yellow
    $PrevEAP = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $KeyTest = & ssh-keygen.exe -y -P '""' -f $KeyPath 2>&1
    Write-Host "        ssh-keygen -y test (exit $LASTEXITCODE): $KeyTest" -ForegroundColor Cyan
    $DiagOut = & ssh.exe -vvv -i $KeyPath -p $SshPort -o BatchMode=yes -o ConnectTimeout=5 $Target "echo OK" 2>&1
    $ErrorActionPreference = $PrevEAP
    $DiagOut | ForEach-Object { "$_" } | Select-Object -Last 30 | ForEach-Object { Write-Host "        $_" -ForegroundColor Gray }
    if (-not [string]::IsNullOrWhiteSpace($VpsPassword)) {
        Write-Host "      Installing public key using provided VPS password (SSH_ASKPASS)..." -ForegroundColor Yellow
        $AskPassBat = Join-Path $env:TEMP ("aios_askpass_" + [guid]::NewGuid().ToString("N") + ".cmd")
        try {
            Set-Content -Path $AskPassBat -Value "@echo off`r`necho $VpsPassword" -Encoding ASCII
            $env:SSH_ASKPASS = $AskPassBat
            $env:SSH_ASKPASS_REQUIRE = "force"
            $env:DISPLAY = "127.0.0.1:0.0"
            & ssh.exe -p $SshPort -o ConnectTimeout=8 -o StrictHostKeyChecking=accept-new $Target $RemoteCmd
            if ($LASTEXITCODE -ne 0) {
                throw "SSH key installation failed with provided password."
            }
        } finally {
            Remove-Item $AskPassBat -Force -ErrorAction SilentlyContinue
            Remove-Item Env:\SSH_ASKPASS -ErrorAction SilentlyContinue
            Remove-Item Env:\SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
        }
    } elseif ($Interactive) {
        Write-Host "      Please enter the password for $Target when prompted below:" -ForegroundColor Cyan
        & ssh.exe -p $SshPort -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new $Target $RemoteCmd
        if ($LASTEXITCODE -ne 0) {
            throw "Interactive SSH key installation failed on ${Target}:${SshPort}."
        }
    } else {
        Write-Host "      Available keys in ${SshDir}:" -ForegroundColor Yellow
        Get-ChildItem -Path $SshDir -File | ForEach-Object { Write-Host "        - $($_.Name)" -ForegroundColor Gray }
        throw "Non-interactive SSH authentication failed on ${Target}:${SshPort} (public key not yet authorized on remote host)."
    }
}

# 4. Verify Passwordless Login
Write-Host "`n[4/4] Verifying passwordless SSH connection (BatchMode=yes)..." -ForegroundColor Yellow
& ssh.exe -p $SshPort -o ConnectTimeout=5 -o BatchMode=yes $Target "echo '      SUCCESS: Passwordless SSH verified on' `$(hostname) '('`$(uname -sr)')'"
if ($LASTEXITCODE -ne 0) {
    throw "Passwordless verification failed."
}

Write-Host "`nAll set! Passwordless SSH is active for $Target." -ForegroundColor Green
if ($DeployAfterSetup) {
    $DeployScript = Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "deploy-hostinger.ps1"
    & $DeployScript -VpsIp $VpsIp -VpsUser $VpsUser -SshPort $SshPort -InstallBackupCron
}
