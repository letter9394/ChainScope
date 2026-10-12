param(
    [string]$Repository = 'letter9394/ChainScope',
    [string]$BackupDirectory = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'Codex\ChainScope-Backups')
)

$ErrorActionPreference = 'Stop'

if ($Repository -ne 'letter9394/ChainScope') {
    throw 'This helper is restricted to the expected ChainScope GitHub repository.'
}

$gh = (Get-Command gh.exe -ErrorAction Stop).Source
$keyPath = Join-Path $BackupDirectory 'chainscope-github-backup-key.dpapi'

function Get-HiddenText {
    param([string]$Prompt)

    $secure = Read-Host -Prompt $Prompt -AsSecureString
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) {
            [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
        }
    }
}

function Set-GitHubActionSecret {
    param([string]$Name, [string]$Value)

    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $gh
    $start.Arguments = "secret set $Name -R $Repository --app actions"
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardInput = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $process = [Diagnostics.Process]::Start($start)
    try {
        $process.StandardInput.Write($Value)
        $process.StandardInput.Close()
        if (-not $process.WaitForExit(45000)) {
            $process.Kill()
            throw "Setting $Name timed out. No value was printed."
        }
        if ($process.ExitCode -ne 0) {
            throw "Setting $Name failed. No value or CLI diagnostics were printed."
        }
    }
    finally {
        $process.Dispose()
    }
}

$sourceUrl = Get-HiddenText 'Paste the Render EXTERNAL Database URL (hidden; never paste it in chat)'
try {
    if ([string]::IsNullOrWhiteSpace($sourceUrl)) {
        throw 'No Render URL was entered.'
    }
    $uri = [Uri]$sourceUrl
    if ($uri.Scheme -notin @('postgres', 'postgresql') -or
        $uri.Host -ne 'dpg-daoet2ad0e5s73808crg-a.singapore-postgres.render.com' -or
        [Uri]::UnescapeDataString($uri.AbsolutePath) -ne '/chainscope' -or
        [Uri]::UnescapeDataString($uri.UserInfo.Split(':', 2)[0]) -ne 'chainscope' -or
        $uri.UserInfo -notlike '*:*') {
        throw 'This URL does not identify the expected Render source database.'
    }

    New-Item -ItemType Directory -Path $BackupDirectory -Force | Out-Null
    if (Test-Path -LiteralPath $keyPath -PathType Leaf) {
        $protected = [IO.File]::ReadAllBytes($keyPath)
        $key = [Security.Cryptography.ProtectedData]::Unprotect(
            $protected, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        if ($key.Length -ne 32) {
            throw 'The existing local backup key has an invalid length.'
        }
    }
    else {
        $key = New-Object byte[] 32
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        try { $generator.GetBytes($key) } finally { $generator.Dispose() }
        $protected = [Security.Cryptography.ProtectedData]::Protect(
            $key, $null, [Security.Cryptography.DataProtectionScope]::CurrentUser)
        [IO.File]::WriteAllBytes($keyPath, $protected)
    }

    $keyBase64 = [Convert]::ToBase64String($key)
    Set-GitHubActionSecret -Name 'CHAINSCOPE_MIGRATION_KEY_B64' -Value $keyBase64
    Set-GitHubActionSecret -Name 'CHAINSCOPE_MIGRATION_RENDER_URL' -Value $sourceUrl
    Write-Host 'GitHub Actions backup secrets configured. No secret values were displayed.'
    Write-Host "The backup decryption key is DPAPI-protected in: $keyPath"
    Write-Host 'Keep that file and this Windows user profile until the encrypted backup is downloaded and verified.'
}
finally {
    if ($key) { [Array]::Clear($key, 0, $key.Length) }
    $keyBase64 = $null
    $sourceUrl = $null
}
