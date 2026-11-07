[CmdletBinding()]
param([string]$InstallDir, [string]$StateDir, [string]$PathStore)
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

$record = Get-LeOwnership
if (-not $record) {
    Write-Output 'No manual le installation record found; nothing was removed. Use winget uninstall for a WinGet-managed installation.'
    exit 0
}
Assert-LeOwnedBinary $record
$oldPath = Get-LeUserPath
if ($record.path_added) {
    $entryRemoved = $false
    $parts = [Collections.Generic.List[string]]::new()
    foreach ($part in ($oldPath -split ';', 0, 'SimpleMatch')) { $parts.Add($part) }
    for ($index = $parts.Count - 1; $index -ge 0; $index--) {
        if ((Get-LeCanonicalPath $parts[$index]) -eq (Get-LeCanonicalPath $record.path_entry)) {
            $parts.RemoveAt($index)
            $entryRemoved = $true
            break
        }
    }
    if ($entryRemoved) { Set-LeUserPath ($parts -join ';') }
}
try {
    if ([IO.File]::Exists($LeTarget)) { [IO.File]::Delete($LeTarget) }
} catch { Set-LeUserPath $oldPath; throw }
[IO.File]::Delete($LeRecord)
if ($record.state_dir_created) { Remove-LeEmptyDirectory $StateDir }
# WindowsApps is shared; only remove an installer-created custom directory if empty.
if ($record.install_dir_created -and $InstallDir -ne (Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps')) { Remove-LeEmptyDirectory $InstallDir }
Write-Output 'Removed the manual le installation. Unrelated user files and PATH entries were preserved.'
