le_apt_guard
LE_PREVIOUS=0
if le_read_record; then
    LE_PREVIOUS=1
    le_verify_owned_binary
elif [ -e "$LE_TARGET" ] || [ -L "$LE_TARGET" ]; then
    le_fail 'An unrelated le already exists at the target. Nothing was replaced.'
elif [ -e "$LE_STATE_DIR" ] && [ -n "$(ls -A -- "$LE_STATE_DIR")" ]; then
    le_fail 'The state directory contains unrelated files without an ownership record.'
fi
LE_OTHER=$(command -v le || true)
if [ -n "$LE_OTHER" ] && [ "$(readlink -m -- "$LE_OTHER")" != "$LE_TARGET" ] && [ "$LE_ALLOW_SHADOW" -ne 1 ]; then
    le_fail "Another le command exists at $LE_OTHER. Use --allow-shadow only if you explicitly want this separate installation to take precedence."
fi
case "$(uname -m)" in x86_64|amd64) LE_ARCH=amd64; LE_MACHINE=62;; aarch64|arm64) LE_ARCH=arm64; LE_MACHINE=183;; *) le_fail 'Only AMD64 and ARM64 release artifacts are supported.';; esac
le_new_work
if [ -z "$LE_BINARY" ]; then
    [[ "$LE_REPOSITORY" =~ ^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$ ]] || le_fail 'Set --repo OWNER/REPO.'
    if [ "$LE_VERSION" = latest ]; then
        LE_URL="https://github.com/$LE_REPOSITORY/releases/latest/download"
    else
        [[ "$LE_VERSION" =~ ^v?[0-9]+\.[0-9]+\.[0-9]+([-+][A-Za-z0-9.-]+)?$ ]] || le_fail 'Invalid release version.'
        LE_URL="https://github.com/$LE_REPOSITORY/releases/download/v${LE_VERSION#v}"
    fi
    LE_BINARY="$LE_WORK/le-linux-$LE_ARCH"
    LE_CHECKSUM_FILE="$LE_WORK/SHA256SUMS"
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --location --retry 3 "$LE_URL/le-linux-$LE_ARCH" -o "$LE_BINARY"
    curl --proto '=https' --proto-redir '=https' --tlsv1.2 --fail --location --retry 3 "$LE_URL/SHA256SUMS" -o "$LE_CHECKSUM_FILE"
fi
[ -f "$LE_BINARY" ] || le_fail 'Local binary not found.'
if [ -z "$LE_EXPECTED_SHA" ] && [ -n "$LE_CHECKSUM_FILE" ]; then
    LE_EXPECTED_SHA=$(awk -v file="$(basename "$LE_BINARY")" 'length($1)==64 {name=$2; sub(/^\*/,"",name); if(name==file) {print $1; n++}} END {if(n!=1) exit 1}' "$LE_CHECKSUM_FILE") || le_fail 'Checksum file must contain exactly one entry for this artifact.'
fi
[[ "$LE_EXPECTED_SHA" =~ ^[a-fA-F0-9]{64}$ ]] || le_fail 'Supply --checksum-file or --sha256 for a local artifact.'
LE_ACTUAL_SHA=$(le_hash "$LE_BINARY")
[ "${LE_EXPECTED_SHA,,}" = "$LE_ACTUAL_SHA" ] || le_fail 'SHA-256 verification failed.'
LE_HEADER=$(od -An -tx1 -N6 "$LE_BINARY" | tr -d ' \n')
[ "$LE_HEADER" = 7f454c460201 ] || le_fail 'Release artifact must be a 64-bit little-endian ELF executable.'
LE_ACTUAL_MACHINE=$(od -An -tu2 -j18 -N2 "$LE_BINARY" | tr -d ' \n')
[ "$LE_ACTUAL_MACHINE" = "$LE_MACHINE" ] || le_fail 'ELF architecture does not match this machine.'
install -m 755 -- "$LE_BINARY" "$LE_WORK/le"
LE_REPORTED_VERSION=$("$LE_WORK/le" --version) || le_fail 'The candidate executable cannot run on this system (check its documented glibc baseline).'
"$LE_WORK/le" --help >/dev/null || le_fail 'Candidate --help smoke test failed.'
case "$LE_REPORTED_VERSION" in *$'\n'*|*$'\r'*) le_fail 'The executable reported a multiline version.';; esac
LE_NEEDS_PATH=0
LE_PROFILE_COUNT=0
LE_RC_NAMES=(.profile .bashrc .zshrc)
# Bash login shells prefer these existing files over .profile. Do not create
# either file: that would change the user's startup-file precedence.
for LE_LOGIN_NAME in .bash_profile .bash_login; do
    if [ -e "$LE_HOME_DIR/$LE_LOGIN_NAME" ] || [ -L "$LE_HOME_DIR/$LE_LOGIN_NAME" ]; then
        LE_RC_NAMES+=("$LE_LOGIN_NAME")
        break
    fi
