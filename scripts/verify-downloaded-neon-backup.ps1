param(
    [Parameter(Mandatory = $true)]
    [string]$EncryptedPath,
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [string]$BackupDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Codex\ChainScope-Backups'),
    [switch]$KeyFromPrompt
)

$ErrorActionPreference = 'Stop'

$encrypted = (Resolve-Path -LiteralPath $EncryptedPath).Path
$manifest = (Resolve-Path -LiteralPath $ManifestPath).Path
if (-not $KeyFromPrompt) {
    Add-Type -AssemblyName System.Security
    $keyPath = Join-Path $BackupDirectory 'chainscope-github-backup-key.dpapi'
    if (-not (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
        throw 'The local DPAPI-protected backup key was not found. Use -KeyFromPrompt with a separately saved key.'
    }
}
$nodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
if ($nodeCommand) {
    $node = $nodeCommand.Source
}
else {
    # Codex bundles Node, but it may not be on the user's ordinary PowerShell PATH.
    $bundledNode = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    if (-not (Test-Path -LiteralPath $bundledNode -PathType Leaf)) {
        throw 'Node.js was not found on PATH or in the local Codex runtime. No backup was changed.'
    }
    $node = $bundledNode
}
$powerShell = (Get-Command powershell.exe -ErrorAction Stop).Source
$temporaryArchive = Join-Path ([IO.Path]::GetTempPath()) ('chainscope-neon-verify-' + [Guid]::NewGuid().ToString('N') + '.dump')
$temporaryChecksum = "$temporaryArchive.sha256"
$keyBytes = $null
$keyBase64 = $null
$secure = $null
$bstr = [IntPtr]::Zero
try {
    if ($KeyFromPrompt) {
        Add-Type -AssemblyName System.Windows.Forms
        Write-Host 'Copy the backup key from your password manager, then paste at the hidden prompt.'
        Write-Host 'Do not paste the key into a command, chat, or screenshot.'
        $secure = Read-Host -Prompt 'Paste backup key and press Enter (hidden)' -AsSecureString
        $bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        $keyBase64 = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        $bstr = [IntPtr]::Zero
        if ($keyBase64 -notmatch '^[A-Za-z0-9+/]{43}=$') {
            throw 'The pasted value is not a base64-encoded 32-byte backup key.'
        }
        $keyBytes = [Convert]::FromBase64String($keyBase64)
    }
    else {
        $protected = [IO.File]::ReadAllBytes($keyPath)
        $keyBytes = [Security.Cryptography.ProtectedData]::Unprotect(
            $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser
        )
        $keyBase64 = [Convert]::ToBase64String($keyBytes)
    }
    if ($keyBytes.Length -ne 32) {
        throw 'The backup key has the wrong length.'
    }
    $env:CHAINSCOPE_MIGRATION_KEY_B64 = $keyBase64
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
    if ($KeyFromPrompt) {
        Write-Host 'SEPARATE_KEY_VERIFIED_OK: the supplied key opened this backup without local DPAPI.'
    }
}
finally {
    Remove-Item Env:\CHAINSCOPE_MIGRATION_KEY_B64 -ErrorAction SilentlyContinue
    if ($bstr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr) }
    if ($null -ne $secure) { $secure.Dispose() }
    if ($null -ne $keyBytes) { [Array]::Clear($keyBytes, 0, $keyBytes.Length) }
    if (Test-Path -LiteralPath $temporaryArchive) {
        Remove-Item -LiteralPath $temporaryArchive -Force
    }
    if (Test-Path -LiteralPath $temporaryChecksum) {
        Remove-Item -LiteralPath $temporaryChecksum -Force
    }
    if ($KeyFromPrompt -and $null -ne $keyBase64) {
        try {
            if ([System.Windows.Forms.Clipboard]::ContainsText() -and
                [System.Windows.Forms.Clipboard]::GetText() -ceq $keyBase64) {
                [System.Windows.Forms.Clipboard]::Clear()
                Write-Host 'CLIPBOARD_CLEARED'
            }
        }
        catch {
            Write-Warning 'Could not clear the clipboard automatically. Copy a harmless word now to replace it.'
        }
    }
}
