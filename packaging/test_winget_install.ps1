[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$ManifestRoot,
    [Parameter(Mandatory=$true)][string]$ArtifactDirectory,
    [string]$PackageIdentifier = 'LeDistributionTests.Le',
    [switch]$UsePublishedDownloads
)
$ErrorActionPreference = 'Stop'
if ($env:CI -ne 'true' -or -not $env:RUNNER_TEMP) { throw 'Run this test only in a disposable CI Windows runner, never the developer installation.' }
if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw 'WinGet client not installed.' }
$manifestFiles = @(Get-ChildItem -LiteralPath $ManifestRoot -Filter '*.yaml' -Recurse)
if ($manifestFiles.Count -ne 3) { throw 'Expected one complete manifest set.' }
$testRoot = Join-Path $env:RUNNER_TEMP ('le-winget-test-' + [Guid]::NewGuid().ToString('N'))
$localManifests = Join-Path $testRoot 'manifests'
[IO.Directory]::CreateDirectory($localManifests) | Out-Null
$identifier = $PackageIdentifier
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start(); $port = $listener.LocalEndpoint.Port; $listener.Stop()
$server = $null
try {
    foreach ($manifest in $manifestFiles) {
        $text = [IO.File]::ReadAllText($manifest.FullName)
        if (-not $UsePublishedDownloads) {
            $text = [regex]::Replace($text, 'InstallerUrl: https://[^\r\n]+/([^/\r\n]+)', ('InstallerUrl: http://127.0.0.1:' + $port + '/$1'))
        }
        [IO.File]::WriteAllText((Join-Path $localManifests $manifest.Name), $text, [Text.UTF8Encoding]::new($false))
    }
    if (-not $UsePublishedDownloads) {
        $server = Start-Process -FilePath (Get-Command python).Source -ArgumentList @('-m','http.server',"$port",'--bind','127.0.0.1','--directory',('"' + [IO.Path]::GetFullPath($ArtifactDirectory) + '"')) -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $testRoot 'http.out') -RedirectStandardError (Join-Path $testRoot 'http.err')
        $ready = $false
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            try { Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$port/" | Out-Null; $ready = $true; break } catch { Start-Sleep -Milliseconds 200 }
        }
        if (-not $ready) { throw 'Local fixture download server did not start.' }
    }
    winget settings --enable LocalManifestFiles
    if ($LASTEXITCODE -ne 0) { throw 'Could not enable local manifests in the disposable runner.' }
    winget validate --manifest $localManifests --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'Local fixture manifest validation failed.' }
    winget install --manifest $localManifests --scope user --location (Join-Path $testRoot 'portable') --accept-package-agreements --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'WinGet local portable installation failed.' }
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = 'powershell.exe'
    $start.Arguments = '-NoProfile -NonInteractive -Command "le --version"'
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.EnvironmentVariables['PATH'] = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
    $child = [Diagnostics.Process]::Start($start)
    $result = $child.StandardOutput.ReadToEnd()
    $errorText = $child.StandardError.ReadToEnd()
    $child.WaitForExit()
    if ($child.ExitCode -ne 0 -or $result -notmatch '\d+\.\d+') { throw "Fresh-shell le command failed: $errorText" }
    Write-Output $result
    # Local manifests are not indexed by a public source, so their package ID
    # cannot be resolved there. Use the portable registration's product code,
    # just as WinGet's own registered UninstallString does.
    $registrations = @(Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*' |
        Where-Object { $_.WinGetPackageIdentifier -eq $identifier })
    if ($registrations.Count -ne 1) { throw 'Expected one registered local portable package.' }
    winget uninstall --product-code $registrations[0].PSChildName --silent --accept-source-agreements --disable-interactivity
    if ($LASTEXITCODE -ne 0) { throw 'WinGet uninstallation failed.' }
    if (Test-Path -LiteralPath $registrations[0].PSPath) { throw 'WinGet left the package registered after removal.' }
    Write-Output 'WinGet portable install, fresh-shell command, and uninstallation passed.'
} finally {
    if ($server -and -not $server.HasExited) { Stop-Process -Id $server.Id -ErrorAction SilentlyContinue }
    # The runner is disposable. WinGet owns any failed partial package cleanup.
}
