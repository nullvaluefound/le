set -euo pipefail
LE_MARK_START='# >>> le manual installer PATH >>>'
LE_MARK_END='# <<< le manual installer PATH <<<'
LE_HOME_DIR="$HOME"
LE_BIN_DIR=''
LE_STATE_DIR=''
LE_BINARY=''
LE_CHECKSUM_FILE=''
LE_EXPECTED_SHA=''
LE_REPOSITORY="${LE_GITHUB_REPOSITORY:-nullvaluefound/le}"
LE_VERSION='latest'
LE_SYSTEM=0
LE_ALLOW_SHADOW=0
LE_WORK=''
le_fail() { printf 'le: %s\n' "$*" >&2; exit 1; }
le_usage() {
    printf '%s\n' 'Options: --binary PATH --checksum-file PATH | --sha256 HASH; --repo OWNER/REPO; --version VERSION; --bin-dir PATH; --state-dir PATH; --home-dir PATH; --system; --allow-shadow'
}
while [ "$#" -gt 0 ]; do
    case "$1" in
        --binary|--checksum-file|--sha256|--repo|--version|--bin-dir|--state-dir|--home-dir)
            [ "$#" -ge 2 ] || le_fail "Missing value for $1"
            case "$1" in
                --binary) LE_BINARY=$2;; --checksum-file) LE_CHECKSUM_FILE=$2;;
                --sha256) LE_EXPECTED_SHA=$2;; --repo) LE_REPOSITORY=$2;;
                --version) LE_VERSION=$2;; --bin-dir) LE_BIN_DIR=$2;;
                --state-dir) LE_STATE_DIR=$2;; --home-dir) LE_HOME_DIR=$2;;
            esac; shift 2;;
        --system) LE_SYSTEM=1; shift;;
        --allow-shadow) LE_ALLOW_SHADOW=1; shift;;
        --help|-h) le_usage; exit 0;;
        *) le_fail "Unknown option: $1";;
    esac
done
if [ "$LE_SYSTEM" -eq 1 ]; then
    [ "$(id -u)" -eq 0 ] || le_fail 'System installation requires an explicitly elevated shell; use sudo bash install.sh --system.'
    LE_BIN_DIR=${LE_BIN_DIR:-/usr/bin}
    LE_STATE_DIR=${LE_STATE_DIR:-/var/lib/le-manual}
else
    LE_BIN_DIR=${LE_BIN_DIR:-$LE_HOME_DIR/.local/bin}
    LE_STATE_DIR=${LE_STATE_DIR:-${XDG_STATE_HOME:-$LE_HOME_DIR/.local/state}/le}
fi
for LE_VALUE in "$LE_HOME_DIR" "$LE_BIN_DIR" "$LE_STATE_DIR"; do
    case "$LE_VALUE" in *$'\n'*|*$'\r'*|*$'\t'*) le_fail 'Installation paths must not contain newlines or tabs.';; esac
    [[ "$LE_VALUE" = /* ]] || le_fail 'Installation paths must be absolute.'
done
LE_HOME_DIR=$(readlink -m -- "$LE_HOME_DIR")
LE_BIN_DIR=$(readlink -m -- "$LE_BIN_DIR")
LE_STATE_DIR=$(readlink -m -- "$LE_STATE_DIR")
LE_TARGET="$LE_BIN_DIR/le"
LE_RECORD="$LE_STATE_DIR/ownership"
le_hash() { sha256sum -- "$1" | cut -d ' ' -f 1; }
le_field() { sed -n "${1}p" "$LE_RECORD"; }
le_apt_guard() {
    if command -v dpkg-query >/dev/null 2>&1 && dpkg-query -S "$LE_TARGET" >/dev/null 2>&1; then
        le_fail 'That executable is APT/dpkg-managed. Use apt upgrade/remove le-cli (or keep the unrelated le editor); the manual installer will not modify it.'
    fi
}
le_read_record() {
    [ ! -L "$LE_RECORD" ] && [ ! -L "$LE_STATE_DIR" ] || le_fail 'Refusing a symlinked installation record.'
    [ -f "$LE_RECORD" ] || return 1
    [ "$(le_field 1)" = 'LE-MANUAL-BASH-1' ] || le_fail 'This installation is not owned by the Bash installer.'
    [ "$(le_field 2)" = "$LE_TARGET" ] || le_fail 'Installation record does not match --bin-dir.'
    [[ "$(le_field 3)" =~ ^[a-fA-F0-9]{64}$ ]] || le_fail 'Invalid ownership checksum.'
}
le_verify_owned_binary() {
    [ ! -L "$LE_TARGET" ] || le_fail 'Refusing to replace or remove a symlink.'
    if [ -e "$LE_TARGET" ]; then
        [ -f "$LE_TARGET" ] || le_fail 'The command path is not a file.'
        [ "$(le_hash "$LE_TARGET")" = "$(le_field 3)" ] || le_fail 'The installed executable was changed; preserving it.'
    fi
}
le_new_work() {
    LE_WORK=$(mktemp -d "${TMPDIR:-/tmp}/le-install.XXXXXXXX")
    trap 'if [ -n "$LE_WORK" ] && [ -d "$LE_WORK" ]; then rm -rf -- "$LE_WORK"; fi' EXIT
}
le_atomic_copy() {
    local source=$1 destination=$2 mode=$3 temporary
    temporary=$(mktemp "$(dirname "$destination")/.le-write.XXXXXXXX")
    if ! install -m "$mode" -- "$source" "$temporary" || ! mv -f -- "$temporary" "$destination"; then
        rm -f -- "$temporary"; return 1
    fi
}
le_quote() { printf "'%s'" "${1//\'/\'\\\'\'}"; }
le_make_block() {
    {
        printf '\n%s\n' "$LE_MARK_START"
        printf 'case ":$PATH:" in *:'
        le_quote "$LE_BIN_DIR"
        printf ':*) ;; *) export PATH='
        le_quote "$LE_BIN_DIR"
        printf ':"$PATH" ;; esac\n%s\n' "$LE_MARK_END"
    } > "$LE_WORK/path-block"
}
le_block_offsets() {
    local file=$1 start end lines
    lines=$(grep -Fxc -- "$LE_MARK_START" "$file" || true)
    [ "$lines" -eq 1 ] || return 1
    lines=$(grep -Fxc -- "$LE_MARK_END" "$file" || true)
    [ "$lines" -eq 1 ] || return 1
    start=$(grep -n -b -F -x -- "$LE_MARK_START" "$file" | cut -d: -f2)
    end=$(grep -n -b -F -x -- "$LE_MARK_END" "$file" | cut -d: -f2)
    [ "$start" -gt 0 ] && [ "$end" -gt "$start" ] || return 1
    LE_BLOCK_BEGIN=$((start - 1))
    LE_BLOCK_END=$((end + ${#LE_MARK_END} + 1))
    dd if="$file" of="$LE_WORK/found-block" bs=1 skip="$LE_BLOCK_BEGIN" count="$((LE_BLOCK_END - LE_BLOCK_BEGIN))" status=none
    cmp -s "$LE_WORK/found-block" "$LE_STATE_DIR/path-block"
}
