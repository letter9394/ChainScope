param(
    [Parameter(Mandatory = $true)]
    [string]$EncryptedPath,
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$BackupDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Codex\ChainScope-Backups')
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Security

$encrypted = (Resolve-Path -LiteralPath $EncryptedPath).Path
$manifest = (Resolve-Path -LiteralPath $ManifestPath).Path
$keyPath = Join-Path $BackupDirectory 'chainscope-github-backup-key.dpapi'
if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
    throw 'The local DPAPI-protected backup key was not found.'
}
$node = (Get-Command node.exe -ErrorAction Stop).Source
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$temporaryArchive = Join-Path ([IO.Path]::GetTempPath()) ('chainscope-neon-verify-' + [Guid]::NewGuid().ToString('N') + '.dump')
$temporaryChecksum = "$temporaryArchive.sha256"
$keyBytes = $null
try {
    $protected = [IO.File]::ReadAllBytes($keyPath)
    $keyBytes = [Security.Cryptography.ProtectedData]::Unprotect(
        $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
    )
    if ($keyBytes.Length -ne 32) {
        throw 'The local backup key has the wrong length.'
    }
    $env:CHAINSCOPE_MIGRATION_KEY_B64 = [Convert]::ToBase64String($keyBytes)
    & $node (Join-Path $PSScriptRoot 'decrypt-neon-backup.mjs') $encrypted $manifest $temporaryArchive
    if ($LASTEXITCODE -ne 0) {
        throw 'The encrypted Neon archive failed authentication or checksum verification.'
    }
    Remove-Item Env:\CHAINSCOPE_MIGRATION_KEY_B64 -ErrorAction SilentlyContinue
    & $powerShell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'verify-postgres-backup.ps1') -ArchivePath $temporaryArchive
    if ($LASTEXITCODE -ne 0) {
        throw 'The decrypted Neon archive failed the offline PostgreSQL check.'
    }
    Write-Host 'VERIFIED_OK: encrypted Neon artifact authenticated and PostgreSQL archive fully read.'
}
finally {
    Remove-Item Env:\CHAINSCOPE_MIGRATION_KEY_B64 -ErrorAction SilentlyContinue
    if ($null -ne $keyBytes) { [Array]::Clear($keyBytes, 0, $keyBytes.Length) }
    if (Test-Path -LiteralPath $temporaryArchive) {
        Remove-Item -LiteralPath $temporaryArchive -Force
    }
    if (Test-Path -LiteralPath $temporaryChecksum) {
        Remove-Item -LiteralPath $temporaryChecksum -Force
    }
}
