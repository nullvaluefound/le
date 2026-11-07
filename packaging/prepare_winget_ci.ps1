[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
if ($env:CI -ne 'true' -or -not $env:RUNNER_TEMP) {
    throw 'This bootstrap is only for disposable GitHub Actions runners.'
}
# Pinned official client supports the vendored manifest schema 1.28.0.
$requiredVersion = [version]'1.29.380'
$installedVersion = [version]'0.0'
if (Get-Command winget -ErrorAction SilentlyContinue) {
    $versionText = (& winget --version | Out-String).Trim().TrimStart('v')
    if ($LASTEXITCODE -eq 0) { $installedVersion = [version]$versionText }
}
if ($installedVersion -lt $requiredVersion) {
    Install-Module -Name Microsoft.WinGet.Client -RequiredVersion $requiredVersion.ToString() -Scope CurrentUser -Repository PSGallery -Force -AllowClobber
    Import-Module Microsoft.WinGet.Client -RequiredVersion $requiredVersion.ToString()
    Repair-WinGetPackageManager -AllUsers -Force -Version $requiredVersion.ToString()
}
winget --version
if ($LASTEXITCODE -ne 0) { throw 'WinGet bootstrap did not provide a working client.' }
$actualVersion = [version]((& winget --version | Out-String).Trim().TrimStart('v'))
if ($actualVersion -lt $requiredVersion) { throw "WinGet $requiredVersion or newer is required." }
