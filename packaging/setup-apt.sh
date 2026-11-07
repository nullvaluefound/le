#!/usr/bin/env bash
# Explicit repository trust bootstrap; does not install/remove the application.
set -euo pipefail
LE_APT_URL='https://nullvaluefound.github.io/le'
LE_APT_SUITE=stable
LE_APT_FINGERPRINT=''
LE_APT_ROOT=''
LE_APT_REMOVE=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        --url|--suite|--fingerprint|--root)
            [ "$#" -ge 2 ] || { echo "Missing value for $1" >&2; exit 1; }
            case "$1" in --url) LE_APT_URL=$2;; --suite) LE_APT_SUITE=$2;; --fingerprint) LE_APT_FINGERPRINT=$2;; --root) LE_APT_ROOT=$2;; esac
            shift 2;;
        --remove-repository) LE_APT_REMOVE=1; shift;;
        --help) echo 'Usage: sudo bash setup-apt.sh --fingerprint TRUSTED_FULL_FINGERPRINT [--url HTTPS_URL] [--remove-repository]'; exit 0;;
        *) echo "Unknown option: $1" >&2; exit 1;;
    esac
done
if [ -z "$LE_APT_ROOT" ] && [ "$(id -u)" -ne 0 ]; then echo 'Run this repository-configuration operation in an explicitly elevated shell.' >&2; exit 1; fi
if [ -n "$LE_APT_ROOT" ]; then [[ "$LE_APT_ROOT" = /* ]] || { echo '--root must be absolute' >&2; exit 1; }; LE_APT_ROOT=$(readlink -m "$LE_APT_ROOT"); fi
LE_APT_KEY="$LE_APT_ROOT/etc/apt/keyrings/le-archive-keyring.gpg"
LE_APT_SOURCE="$LE_APT_ROOT/etc/apt/sources.list.d/le.sources"
LE_APT_RECORD="$LE_APT_ROOT/etc/apt/le-repository.ownership"
le_apt_hash() { sha256sum "$1" | cut -d ' ' -f1; }
if [ -L "$LE_APT_RECORD" ] || [ -L "$LE_APT_KEY" ] || [ -L "$LE_APT_SOURCE" ]; then echo 'Refusing symlinked repository configuration.' >&2; exit 1; fi
if [ -f "$LE_APT_RECORD" ]; then
    [ "$(sed -n '1p' "$LE_APT_RECORD")" = LE-APT-REPOSITORY-1 ] || { echo 'Unowned repository record' >&2; exit 1; }
    for LE_APT_ENTRY in "$LE_APT_KEY" "$LE_APT_SOURCE"; do
        if [ -f "$LE_APT_ENTRY" ]; then
            LE_APT_EXPECTED=$(if [ "$LE_APT_ENTRY" = "$LE_APT_KEY" ]; then sed -n '2p' "$LE_APT_RECORD"; else sed -n '3p' "$LE_APT_RECORD"; fi)
            [ "$(le_apt_hash "$LE_APT_ENTRY")" = "$LE_APT_EXPECTED" ] || { echo 'Repository configuration was modified; preserving user changes.' >&2; exit 1; }
        fi
    done
elif [ -e "$LE_APT_KEY" ] || [ -e "$LE_APT_SOURCE" ]; then
    echo 'Existing repository files are not owned by this bootstrap; nothing was overwritten.' >&2; exit 1
fi
if [ "$LE_APT_REMOVE" -eq 1 ]; then
    if [ -f "$LE_APT_RECORD" ]; then rm -f -- "$LE_APT_KEY" "$LE_APT_SOURCE" "$LE_APT_RECORD"; fi
    echo 'Removed the owned repository configuration only. Package removal is separate: sudo apt remove le-cli.'
    exit 0
fi
[[ "$LE_APT_URL" =~ ^https://[A-Za-z0-9._:-]+(/[^[:space:]]*)?$ ]] || { echo 'Repository URL must be HTTPS without credentials or whitespace.' >&2; exit 1; }
[[ "$LE_APT_SUITE" =~ ^[a-z][a-z0-9-]*$ ]] || { echo 'Invalid suite.' >&2; exit 1; }
LE_APT_FINGERPRINT=${LE_APT_FINGERPRINT// /}
LE_APT_FINGERPRINT=${LE_APT_FINGERPRINT^^}
[[ "$LE_APT_FINGERPRINT" =~ ^[A-F0-9]{40,64}$ ]] || { echo 'Supply the full independently verified signing-key fingerprint.' >&2; exit 1; }
LE_APT_WORK=$(mktemp -d "${TMPDIR:-/tmp}/le-apt-bootstrap.XXXXXXXX")
trap 'rm -rf -- "$LE_APT_WORK"' EXIT
mkdir -m 700 "$LE_APT_WORK/gpg-home"
export GNUPGHOME="$LE_APT_WORK/gpg-home"
curl --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --location --retry 3 "${LE_APT_URL%/}/keys/$LE_APT_FINGERPRINT.gpg" -o "$LE_APT_WORK/key.gpg"
LE_APT_ACTUAL=$(gpg --batch --show-keys --with-colons "$LE_APT_WORK/key.gpg" 2>/dev/null | awk -F: '$1=="fpr" {print toupper($10); exit}')
[ "$LE_APT_ACTUAL" = "$LE_APT_FINGERPRINT" ] || { echo 'Signing-key fingerprint mismatch; nothing installed.' >&2; exit 1; }
LE_APT_PRIMARY_COUNT=$(gpg --batch --show-keys --with-colons "$LE_APT_WORK/key.gpg" 2>/dev/null | grep -c '^pub:')
[ "$LE_APT_PRIMARY_COUNT" -eq 1 ] || { echo 'The downloaded file must contain only the selected public key.' >&2; exit 1; }
if gpg --batch --list-packets "$LE_APT_WORK/key.gpg" 2>/dev/null | grep -q ':secret'; then echo 'Refusing secret-key material.' >&2; exit 1; fi
printf 'Types: deb\nURIs: %s\nSuites: %s\nComponents: main\nSigned-By: %s\n' "${LE_APT_URL%/}" "$LE_APT_SUITE" "$LE_APT_KEY" > "$LE_APT_WORK/le.sources"
mkdir -p -- "$(dirname "$LE_APT_KEY")" "$(dirname "$LE_APT_SOURCE")"
install -m 644 "$LE_APT_WORK/key.gpg" "$LE_APT_KEY"
install -m 644 "$LE_APT_WORK/le.sources" "$LE_APT_SOURCE"
printf 'LE-APT-REPOSITORY-1\n%s\n%s\n' "$(le_apt_hash "$LE_APT_KEY")" "$(le_apt_hash "$LE_APT_SOURCE")" > "$LE_APT_RECORD"
chmod 644 "$LE_APT_RECORD"
printf 'Configured the signed le repository. Next: sudo apt update && sudo apt install le-cli\n'
