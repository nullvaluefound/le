#!/usr/bin/env python3
"""Use ephemeral signing keys and disposable containers, never the host dpkg database."""
import argparse
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

import release

ROOT = Path(__file__).resolve().parents[1]


def command(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def build_deb(binary, version, configuration, output):
    metadata = json.loads(Path(binary).with_name(Path(binary).name + '.build.json').read_text(encoding='utf-8'))
    epoch = metadata.get('source_date_epoch') or release.default_epoch()
    command(sys.executable, ROOT / 'packaging/release.py', 'deb', '--binary', binary,
            '--version', version, '--config', configuration, '--output', output, '--epoch', epoch)
    return next(Path(output).glob('*.deb'))


def check_package(package):
    archive = command('dpkg-deb', '--fsys-tarfile', package, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(archive), mode='r:') as contents:
        members = contents.getmembers()
        assert all(item.uid == 0 and item.gid == 0 for item in members)
        assert all(not item.name.startswith('./usr/local/') for item in members)
        executable = next(item for item in members if item.name == './usr/bin/le')
        assert executable.mode == 0o755
    control = command('dpkg-deb', '--field', package, capture_output=True, text=True).stdout
    assert 'Package: le-cli' in control and 'Replaces:' not in control and 'Conflicts:' not in control
    if shutil.which('lintian'):
        command('lintian', '--fail-on', 'error', package)


CONTAINER_TEST = r'''#!/bin/bash
set -euo pipefail
test ! -e /usr/bin/le
apt-get install -y /artifacts/actual/*.deb
le --version
le --help | grep -q -- --output-json
apt-get remove -y le-cli
dpkg --purge le-cli
test ! -e /usr/bin/le
# A local-only package has no APT index entry after complete removal.
# Exercise APT purge while installed as a separate installation cycle.
apt-get install -y /artifacts/actual/*.deb
apt-get purge -y le-cli
test ! -e /usr/bin/le
mkdir -p /tmp/le-keyrings /tmp/le-sources
cp /artifacts/repo-v1/le-archive-keyring.gpg /tmp/le-keyrings/le.gpg
cp -a /artifacts/repo-v1 /tmp/le-repository
chmod -R a+rX /tmp/le-repository /tmp/le-keyrings
printf 'Types: deb
URIs: file:/tmp/le-repository
Suites: stable
Components: main
Signed-By: /tmp/le-keyrings/le.gpg
' > /tmp/le-sources/le.sources
APT_OPTIONS=(-o Dir::Etc::sourcelist=/dev/null -o Dir::Etc::sourceparts=/tmp/le-sources)
apt-get "${APT_OPTIONS[@]}" update
apt-get "${APT_OPTIONS[@]}" install -y le-cli
le --version | grep -q '1.0.0'
cp -a /artifacts/repo-v2/. /tmp/le-repository/
chmod -R a+rX /tmp/le-repository
apt-get "${APT_OPTIONS[@]}" update
apt-get "${APT_OPTIONS[@]}" upgrade -y
le --version | grep -q '1.0.1'
apt-get "${APT_OPTIONS[@]}" remove -y le-cli
apt-get "${APT_OPTIONS[@]}" purge -y le-cli
test ! -e /usr/bin/le
cp -a /artifacts/repo-v2 /tmp/le-unsigned
rm /tmp/le-unsigned/dists/stable/InRelease /tmp/le-unsigned/dists/stable/Release.gpg
sed -i 's,file:/tmp/le-repository,file:/tmp/le-unsigned,' /tmp/le-sources/le.sources
if apt-get "${APT_OPTIONS[@]}" update; then echo 'ERROR: unsigned repository accepted' >&2; exit 1; fi
sed -i 's,file:/tmp/le-unsigned,file:/tmp/le-repository,' /tmp/le-sources/le.sources
printf invalid-key > /tmp/le-keyrings/wrong.gpg
sed -i 's,le.gpg,wrong.gpg,' /tmp/le-sources/le.sources
if apt-get "${APT_OPTIONS[@]}" update; then echo 'ERROR: invalid signing key accepted' >&2; exit 1; fi
sed -i 's,wrong.gpg,le.gpg,' /tmp/le-sources/le.sources
printf '#!/bin/sh\necho unrelated\n' > /usr/bin/le
chmod 755 /usr/bin/le
before=$(sha256sum /usr/bin/le)
if apt-get install -y /artifacts/actual/*.deb; then echo 'ERROR: foreign executable overwritten' >&2; exit 1; fi
test "$before" = "$(sha256sum /usr/bin/le)"
rm /usr/bin/le
apt-get remove -y le-cli || true
# Check the actual unrelated Debian editor where the distro provides it.
apt-get update
if apt-cache show le >/dev/null 2>&1; then
    apt-get install -y le
    before=$(sha256sum /usr/bin/le)
    if apt-get install -y /artifacts/actual/*.deb; then echo 'ERROR: Debian le editor was displaced' >&2; exit 1; fi
    test "$before" = "$(sha256sum /usr/bin/le)"
    test "$(dpkg-query -W -f='${db:Status-Status}' le)" = installed
fi
echo 'APT install, signed upgrade, removal, purge, signature refusal, and collision tests passed.'
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binary', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--containers', action='store_true')
    args = parser.parse_args()
    binary = Path(args.binary).resolve()
    release.smoke(binary, args.version)
    with tempfile.TemporaryDirectory(prefix='le-apt-tests-') as temporary:
        base = Path(temporary)
        artifacts = base / 'public-artifacts'
        artifacts.mkdir(mode=0o755)
        signing = base / 'test-signing-key'
        signing.mkdir(mode=0o700)
        previous_gnupg = os.environ.get('GNUPGHOME')
        os.environ['GNUPGHOME'] = str(signing)
        try:
            command('gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '',
                    '--quick-generate-key', 'LE Packaging Test Key (temporary, never production) <test-fixture@example.invalid>',
                    'ed25519', 'sign', '1d')
            listing = command('gpg', '--batch', '--with-colons', '--list-secret-keys', capture_output=True, text=True).stdout
            fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
            fixture_config = base / 'fixture-config.json'
            command(sys.executable, ROOT / 'packaging/make_fixture_config.py', fixture_config, '--fingerprint', fingerprint)
            actual = build_deb(binary, args.version, fixture_config, artifacts / 'actual')
            check_package(actual)
            arch = release.identity(binary)[1]
            for package_version in ('1.0.0', '1.0.1'):
                source = base / ('fixture-' + package_version + '.c')
                source.write_text('#include <stdio.h>\nint main(void){ puts("le packaging fixture ' + package_version + '"); return 0; }\n', encoding='utf-8')
                executable = base / ('fixture-' + package_version)
                command('cc', '-O2', '-s', '-o', executable, source)
                metadata = {'version': package_version, 'sha256': release.sha256(executable), 'minimum_glibc': platform.libc_ver()[1]}
                executable.with_name(executable.name + '.build.json').write_text(json.dumps(metadata), encoding='utf-8')
                output = base / ('deb-' + package_version)
                package = build_deb(executable, package_version, fixture_config, output)
                check_package(package)
                repository = base / 'repository-state'
                command(sys.executable, ROOT / 'packaging/release.py', 'apt', '--config', fixture_config,
                        '--packages', output, '--output', repository)
                snapshot = artifacts / ('repo-v1' if package_version == '1.0.0' else 'repo-v2')
                shutil.copytree(repository, snapshot)
            # Both versions remain in pool even when only the newest is indexed.
            assert len(list((artifacts / 'repo-v2/pool').rglob('*.deb'))) == 2
            wrong_key = base / 'empty-keyring.gpg'
            wrong_key.write_bytes(b'')
            invalid = subprocess.run(['gpgv', '--keyring', str(wrong_key), str(artifacts / 'repo-v2/dists/stable/InRelease')], capture_output=True)
            assert invalid.returncode != 0
            tested = []
            if args.containers:
                command('docker', 'info', stdout=subprocess.DEVNULL)
                metadata = json.loads(binary.with_name(binary.name + '.build.json').read_text())
                minimum = tuple(map(int, metadata['minimum_glibc'].split('.')))
                images = ['ubuntu:22.04', 'debian:12-slim'] if minimum <= (2, 35) else ['ubuntu:24.04', 'debian:13-slim']
                script = artifacts / 'container-tests.sh'
                script.write_text(CONTAINER_TEST, encoding='utf-8')
                for image in images:
                    command('docker', 'run', '--rm', '--volume', f'{artifacts}:/artifacts:ro', image,
                            'bash', '/artifacts/container-tests.sh')
                    tested.append(image)
            report = {'actual_deb': actual.name, 'architecture': arch, 'ephemeral_signature_verified': True,
                      'untrusted_key_rejected': True, 'prior_pool_versions_preserved': True,
                      'clean_container_tests': tested, 'synthetic_test_metadata_only': True}
            (ROOT / 'build').mkdir(exist_ok=True)
            (ROOT / 'build/apt-test-results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
            print(json.dumps(report, indent=2))
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], check=False)
            if previous_gnupg is None:
                os.environ.pop('GNUPGHOME', None)
            else:
                os.environ['GNUPGHOME'] = previous_gnupg


if __name__ == '__main__':
    main()
