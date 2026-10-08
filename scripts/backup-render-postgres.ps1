param(
    [string]$OutputDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Codex\ChainScope-Backups')
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$clientBin = Join-Path $repositoryRoot '.tools\postgresql-client\postgresql-18.6.0-x86_64-pc-windows-msvc\bin'
$pgDump = Join-Path $clientBin 'pg_dump.exe'
$pgRestore = Join-Path $clientBin 'pg_restore.exe'

if (-not (Test-Path -LiteralPath $pgDump -PathType Leaf) -or -not (Test-Path -LiteralPath $pgRestore -PathType Leaf)) {
    throw "PostgreSQL 18 client tools were not found in $clientBin"
}

$secureUrl = Read-Host -Prompt 'Paste Render External Database URL (hidden input)' -AsSecureString
$bstr = [IntPtr]::Zero
$connectionUrl = $null
$password = $null
$previousPassword = [Environment]::GetEnvironmentVariable('PGPASSWORD', 'Process')
$previousSslMode = [Environment]::GetEnvironmentVariable('PGSSLMODE', 'Process')
$previousConnectTimeout = [Environment]::GetEnvironmentVariable('PGCONNECT_TIMEOUT', 'Process')

try {
    $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureUrl)
    $connectionUrl = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
    if ([string]::IsNullOrWhiteSpace($connectionUrl)) {
        throw 'No database URL was entered.'
    }

    $uri = [Uri]$connectionUrl
    if ($uri.Scheme -notin @('postgres', 'postgresql') -or [string]::IsNullOrWhiteSpace($uri.Host)) {
        throw 'Enter a valid PostgreSQL External Database URL from Render.'
    }
    if ($uri.UserInfo -notmatch '^([^:]+):(.+)$') {
        throw 'The URL must include both a database user and password.'
    }

    $databaseUser = [Uri]::UnescapeDataString($Matches[1])
    $password = [Uri]::UnescapeDataString($Matches[2])
    $databaseName = [Uri]::UnescapeDataString($uri.AbsolutePath.TrimStart('/'))
    if ([string]::IsNullOrWhiteSpace($databaseName)) {
        throw 'The URL does not contain a database name.'
    }
    $databasePort = if ($uri.IsDefaultPort) { 5432 } else { $uri.Port }

    $connectionUrl = $null
    [Environment]::SetEnvironmentVariable('PGPASSWORD', $password, 'Process')
    [Environment]::SetEnvironmentVariable('PGSSLMODE', 'require', 'Process')
    [Environment]::SetEnvironmentVariable('PGCONNECT_TIMEOUT', '20', 'Process')
    $password = $null

    New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $archive = Join-Path $OutputDirectory "chainscope-db-$timestamp.dump"

    Write-Host "Creating complete database dump: $archive"
    & $pgDump --host=$($uri.Host) --port=$databasePort --username=$databaseUser --dbname=$databaseName --format=custom --file=$archive
    if ($LASTEXITCODE -ne 0) {
        $dumpExitCode = $LASTEXITCODE
        if ((Test-Path -LiteralPath $archive -PathType Leaf) -and (Get-Item -LiteralPath $archive).Length -eq 0) {
            Remove-Item -LiteralPath $archive
        }
        throw "pg_dump failed with exit code $dumpExitCode. No valid backup was created."
    }

    $listing = & $pgRestore --list $archive
    if ($LASTEXITCODE -ne 0 -or @($listing).Count -eq 0) {
        throw 'The archive failed the pg_restore contents check.'
    }

    $file = Get-Item -LiteralPath $archive
    $hash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumPath = "$archive.sha256"
    Set-Content -LiteralPath $checksumPath -Value "$hash  $($file.Name)" -Encoding ascii

    & (Join-Path $PSScriptRoot 'verify-postgres-backup.ps1') -ArchivePath $archive

    Write-Host "Backup verified (archive contents readable): $($file.Length) bytes"
    Write-Host "SHA-256: $hash"
    Write-Host "Archive: $archive"
    Write-Host "Checksum: $checksumPath"
    Write-Host 'Now remove your temporary IP allowlist rule in Render.'
}
finally {
    if ($bstr -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
    }
    [Environment]::SetEnvironmentVariable('PGPASSWORD', $previousPassword, 'Process')
    [Environment]::SetEnvironmentVariable('PGSSLMODE', $previousSslMode, 'Process')
    [Environment]::SetEnvironmentVariable('PGCONNECT_TIMEOUT', $previousConnectTimeout, 'Process')
    $connectionUrl = $null
    $password = $null
}
