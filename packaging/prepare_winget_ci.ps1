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
    # Registering the runner's old provisioned bundle fails on Server 2025.
    # Install the official signed bundle directly with its matching dependencies.
    $downloadRoot = Join-Path $env:RUNNER_TEMP ('le-winget-bootstrap-' + [Guid]::NewGuid().ToString('N'))
    [IO.Directory]::CreateDirectory($downloadRoot) | Out-Null
    $assets = @{
        'DesktopAppInstaller_Dependencies.zip' = 'ba875afe9d190f61218985ac0292a99d1db710bf93e13c68944ca9d89f0d82d1'
        'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle' = '65dea9c01ce08ee7b763366b27c0e651f97db857c11ca9b9c301826c10092f2e'
    }
    foreach ($name in $assets.Keys) {
        $destination = Join-Path $downloadRoot $name
        Invoke-WebRequest -UseBasicParsing -Uri ("https://github.com/microsoft/winget-cli/releases/download/v$requiredVersion/$name") -OutFile $destination
        if ((Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash.ToLowerInvariant() -ne $assets[$name]) {
            throw "Official WinGet bootstrap checksum mismatch: $name"
        }
    }
    Expand-Archive -LiteralPath (Join-Path $downloadRoot 'DesktopAppInstaller_Dependencies.zip') -DestinationPath (Join-Path $downloadRoot 'dependencies')
    $architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString().ToLowerInvariant()
    $dependencies = @(Get-ChildItem -LiteralPath (Join-Path $downloadRoot "dependencies/$architecture") -Filter '*.appx' | ForEach-Object { $_.FullName })
    Add-AppxPackage -Path (Join-Path $downloadRoot 'Microsoft.DesktopAppInstaller_8wekyb3d8bbwe.msixbundle') -DependencyPath $dependencies -ForceApplicationShutdown
    $windowsApps = Join-Path $env:LOCALAPPDATA 'Microsoft\WindowsApps'
    if (($env:PATH -split ';') -notcontains $windowsApps) {
        # Preserve setup-python's priority over the Microsoft Store Python aliases.
        $env:PATH += ';' + $windowsApps
        Add-Content -LiteralPath $env:GITHUB_ENV -Value ('PATH=' + $env:PATH) -Encoding utf8
    }
}
winget --version
if ($LASTEXITCODE -ne 0) { throw 'WinGet bootstrap did not provide a working client.' }
$actualVersion = [version]((& winget --version | Out-String).Trim().TrimStart('v'))
if ($actualVersion -lt $requiredVersion) { throw "WinGet $requiredVersion or newer is required." }
