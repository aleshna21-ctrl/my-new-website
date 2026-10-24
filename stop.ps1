$ErrorActionPreference = 'Stop'
$deploymentRoot = $PSScriptRoot
foreach ($name in @('server', 'observer')) {
    $pidFile = Join-Path $deploymentRoot "state\$name.pid"
    if (Test-Path -LiteralPath $pidFile) {
        $processId = [int](Get-Content -LiteralPath $pidFile -Raw)
        $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
        $expected = if ($name -eq 'server') { Join-Path $deploymentRoot 'app.py' } else { Join-Path $deploymentRoot 'offline_observer.py' }
        if ($process -and $process.CommandLine -and $process.CommandLine.Contains($expected)) {
            Stop-Process -Id $processId -ErrorAction Stop
            Write-Host "Stopped JEV $name ($processId)."
        }
        Remove-Item -LiteralPath $pidFile
    }
}
