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
# COMMON
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
