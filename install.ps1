[CmdletBinding()]
param(
    [Alias('BinaryPath')][string]$LocalBinary,
    [string]$ChecksumFile,
    [string]$ExpectedSha256,
    [string]$Version = 'latest',
    [string]$Repository = 'nullvaluefound/le',
    [ValidateSet('amd64','arm64')][string]$Architecture,
    [string]$InstallDir,
    [string]$StateDir,
    [string]$PathStore
)
$ErrorActionPreference = 'Stop'
if (-not $InstallDir) { $InstallDir = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps' }
if (-not $StateDir) { $StateDir = Join-Path $env:LOCALAPPDATA 'le-manual' }
$InstallDir = [IO.Path]::GetFullPath($InstallDir)
$StateDir = [IO.Path]::GetFullPath($StateDir)
$LeTarget = Join-Path $InstallDir 'le.exe'
$LeRecord = Join-Path $StateDir 'ownership.json'
function Get-LeHash([string] $Path) {
    $algorithm = [Security.Cryptography.SHA256]::Create()
    $stream = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant() }
    finally { $stream.Dispose(); $algorithm.Dispose() }
}
function Get-LeCanonicalPath([string] $Value) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return '' }
    return [Environment]::ExpandEnvironmentVariables($Value.Trim().Trim('"')).TrimEnd('\','/').ToLowerInvariant()
}
function Get-LeUserPath {
    if ($PathStore) {
        if ([IO.File]::Exists($PathStore)) { return [IO.File]::ReadAllText($PathStore) }
        return ''
    }
    return [Environment]::GetEnvironmentVariable('Path', 'User')
}
function Set-LeUserPath([string] $Value) {
    if ($PathStore) { [IO.File]::WriteAllText($PathStore, $Value); return }
    [Environment]::SetEnvironmentVariable('Path', $Value, 'User')
}
function Test-LePathEntry([string] $Value, [string] $Entry) {
    $canonical = Get-LeCanonicalPath $Entry
    foreach ($part in ($Value -split ';', 0, 'SimpleMatch')) {
        if ((Get-LeCanonicalPath $part) -eq $canonical) { return $true }
    }
    return $false
}
function Test-LeReparsePoint([string] $Path) {
    if (Test-Path -LiteralPath $Path) {
        return ((Get-Item -LiteralPath $Path -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) -ne 0
    }
    return $false
}
function Get-LeOwnership {
    if (Test-LeReparsePoint $StateDir) { throw 'Refusing a symlinked installation record directory.' }
    if (Test-LeReparsePoint $LeRecord) { throw 'Refusing a symlinked ownership record.' }
    if (-not [IO.File]::Exists($LeRecord)) { return $null }
    $record = [IO.File]::ReadAllText($LeRecord) | ConvertFrom-Json
    if ($record.manager -ne 'le-manual-powershell-v1') {
        throw 'This is not a manual installation. For a WinGet installation use winget upgrade/uninstall; it will not be modified here.'
    }
    if ([IO.Path]::GetFullPath($record.executable) -ne $LeTarget -or $record.sha256 -notmatch '^[a-fA-F0-9]{64}$' -or (Get-LeCanonicalPath $record.path_entry) -ne (Get-LeCanonicalPath $InstallDir)) {
        throw 'Ownership record does not match this installation location.'
    }
    return $record
}
function Assert-LeOwnedBinary($Record) {
    if (Test-LeReparsePoint $LeTarget) { throw 'The command is a link, potentially WinGet-managed. Use its package manager instead.' }
    if ([IO.File]::Exists($LeTarget) -and (Get-LeHash $LeTarget) -ne $Record.sha256) {
        throw 'The installed executable was changed. Preserving it instead of overwriting or deleting it.'
    }
}
function Write-LeAtomic([string] $Destination, [byte[]] $Bytes) {
    $parent = [IO.Path]::GetDirectoryName($Destination)
    [IO.Directory]::CreateDirectory($parent) | Out-Null
    $temporary = Join-Path $parent ('.le-write-' + [Guid]::NewGuid().ToString('N'))
    try {
        [IO.File]::WriteAllBytes($temporary, $Bytes)
        if ([IO.File]::Exists($Destination)) { [IO.File]::Replace($temporary, $Destination, [NullString]::Value) }
        else { [IO.File]::Move($temporary, $Destination) }
    } finally { if ([IO.File]::Exists($temporary)) { [IO.File]::Delete($temporary) } }
}
function Get-LeVersion([string] $Executable) {
    $output = & $Executable --version 2>&1
    if ($LASTEXITCODE -ne 0 -or -not $output) { throw 'The executable failed its --version smoke test.' }
    return ($output -join "`n").Trim()
}
function Get-LeArchitecture {
    $native = if ($env:PROCESSOR_ARCHITEW6432) { $env:PROCESSOR_ARCHITEW6432 } else { $env:PROCESSOR_ARCHITECTURE }
    switch ($native.ToUpperInvariant()) { 'AMD64' { return 'amd64' }; 'ARM64' { return 'arm64' }; default { throw "Unsupported architecture: $native" } }
}
function Assert-LePE([string] $Path, [string] $Architecture) {
    $bytes = [IO.File]::ReadAllBytes($Path)
    if ($bytes.Length -lt 64 -or $bytes[0] -ne 77 -or $bytes[1] -ne 90) { throw 'Artifact is not a Windows PE executable.' }
    $offset = [BitConverter]::ToInt32($bytes, 60)
    if ($offset -lt 0 -or $offset + 6 -gt $bytes.Length -or [BitConverter]::ToUInt32($bytes, $offset) -ne 17744) { throw 'Invalid PE header.' }
    $machine = [BitConverter]::ToUInt16($bytes, $offset + 4)
    $expected = if ($Architecture -eq 'amd64') { 34404 } else { 43620 }
    if ($machine -ne $expected) { throw 'Release artifact architecture does not match the requested architecture.' }
}
function Remove-LeEmptyDirectory([string] $Path) {
    if ([IO.Directory]::Exists($Path) -and -not (Test-LeReparsePoint $Path)) {
        try { [IO.Directory]::Delete($Path, $false) } catch [IO.IOException] { }
    }
}

$work = Join-Path ([IO.Path]::GetTempPath()) ('le-install-' + [Guid]::NewGuid().ToString('N'))
$oldRecord = $null
$previousBinary = $null
$previousRecord = $null
$previousPath = Get-LeUserPath
$started = $false
$installDirExisted = [IO.Directory]::Exists($InstallDir)
$stateDirExisted = [IO.Directory]::Exists($StateDir)
try {
    $oldRecord = Get-LeOwnership
    if ($oldRecord) { Assert-LeOwnedBinary $oldRecord }
    elseif ((Test-Path -LiteralPath $LeTarget) -or (Test-LeReparsePoint $LeTarget)) {
        throw 'An unrelated le.exe or a WinGet link exists at the target. Use WinGet for WinGet-managed installs; nothing was overwritten.'
    }
    if (-not $Architecture) { $Architecture = Get-LeArchitecture }
    [IO.Directory]::CreateDirectory($work) | Out-Null
    if (-not $LocalBinary) {
        if ($Repository -notmatch '^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$') { throw 'Repository must be OWNER/REPO.' }
        if ($Version -eq 'latest') { $baseUrl = "https://github.com/$Repository/releases/latest/download" }
        else {
            if ($Version -notmatch '^v?\d+\.\d+\.\d+([-+][A-Za-z0-9.-]+)?$') { throw 'Invalid release version.' }
            $baseUrl = "https://github.com/$Repository/releases/download/v$($Version.TrimStart('v'))"
        }
        $LocalBinary = Join-Path $work "le-windows-$Architecture.exe"
        $ChecksumFile = Join-Path $work 'SHA256SUMS'
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/le-windows-$Architecture.exe" -OutFile $LocalBinary
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/SHA256SUMS" -OutFile $ChecksumFile
    }
    $LocalBinary = [IO.Path]::GetFullPath($LocalBinary)
    if (-not [IO.File]::Exists($LocalBinary)) { throw 'Local executable not found.' }
    if (-not $ExpectedSha256 -and $ChecksumFile) {
        $checksumEntries = @()
        foreach ($line in [IO.File]::ReadAllLines([IO.Path]::GetFullPath($ChecksumFile))) {
            if ($line -match '^([a-fA-F0-9]{64})\s+\*?(.+)$' -and $Matches[2] -ceq [IO.Path]::GetFileName($LocalBinary)) { $checksumEntries += $Matches[1] }
        }
        if ($checksumEntries.Count -ne 1) { throw 'Checksum file must contain exactly one matching artifact entry.' }
        $ExpectedSha256 = $checksumEntries[0]
    }
    if ($ExpectedSha256 -notmatch '^[a-fA-F0-9]{64}$') { throw 'A local artifact requires -ChecksumFile or -ExpectedSha256.' }
    $actualHash = Get-LeHash $LocalBinary
    if ($actualHash -ne $ExpectedSha256.ToLowerInvariant()) { throw 'SHA-256 verification failed.' }
    Assert-LePE $LocalBinary $Architecture
    $reported = Get-LeVersion $LocalBinary
    if ([IO.File]::Exists($LeTarget)) { $previousBinary = [IO.File]::ReadAllBytes($LeTarget) }
    if ([IO.File]::Exists($LeRecord)) { $previousRecord = [IO.File]::ReadAllBytes($LeRecord) }
    if ((Test-Path -LiteralPath $StateDir) -and -not $oldRecord -and (Get-ChildItem -LiteralPath $StateDir -Force | Select-Object -First 1)) {
        throw 'The state directory contains unrelated data and no ownership record.'
    }
    $started = $true
    Write-LeAtomic $LeTarget ([IO.File]::ReadAllBytes($LocalBinary))
    $installedVersion = Get-LeVersion $LeTarget
    if ($installedVersion -ne $reported) { throw 'Installed version differs from the verified candidate.' }
    $pathAdded = if ($oldRecord) { [bool]$oldRecord.path_added } else { $false }
    if (-not (Test-LePathEntry $previousPath $InstallDir)) {
        $updated = if ([string]::IsNullOrEmpty($previousPath)) { $InstallDir } else { $previousPath + ';' + $InstallDir }
        Set-LeUserPath $updated
        $pathAdded = $true
    }
    $commandDirectoryCreated = if ($oldRecord) { [bool]$oldRecord.install_dir_created } else { -not $installDirExisted }
    $stateDirectoryCreated = if ($oldRecord) { [bool]$oldRecord.state_dir_created } else { -not $stateDirExisted }
    $record = [ordered]@{ manager='le-manual-powershell-v1'; executable=$LeTarget; sha256=$actualHash; version=$reported; path_added=$pathAdded; path_entry=$InstallDir; install_dir_created=$commandDirectoryCreated; state_dir_created=$stateDirectoryCreated }
    Write-LeAtomic $LeRecord ([Text.Encoding]::UTF8.GetBytes(($record | ConvertTo-Json)))
    Write-Output "Installed $reported"
    Write-Output "Executable: $LeTarget"
    Write-Output 'Open a new terminal if PATH was updated. Upgrade by rerunning this installer with a newer verified artifact.'
} catch {
    $failure = $_
    if ($started) {
        if ($null -ne $previousBinary) { Write-LeAtomic $LeTarget $previousBinary }
        elseif ([IO.File]::Exists($LeTarget)) { [IO.File]::Delete($LeTarget) }
        if ($null -ne $previousRecord) { Write-LeAtomic $LeRecord $previousRecord }
        elseif ([IO.File]::Exists($LeRecord)) { [IO.File]::Delete($LeRecord) }
        Set-LeUserPath $previousPath
        if (-not $stateDirExisted) { Remove-LeEmptyDirectory $StateDir }
        if (-not $installDirExisted) { Remove-LeEmptyDirectory $InstallDir }
    }
    throw $failure
} finally {
    # Only two known download files and our own temporary directory are removed.
    foreach ($name in @("le-windows-$Architecture.exe", 'SHA256SUMS')) {
        $owned = Join-Path $work $name
        if ([IO.File]::Exists($owned)) { [IO.File]::Delete($owned) }
    }
    Remove-LeEmptyDirectory $work
}
