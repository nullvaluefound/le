# le

`le` lists directories with file icons, ownership, permissions, modification
times, sizes, recursive depth limits, and JSON export. The Python application
is unchanged by the distribution tooling.

```text
le
le /path/to/directory -portn 3
le . -rn 3 --output-json /path/to/tree.json
```

The path defaults to the current directory. `-n` limits recursion only when
`-r` is present. JSON uses an outer array, absolute directory keys, and
filenames as string values; nested directories retain their child relationships.

## Installation

Download artifacts and `SHA256SUMS` from the
[GitHub Releases page](https://github.com/nullvaluefound/le/releases).
If no release is listed yet, build locally using the instructions below.

### Windows — manual, per user

Download `le-manual-installers.zip` and the matching Windows executable. Extract
the installer scripts, then run:

```powershell
.\install.ps1 -LocalBinary .\le-windows-amd64.exe -ChecksumFile .\SHA256SUMS
```

The default command location is
`%LOCALAPPDATA%\Microsoft\WindowsApps\le.exe`. No administrator access is
required. The installer avoids duplicate user PATH entries and records which
entry, if any, it adds. Open a new terminal after a PATH update.

For an already published release, the script can download and verify it:

```powershell
.\install.ps1 -Version 1.0.0
```

CMD users can run `install.bat` and `uninstall.bat` with the same arguments.
Upgrade by rerunning the installer with a newer verified artifact. Uninstall:

```powershell
.\uninstall.ps1
```

### Linux — manual, per user

```bash
bash install.sh --binary ./le-linux-amd64 --checksum-file ./SHA256SUMS
# Or download an existing published version:
bash install.sh --version 1.0.0
```

This installs `~/.local/bin/le`, with reversible, installer-owned PATH blocks
for Bash/Zsh when needed. No root access is required. Upgrade by rerunning the
installer; remove it with `bash uninstall.sh`.

Optional system-wide manual installation is explicit:

```bash
sudo bash install.sh --system --binary ./le-linux-amd64 --checksum-file ./SHA256SUMS
sudo bash uninstall.sh --system
```

The system target is `/usr/bin/le`. The installer refuses APT-owned or unrelated
executables. It never changes `/usr/bin/ls`.

### Package managers

WinGet package ID: `nullvaluefound.Le`. Debian package name: `le-cli`.
The command on both platforms remains `le`.

These commands become available only after the corresponding publication and,
for WinGet, community approval/indexing:

```powershell
winget install --id nullvaluefound.Le -e
winget upgrade --id nullvaluefound.Le -e
winget uninstall --id nullvaluefound.Le -e
```

```bash
sudo apt update
sudo apt install le-cli
sudo apt upgrade
sudo apt remove le-cli
```

Configure the signed APT repository first, using its independently verified
signing fingerprint as described in [docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).
The signed repository is live at `https://nullvaluefound.github.io/le`.
Its signing fingerprint is `9ECD6CC083C1EE9EF8EDD26240167FE47E9E1C26`.
Production installation and removal are verified on Ubuntu 22.04 and Debian 12.
WinGet manifests are staged; community submission and indexing remain pending.

Debian already has an unrelated `le` text editor. `le-cli` refuses to displace
that package or an unrelated `/usr/bin/le`. They cannot coexist at that path.
A per-user manual installation is separate and requires explicit
`--allow-shadow` if another `le` is already discoverable.

## Options

| Option | Behavior |
|---|---|
| `-r`, `--recurse` | Traverse subdirectories. |
| `-n`, `--depth N` | Limit recursion; root is depth 0. Ignored without `-r`. |
| `-d`, `--only-dirs` | Show directories only. |
| `-p`, `--show-permissions` | Show permissions. |
| `-o`, `--show-owner` | Show ownership. |
| `-s`, `--show-size` | Show file and directory sizes. |
| `-t`, `--show-time` | Show modification times. |
| `--time-zone local\|utc` | Select the time zone for displayed times. |
| `--output-json PATH` | Also save the visible hierarchy as JSON. |
| `-v`, `--version` | Report the application version. |
| `-h`, `--help` | Show help. |

## Build and test

Python 3.10+ is needed for source use and builds. Bundled executables include
Python and Colorama; users do not need to install them separately.

```bash
python -m pip install -r requirements.txt -r packaging/requirements-build.txt
python packaging/generate_manual.py
python packaging/release.py build --version 1.0.0 --output release
python packaging/build_test_fixtures.py
python -m unittest discover -s tests -v
python packaging/release.py checksums release
```

Build each architecture on a matching native runner. AMD64 Windows and Linux
are the initial targets. ARM64 jobs are opt-in and must build and pass smoke
tests before their binaries can be published.

Builds are dynamically linked. Consult each artifact's `.build.json` for its
Python version, source checksum, platform, and conservative glibc baseline.
The local Ubuntu 24.04 build requires glibc 2.39; CI AMD64 Linux builds use
Ubuntu 22.04 (glibc 2.35) and test clean Ubuntu/Debian containers. Windows
manual binaries are tested on Windows 11 and CI Windows runners; WinGet
requires a supported Windows/WinGet installation.

Release configuration, signed repository setup, uninstallation behavior,
key rotation, and publication status are documented in
[docs/DISTRIBUTION.md](docs/DISTRIBUTION.md).

## License

[MIT](LICENSE). Bundled dependencies retain their own licenses.
