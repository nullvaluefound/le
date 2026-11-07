le_apt_guard
if ! le_read_record; then
    printf 'No manual le installation record found; nothing was removed. For an APT installation, use sudo apt remove le-cli.\n'
    exit 0
fi
le_verify_owned_binary
LE_REMOVE_BIN=$(le_field 5)
LE_REMOVE_STATE=$(le_field 6)
le_new_work
if [ -f "$LE_STATE_DIR/path-files" ]; then
    while IFS=$'\t' read -r LE_CREATED LE_RC; do
        [ -n "$LE_RC" ] || continue
        case "$LE_RC" in "$LE_HOME_DIR/.profile"|"$LE_HOME_DIR/.bashrc"|"$LE_HOME_DIR/.zshrc") ;; *) le_fail 'Ownership record names an unexpected profile; refusing removal.';; esac
        [ ! -L "$LE_RC" ] || le_fail 'Profile changed into a symlink; preserving it.'
        if [ -f "$LE_RC" ]; then
            if ! grep -Fq -- "$LE_MARK_START" "$LE_RC" && ! grep -Fq -- "$LE_MARK_END" "$LE_RC"; then continue; fi
            le_block_offsets "$LE_RC" || le_fail "The installer-owned PATH block was changed in $LE_RC; preserving user edits."
        fi
    done < "$LE_STATE_DIR/path-files"
    while IFS=$'\t' read -r LE_CREATED LE_RC; do
        [ -n "$LE_RC" ] && [ -f "$LE_RC" ] || continue
        if ! grep -Fq -- "$LE_MARK_START" "$LE_RC" && ! grep -Fq -- "$LE_MARK_END" "$LE_RC"; then continue; fi
        le_block_offsets "$LE_RC"
        { dd if="$LE_RC" bs=1 count="$LE_BLOCK_BEGIN" status=none; dd if="$LE_RC" bs=1 skip="$LE_BLOCK_END" status=none; } > "$LE_WORK/profile"
        if [ "$LE_CREATED" = 1 ] && [ ! -s "$LE_WORK/profile" ]; then
            rm -f -- "$LE_RC"
        else
            le_atomic_copy "$LE_WORK/profile" "$LE_RC" "$(stat -c %a "$LE_RC")"
        fi
    done < "$LE_STATE_DIR/path-files"
fi
[ ! -e "$LE_TARGET" ] || rm -- "$LE_TARGET"
rm -f -- "$LE_RECORD" "$LE_STATE_DIR/path-files" "$LE_STATE_DIR/path-block"
if [ "$LE_REMOVE_STATE" = 1 ]; then rmdir -- "$LE_STATE_DIR" 2>/dev/null || true; fi
if [ "$LE_REMOVE_BIN" = 1 ]; then rmdir -- "$LE_BIN_DIR" 2>/dev/null || true; fi
printf 'Removed the manually installed le. Unrelated files and configuration were preserved.\n'
