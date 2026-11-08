# One-time APT onboarding and package installation. The repository helper above
# runs in a subshell so its cleanup trap and temporary GNUPGHOME stay private.
if [ "$#" -gt 0 ]; then
    case "$1" in
        --help|-h)
            [ "$#" -eq 1 ] || { echo 'Unexpected arguments.' >&2; exit 1; }
            printf 'Usage: sudo bash install-apt.sh\n\nInstalls prerequisites, configures the signed le repository, and installs le-cli.\nSupported package architectures: %s\n' "$LE_INSTALL_APT_ARCHITECTURES"
            exit 0;;
        *) echo 'Usage: sudo bash install-apt.sh (or --help)' >&2; exit 1;;
    esac
fi
[ "$(id -u)" -eq 0 ] || { echo 'Run with: sudo bash install-apt.sh. No changes were made.' >&2; exit 1; }
[[ "$LE_INSTALL_APT_FINGERPRINT" =~ ^[A-F0-9]{40,64}$ ]] || { echo 'APT signing is not configured in this installer. Use a current published installer.' >&2; exit 1; }
for LE_APT_COMMAND in apt-get dpkg dpkg-query; do
    command -v "$LE_APT_COMMAND" >/dev/null 2>&1 || { echo 'This installer requires a Debian/Ubuntu system with APT.' >&2; exit 1; }
done
LE_APT_ARCHITECTURE=$(dpkg --print-architecture)
case " $LE_INSTALL_APT_ARCHITECTURES " in
    *" $LE_APT_ARCHITECTURE "*) ;;
    *) printf 'No published le-cli package for architecture %s. Supported: %s\n' "$LE_APT_ARCHITECTURE" "$LE_INSTALL_APT_ARCHITECTURES" >&2; exit 1;;
esac
LE_APT_MISSING=()
for LE_APT_PACKAGE in ca-certificates curl gnupg; do
    LE_APT_STATUS=$(dpkg-query -W -f='${db:Status-Status}' "$LE_APT_PACKAGE" 2>/dev/null || true)
    [ "$LE_APT_STATUS" = installed ] || LE_APT_MISSING+=("$LE_APT_PACKAGE")
done
if [ "${#LE_APT_MISSING[@]}" -gt 0 ]; then
    echo 'Installing required tools...'
    apt-get -o APT::Update::Error-Mode=any update
    apt-get install -y --no-install-recommends "${LE_APT_MISSING[@]}"
fi
echo 'Configuring the signed le repository...'
le_configure_apt_repository --url "$LE_INSTALL_APT_URL" --suite "$LE_INSTALL_APT_SUITE" --fingerprint "$LE_INSTALL_APT_FINGERPRINT" >/dev/null
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y --no-install-recommends le-cli
printf '\nle-cli is installed. Run: le\nUpdate later with: sudo apt-get update && sudo apt-get install --only-upgrade le-cli\n'
