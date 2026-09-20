$ErrorActionPreference = 'Stop'

$projectRoot = Split-Path $PSScriptRoot -Parent
$runtimeRoot = Join-Path $projectRoot '.local'
$logRoot = Join-Path $runtimeRoot 'logs'
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$backendRoot = Join-Path $projectRoot 'backend'
$webRoot = Join-Path $projectRoot 'web'
$backendPidPath = Join-Path $runtimeRoot 'backend.pid'
$webPidPath = Join-Path $runtimeRoot 'web.pid'

New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

function Test-LocalPort {
    param([int]$Port)
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $task = $client.ConnectAsync('127.0.0.1', $Port)
        if (-not $task.Wait(600)) {
            $client.Dispose()
            return $false
        }
        $connected = $client.Connected
        $client.Dispose()
        return $connected
    } catch {
        return $false
    }
}

function Get-ListeningProcessId {
    param([int]$Port)
    $connection = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($connection) {
        return [int]$connection.OwningProcess
    }
    return $null
}

if (-not (Test-Path -LiteralPath $python)) {
    throw 'Python environment is missing. Run the setup instructions in README.md first.'
}

if (-not (Test-Path -LiteralPath (Join-Path $webRoot 'node_modules'))) {
    throw 'Web dependencies are missing. Run pnpm install in the web directory first.'
}

if (-not (Test-LocalPort -Port 8000)) {
    $backendProcess = Start-Process -FilePath $python `
        -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') `
        -WorkingDirectory $backendRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logRoot 'backend.stdout.log') `
        -RedirectStandardError (Join-Path $logRoot 'backend.stderr.log')

    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (Test-LocalPort -Port 8000) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-LocalPort -Port 8000)) {
        throw "Backend did not start. See $logRoot\backend.stderr.log"
    }
    $backendPid = Get-ListeningProcessId -Port 8000
    if (-not $backendPid) { $backendPid = $backendProcess.Id }
    [System.IO.File]::WriteAllText($backendPidPath, [string]$backendPid)
}

if (-not (Test-LocalPort -Port 3100)) {
    $pnpm = (Get-Command pnpm -ErrorAction Stop).Source
    $webProcess = Start-Process -FilePath $pnpm -ArgumentList @('dev') `
        -WorkingDirectory $webRoot -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logRoot 'web.stdout.log') `
        -RedirectStandardError (Join-Path $logRoot 'web.stderr.log')

    for ($attempt = 0; $attempt -lt 120; $attempt++) {
        if (Test-LocalPort -Port 3100) { break }
        Start-Sleep -Milliseconds 250
    }
    if (-not (Test-LocalPort -Port 3100)) {
        throw "Web dashboard did not start. See $logRoot\web.stderr.log"
    }
    $webPid = Get-ListeningProcessId -Port 3100
    if (-not $webPid) { $webPid = $webProcess.Id }
    [System.IO.File]::WriteAllText($webPidPath, [string]$webPid)
}

Write-Output 'ChainScope is running at http://localhost:3100'
Write-Output 'API documentation is available at http://localhost:8000/docs'

