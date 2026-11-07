"""Verify the deployed production APT repository in disposable native clients."""
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]

CLIENT_TEST = r'''set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg
bash /source/packaging/setup-apt.sh --fingerprint "$LE_EXPECTED_FINGERPRINT"
# A publication can precede the Pages edge cache becoming ready by a few seconds.
ready=0
for attempt in $(seq 1 12); do
    if apt-get -o APT::Update::Error-Mode=any update; then ready=1; break; fi
    sleep 5
done
test "$ready" = 1
apt-cache policy le-cli
apt-get install -y le-cli
test "$(dpkg-query -S /usr/bin/le)" = 'le-cli: /usr/bin/le'
le --version
le --help | grep -q -- --output-json
mkdir -p /tmp/le-public-smoke/child
printf fixture > /tmp/le-public-smoke/child/file.txt
le /tmp/le-public-smoke -rn 1 --output-json /tmp/le-public-tree.json
grep -q 'file.txt' /tmp/le-public-tree.json
grep -q '/tmp/le-public-smoke/child' /tmp/le-public-tree.json
apt-get purge -y le-cli
test ! -e /usr/bin/le
bash /source/packaging/setup-apt.sh --remove-repository
test ! -e /etc/apt/sources.list.d/le.sources
test ! -e /etc/apt/keyrings/le-archive-keyring.gpg
printf '%s\n' 'Production HTTPS APT signature verification, install, CLI/JSON, purge and repository removal passed.'
'''


def main():
    if os.environ.get('CI') != 'true' or not os.environ.get('RUNNER_TEMP'):
        raise SystemExit('Run only on a disposable CI runner; host package state must remain untouched.')
    data = json.loads((ROOT / 'packaging/distribution.json').read_text(encoding='utf-8'))
    fingerprint = data.get('apt_signing_fingerprint', '')
    if not isinstance(fingerprint, str) or not re.fullmatch('[A-F0-9]{40,64}', fingerprint):
        raise ValueError('A full configured production signing fingerprint is required.')
    for image in ('ubuntu:22.04', 'debian:12-slim'):
        subprocess.run(['docker', 'run', '--rm', '--interactive', '--volume', f'{ROOT}:/source:ro',
                        '--env', 'LE_EXPECTED_FINGERPRINT=' + fingerprint, image, 'bash', '-s'],
                       input=CLIENT_TEST.encode(), check=True)
        print(f'Production APT client passed: {image}', flush=True)


if __name__ == '__main__':
    main()
