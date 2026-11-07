[CmdletBinding()]
param([string]$InstallDir, [string]$StateDir, [string]$PathStore)
# COMMON
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