done
if [ "$LE_PREVIOUS" -eq 0 ]; then
    le_make_block
    : > "$LE_WORK/new-path-files"
    case ":$PATH:" in *:"$LE_BIN_DIR":*) ;; *) [ "$LE_SYSTEM" -eq 1 ] || LE_NEEDS_PATH=1;; esac
    if [ "$LE_NEEDS_PATH" -eq 1 ]; then
        for LE_RC_NAME in "${LE_RC_NAMES[@]}"; do
            LE_RC="$LE_HOME_DIR/$LE_RC_NAME"
            [ ! -L "$LE_RC" ] || le_fail "Refusing to edit a symlinked profile: $LE_RC"
            if [ -f "$LE_RC" ] && grep -Fq -- "$LE_MARK_START" "$LE_RC"; then
                le_fail "An unowned le PATH marker already exists in $LE_RC; nothing was installed."
            fi
            LE_CREATED=1
            if [ -e "$LE_RC" ]; then
                [ -f "$LE_RC" ] || le_fail 'A shell profile path is not a regular file.'
                cp -p -- "$LE_RC" "$LE_WORK/profile-$LE_PROFILE_COUNT.old"
                LE_CREATED=0
                cat "$LE_RC" "$LE_WORK/path-block" > "$LE_WORK/profile-$LE_PROFILE_COUNT.new"
            else
                cp -- "$LE_WORK/path-block" "$LE_WORK/profile-$LE_PROFILE_COUNT.new"
            fi
            printf '%s\t%s\n' "$LE_CREATED" "$LE_RC" >> "$LE_WORK/new-path-files"
            LE_PROFILE_COUNT=$((LE_PROFILE_COUNT + 1))
        done
    fi
fi
LE_BIN_EXISTED=0; [ ! -d "$LE_BIN_DIR" ] || LE_BIN_EXISTED=1
LE_STATE_EXISTED=0; [ ! -d "$LE_STATE_DIR" ] || LE_STATE_EXISTED=1
LE_BIN_CREATED=$((1 - LE_BIN_EXISTED))
LE_STATE_CREATED=$((1 - LE_STATE_EXISTED))
if [ "$LE_PREVIOUS" -eq 1 ]; then
    LE_BIN_CREATED=$(le_field 5); LE_BIN_CREATED=${LE_BIN_CREATED:-0}
    LE_STATE_CREATED=$(le_field 6); LE_STATE_CREATED=${LE_STATE_CREATED:-0}
fi
mkdir -p -- "$LE_BIN_DIR" "$LE_STATE_DIR"
[ ! -L "$LE_STATE_DIR" ] || le_fail 'Refusing a symlinked state directory.'
LE_HAD_BINARY=0
if [ -f "$LE_TARGET" ]; then cp -p -- "$LE_TARGET" "$LE_WORK/previous-le"; LE_HAD_BINARY=1; fi
for LE_STATE_FILE in ownership path-files path-block; do
    [ ! -L "$LE_STATE_DIR/$LE_STATE_FILE" ] || le_fail 'Refusing symlinked installer metadata.'
    if [ -f "$LE_STATE_DIR/$LE_STATE_FILE" ]; then cp -p -- "$LE_STATE_DIR/$LE_STATE_FILE" "$LE_WORK/$LE_STATE_FILE.old"; fi
