"""Trusted-branch signing entrypoint. Never executes downloaded release binaries."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

import release


def gh(*args, **kwargs):
    return subprocess.run(['gh', *map(str, args)], check=True, **kwargs)


def primary_fingerprints(keyring):
    result = subprocess.run(['gpg', '--batch', '--show-keys', '--with-colons', str(keyring)],
                            capture_output=True, text=True, check=True).stdout
    fingerprints, need_primary = [], False
    for line in result.splitlines():
        parts = line.split(':')
        if parts[0] == 'pub':
            need_primary = True
        elif parts[0] == 'fpr' and need_primary:
            fingerprints.append(parts[9].upper())
            need_primary = False
    return fingerprints


def unpack_state(archive, output):
    with tarfile.open(archive, 'r:gz') as bundle:
        members = bundle.getmembers()
        if sum(item.size for item in members) > 2 * 1024 ** 3 or len(members) > 100000:
            raise ValueError('APT history snapshot exceeds configured resource limits')
        for item in members:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                raise ValueError('Unsafe APT history archive member')
        bundle.extractall(output, filter='data')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tag', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    data = release.config(require=('github_owner', 'github_repository', 'apt_base_url', 'apt_signing_fingerprint'))
    release.validate_public(argparse.Namespace(config=None, version=release.version(args.tag)))
    repository = data['github_owner'] + '/' + data['github_repository']
    if os.environ.get('GITHUB_REPOSITORY') != repository:
        raise ValueError('Repository ownership mismatch')
    private_key = os.environ.pop('APT_SIGNING_KEY', '')
    passphrase = os.environ.pop('APT_SIGNING_PASSPHRASE', '')
    if not private_key:
        raise ValueError('Protected APT_SIGNING_KEY secret is missing; nothing will be published')
    expected = data['apt_signing_fingerprint'].replace(' ', '').upper()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='le-apt-publish-') as temporary:
        work = Path(temporary)
        signing = work / 'secret-key-home'
        signing.mkdir(mode=0o700)
        (signing / 'gpg-agent.conf').write_text('allow-loopback-pinentry\ndefault-cache-ttl 3600\nmax-cache-ttl 3600\n', encoding='ascii')
        os.environ['GNUPGHOME'] = str(signing)
        try:
            subprocess.run(['gpg', '--batch', '--import'], input=private_key.encode(), check=True, capture_output=True)
            private_key = ''
            public_key = subprocess.check_output(['gpg', '--batch', '--export', expected])
            probe_key = work / 'expected-public.gpg'
            probe_key.write_bytes(public_key)
            if primary_fingerprints(probe_key) != [expected]:
                raise ValueError('Signing secret does not match the configured fingerprint')
            probe = work / 'signing-probe'
            probe.write_text('Signing readiness check', encoding='utf-8')
            subprocess.run(['gpg', '--batch', '--yes', '--pinentry-mode', 'loopback', '--passphrase-fd', '0',
                            '--local-user', expected, '--detach-sign', str(probe)],
                           input=(passphrase + '\n').encode(), check=True, capture_output=True)
            passphrase = ''
            state = work / 'repository-state'
            releases = json.loads(gh('release', 'list', '--repo', repository, '--limit', '100',
                                    '--json', 'tagName,isDraft', capture_output=True, text=True).stdout)
            for previous in releases:
                if previous['isDraft']:
                    continue
                assets = json.loads(gh('release', 'view', previous['tagName'], '--repo', repository,
                                       '--json', 'assets', capture_output=True, text=True).stdout)['assets']
                if any(item['name'] == 'apt-repository-state.tar.gz' for item in assets):
                    history = work / 'history'
                    history.mkdir()
                    gh('release', 'download', previous['tagName'], '--repo', repository,
                       '--pattern', 'apt-repository-state.tar.gz', '--dir', history)
                    unpack_state(history / 'apt-repository-state.tar.gz', state)
                    allowed = {expected, *[item.replace(' ', '').upper() for item in data.get('apt_trusted_previous_fingerprints', [])]}
                    actual = set(primary_fingerprints(state / 'le-archive-keyring.gpg'))
                    if not actual or not actual.issubset(allowed):
                        raise ValueError('APT snapshot uses an unapproved historical signing key')
                    subprocess.run(['gpgv', '--keyring', str(state / 'le-archive-keyring.gpg'),
                                    str(state / 'SNAPSHOT.json.sig'), str(state / 'SNAPSHOT.json')], check=True)
                    recorded_files = json.loads((state / 'SNAPSHOT.json').read_text(encoding='utf-8'))
                    actual_files = {path.relative_to(state).as_posix(): release.sha256(path)
                                    for path in state.rglob('*') if path.is_file() and path.name not in ('SNAPSHOT.json', 'SNAPSHOT.json.sig')}
                    if recorded_files != actual_files:
                        raise ValueError('APT history snapshot was altered; refusing its repository state')
                    subprocess.run(['gpgv', '--keyring', str(state / 'le-archive-keyring.gpg'),
                                    str(state / 'dists' / data['apt_suite'] / 'InRelease')], check=True)
                    break
            packages = work / 'packages'
            packages.mkdir()
            gh('release', 'download', args.tag, '--repo', repository, '--pattern', 'le-cli_*.deb', '--pattern', 'SHA256SUMS', '--dir', packages)
            checksums = {}
            for line in (packages / 'SHA256SUMS').read_text(encoding='utf-8').splitlines():
                digest, filename = line.split(None, 1)
                checksums[filename.strip().removeprefix('*')] = digest
            for package in packages.glob('*.deb'):
                if checksums.get(package.name) != release.sha256(package):
                    raise ValueError('Published Debian artifact checksum mismatch')
                arch = subprocess.check_output(['dpkg-deb', '--field', str(package), 'Architecture'], text=True).strip()
                new_version = subprocess.check_output(['dpkg-deb', '--field', str(package), 'Version'], text=True).strip()
                if new_version != release.deb_version(args.tag):
                    raise ValueError('Debian package version/tag mismatch')
                index = state / 'dists' / data['apt_suite'] / 'main' / ('binary-' + arch) / 'Packages'
                if index.exists():
                    for line in index.read_text().splitlines():
                        if line.startswith('Version: '):
                            previous_version = line.removeprefix('Version: ')
                            if subprocess.run(['dpkg', '--compare-versions', new_version, 'lt', previous_version]).returncode == 0:
                                raise ValueError('Refusing an APT repository downgrade')
            release.apt_repository(argparse.Namespace(config=None, packages=str(packages), output=str(state)))
            # Public Pages payload excludes the mutable reprepro database/config.
            for name in ['dists', 'pool', 'keys']:
                destination = output / name
                if destination.exists():
                    raise ValueError('Use a fresh Pages output directory')
                shutil.copytree(state / name, destination)
            for name in ['le-archive-keyring.gpg', 'KEY_FINGERPRINT', '.nojekyll']:
                shutil.copyfile(state / name, output / name)
            snapshot = work / 'apt-repository-state.tar.gz'
            state_manifest = {path.relative_to(state).as_posix(): release.sha256(path)
                              for path in state.rglob('*') if path.is_file() and path.name not in ('SNAPSHOT.json', 'SNAPSHOT.json.sig')}
            (state / 'SNAPSHOT.json').write_text(json.dumps(state_manifest, sort_keys=True), encoding='utf-8')
            subprocess.run(['gpg', '--batch', '--yes', '--local-user', expected, '--detach-sign',
                            '--output', str(state / 'SNAPSHOT.json.sig'), str(state / 'SNAPSHOT.json')], check=True)
            with tarfile.open(snapshot, 'w:gz') as archive:
                for path in sorted(state.iterdir()):
                    archive.add(path, arcname=path.name)
            # State artifacts contain public packages/signatures only; the
            # private GNUPGHOME is outside state and never archived.
            gh('release', 'upload', args.tag, '--repo', repository, '--clobber', snapshot)
            checksums[snapshot.name] = release.sha256(snapshot)
            (packages / 'SHA256SUMS').write_text(''.join(f'{digest}  {name}\n' for name, digest in sorted(checksums.items())), encoding='utf-8')
            gh('release', 'upload', args.tag, '--repo', repository, '--clobber', packages / 'SHA256SUMS')
        finally:
            subprocess.run(['gpgconf', '--kill', 'gpg-agent'], check=False)
            os.environ.pop('GNUPGHOME', None)


if __name__ == '__main__':
    main()
