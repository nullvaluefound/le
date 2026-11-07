# WinGet manifests

The confirmed package identifier is `nullvaluefound.Le`; the installer type is
native `portable`, exposing the command `le`. Official Microsoft schema 1.28.0
files are pinned under `schemas/` for offline validation.

Generate a real submission directory from the published binaries and their
SHA256SUMS, never from a guessed URL/hash:

```powershell
python packaging/release.py winget --version 1.0.0 --artifacts release --output build/winget-submission
python packaging/validate_manifests.py build/winget-submission --winget-client
```

The result is `manifests/n/nullvaluefound/Le/1.0.0/` with the version, installer,
and default-locale YAML files. Only supplied Windows architectures are included.
The GitHub workflow stages this directory; submission to `microsoft/winget-pkgs`
and community approval remain explicit external steps. Do not assume an untagged
local build is already downloadable from a public GitHub Release.