done
LE_INSTALL_COMMITTED=0
le_finish_install() {
    local status=$? failed=0 index=0 created profile mode
    trap - EXIT
    set +e
    if [ "$status" -ne 0 ] && [ "$LE_INSTALL_COMMITTED" -eq 0 ]; then
        if [ "$LE_HAD_BINARY" -eq 1 ]; then le_atomic_copy "$LE_WORK/previous-le" "$LE_TARGET" 755 || failed=1
        elif [ -f "$LE_TARGET" ] && [ "$(le_hash "$LE_TARGET")" = "$LE_ACTUAL_SHA" ]; then rm -f -- "$LE_TARGET"; fi
        if [ -f "$LE_WORK/new-path-files" ]; then
            while IFS=$'\t' read -r created profile; do
                if [ -f "$profile" ] && [ "$(le_hash "$profile")" = "$(le_hash "$LE_WORK/profile-$index.new")" ]; then
                    if [ "$created" = 1 ]; then rm -f -- "$profile"
                    else mode=$(stat -c %a "$LE_WORK/profile-$index.old"); le_atomic_copy "$LE_WORK/profile-$index.old" "$profile" "$mode" || failed=1; fi
                elif [ -e "$profile" ] && [ -f "$LE_WORK/profile-$index.old" ] && ! cmp -s "$profile" "$LE_WORK/profile-$index.old"; then failed=1; fi
                index=$((index + 1))
            done < "$LE_WORK/new-path-files"
        fi
        for LE_STATE_FILE in ownership path-files path-block; do
            if [ -f "$LE_WORK/$LE_STATE_FILE.old" ]; then le_atomic_copy "$LE_WORK/$LE_STATE_FILE.old" "$LE_STATE_DIR/$LE_STATE_FILE" 600 || failed=1
            else rm -f -- "$LE_STATE_DIR/$LE_STATE_FILE"; fi
        done
        [ "$LE_STATE_EXISTED" -eq 1 ] || rmdir -- "$LE_STATE_DIR" 2>/dev/null || true
        [ "$LE_BIN_EXISTED" -eq 1 ] || rmdir -- "$LE_BIN_DIR" 2>/dev/null || true
    fi
    if [ "$failed" -eq 0 ]; then rm -rf -- "$LE_WORK"
    else printf 'Rollback preserved changed files; recovery backups remain at %s\n' "$LE_WORK" >&2; fi
    exit "$status"
}
trap le_finish_install EXIT
le_atomic_copy "$LE_WORK/le" "$LE_TARGET" 755
if ! "$LE_TARGET" --version >/dev/null; then
    le_fail 'Installed smoke test failed; executable rolled back.'
fi
if [ "$LE_PREVIOUS" -eq 0 ]; then
    le_atomic_copy "$LE_WORK/new-path-files" "$LE_STATE_DIR/path-files" 600
    le_atomic_copy "$LE_WORK/path-block" "$LE_STATE_DIR/path-block" 600
    if [ "$LE_NEEDS_PATH" -eq 1 ]; then
        mkdir -p -- "$LE_HOME_DIR"
        LE_PROFILE_COUNT=0
        for LE_RC_NAME in "${LE_RC_NAMES[@]}"; do
            LE_RC="$LE_HOME_DIR/$LE_RC_NAME"
            LE_MODE=644
            if [ -f "$LE_WORK/profile-$LE_PROFILE_COUNT.old" ]; then LE_MODE=$(stat -c %a "$LE_WORK/profile-$LE_PROFILE_COUNT.old"); fi
            le_atomic_copy "$LE_WORK/profile-$LE_PROFILE_COUNT.new" "$LE_RC" "$LE_MODE"
            LE_PROFILE_COUNT=$((LE_PROFILE_COUNT + 1))
        done
    fi
fi
{
    printf 'LE-MANUAL-BASH-1\n%s\n%s\n%s\n%s\n%s\n' "$LE_TARGET" "$LE_ACTUAL_SHA" "$LE_REPORTED_VERSION" "$LE_BIN_CREATED" "$LE_STATE_CREATED"
} > "$LE_WORK/ownership"
le_atomic_copy "$LE_WORK/ownership" "$LE_RECORD" 600
LE_INSTALL_COMMITTED=1
printf 'Installed %s\nExecutable: %s\nOpen a new terminal if PATH was updated.\n' "$LE_REPORTED_VERSION" "$LE_TARGET"
