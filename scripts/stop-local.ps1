$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $projectRoot '.local'

foreach ($name in @('web', 'backend')) {
    $pidPath = Join-Path $runtimeRoot "$name.pid"
    if (-not (Test-Path -LiteralPath $pidPath)) { continue }

    $processId = [int]([System.IO.File]::ReadAllText($pidPath).Trim())
    $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $processId -Force
    }
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
}

Write-Output 'ChainScope services have been stopped.'

