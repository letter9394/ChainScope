param(
    [Parameter(Mandatory = $true)]
    [string]$ArchivePath
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$clientBin = Join-Path $repositoryRoot '.tools\postgresql-client\postgresql-18.6.0-x86_64-pc-windows-msvc\bin'
$pgRestore = Join-Path $clientBin 'pg_restore.exe'
if (-not (Test-Path -LiteralPath $pgRestore -PathType Leaf)) {
    throw "PostgreSQL pg_restore.exe was not found in $clientBin"
}

$archive = (Resolve-Path -LiteralPath $ArchivePath).Path
$checksumPath = "$archive.sha256"
if (-not (Test-Path -LiteralPath $checksumPath -PathType Leaf)) {
    throw "Checksum file not found: $checksumPath"
}
$checksumLine = (Get-Content -LiteralPath $checksumPath -TotalCount 1).Trim()
if ($checksumLine -notmatch '^([a-fA-F0-9]{64})\s+(.+)$') {
    throw 'Checksum file format is invalid.'
}
$expectedHash = $Matches[1]
$expectedName = $Matches[2]
if ($expectedName -ne (Split-Path -Leaf $archive)) {
    throw 'Checksum filename does not match the archive.'
}
$actualHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash
if ($actualHash -ne $expectedHash) {
    throw 'SHA-256 mismatch. Do not restore this archive.'
}

$listing = @(& $pgRestore --list $archive)
if ($LASTEXITCODE -ne 0 -or $listing.Count -eq 0) {
    throw 'pg_restore could not read the archive catalog.'
}
$tableCount = @($listing | Where-Object { $_ -match '^\d+;.* TABLE public ' }).Count
$dataCount = @($listing | Where-Object { $_ -match '^\d+;.* TABLE DATA public ' }).Count
if ($tableCount -eq 0 -or $dataCount -eq 0) {
    throw 'Archive contains no public tables or table data entries.'
}

& $pgRestore --data-only --file=NUL $archive
if ($LASTEXITCODE -ne 0) {
    throw 'pg_restore could not decompress the table data.'
}

Write-Host "Offline archive check passed: $tableCount tables, $dataCount table-data entries."
Write-Host 'This checks integrity and readability; it is not a full database restore test.'
