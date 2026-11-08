#!/usr/bin/env python3
"""Build and validate distribution artifacts; application source stays untouched."""
import argparse
import gzip
import hashlib
import datetime
import json
import os
from pathlib import Path
import platform
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import textwrap
import time
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = '1.28.0'
SEMVER = re.compile(r'^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$')


def run(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def default_epoch():
    configured = os.environ.get('SOURCE_DATE_EPOCH')
    if configured is not None:
        if not configured.isdigit():
            raise ValueError('SOURCE_DATE_EPOCH must be a non-negative integer')
        return int(configured)
    try:
        return int(subprocess.check_output(['git', '-C', str(ROOT), 'show', '-s', '--format=%ct', 'HEAD'],
                                            stderr=subprocess.DEVNULL, text=True).strip())
    except (OSError, ValueError, subprocess.CalledProcessError):
        return int(time.time())


def version(value):
    if not SEMVER.fullmatch(value):
        raise ValueError('Use a semantic version such as v1.0.0; no moving tags or path characters.')
    return value.removeprefix('v')


def deb_version(value):
    value = version(value)
    return value.replace('-', '~', 1)


def config(path=None, require=()):
    path = Path(path or ROOT / 'packaging' / 'distribution.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    missing = [key for key in require if not data.get(key) or str(data[key]).startswith('REQUIRED')]
    if missing:
        raise ValueError('Configure these real project values in distribution.json: ' + ', '.join(missing))
    return data


def identity(path):
    """Check binary headers rather than trusting an artifact's filename."""
    with Path(path).open('rb') as stream:
        first = stream.read(64)
        if first.startswith(b'MZ'):
            stream.seek(struct.unpack_from('<I', first, 60)[0])
            header = stream.read(6)
            if header[:4] != b'PE\0\0':
                raise ValueError('Invalid PE header')
            machine = struct.unpack_from('<H', header, 4)[0]
            return 'windows', {0x8664: 'amd64', 0xAA64: 'arm64'}.get(machine, 'unsupported')
        if first.startswith(b'\x7fELF'):
            if first[4:6] != b'\x02\x01':
                raise ValueError('Only 64-bit little-endian ELF artifacts are supported')
            machine = struct.unpack_from('<H', first, 18)[0]
            return 'linux', {62: 'amd64', 183: 'arm64'}.get(machine, 'unsupported')
    raise ValueError('Artifact must be a Windows PE or Linux ELF executable')


def smoke(binary, expected=None):
    binary = Path(binary).resolve()
    output = run(binary, '--version', capture_output=True).stdout.decode('utf-8').strip()
    match = re.search(r'(?<!\d)(\d+\.\d+(?:\.\d+)?(?:[-+][\w.-]+)?)\s*$', output)
    if not match:
        raise ValueError('The executable did not report a recognizable --version')
    if expected:
        from packaging.version import Version
        if Version(match.group(1)) != Version(version(expected)):
            raise ValueError(f'CLI version {match.group(1)} does not match release {expected}; update the application version before tagging.')
    help_text = run(binary, '--help', capture_output=True).stdout
    for option in [b'--recurse', b'--depth', b'--show-owner', b'--output-json']:
        if option not in help_text:
            raise ValueError('Smoke test failed: missing CLI option ' + option.decode())
    # PyInstaller on Windows keeps the existing console encoding behavior.
    # Use a real console there; pipe-based hierarchy smoke tests run on Linux.
    if os.name != 'nt':
        with tempfile.TemporaryDirectory(prefix='le-smoke-') as temporary:
            root = Path(temporary) / 'tree'
            (root / 'one' / 'two').mkdir(parents=True)
            (root / 'one' / 'file.txt').write_text('test', encoding='utf-8')
            destination = Path(temporary) / 'out.json'
            run(binary, root, '-rtn', '2', '--output-json', destination, stdout=subprocess.DEVNULL)
            tree = json.loads(destination.read_text(encoding='utf-8'))
            if not isinstance(tree, list) or str(root) not in tree[0]:
                raise ValueError('JSON smoke test failed')
    return output


def build(args):
    release_version = version(args.version)
    operating_system = 'windows' if os.name == 'nt' else 'linux'
    arch = {'x86_64': 'amd64', 'AMD64': 'amd64', 'aarch64': 'arm64', 'ARM64': 'arm64'}.get(platform.machine())
    if arch not in ('amd64', 'arm64'):
        raise ValueError('Unsupported native build architecture: ' + platform.machine())
    if args.arch and args.arch != arch:
        raise ValueError('Use a native runner for each architecture; cross-compilation is not enabled.')
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    name = f'le-{operating_system}-{arch}'
    from licenses import notices
    license_artifact = output / (name + '.LICENSES.txt')
    license_artifact.write_text(notices(ROOT), encoding='utf-8', newline='\n')
    env = dict(os.environ, PYTHONHASHSEED='0', SOURCE_DATE_EPOCH=str(args.epoch))
    with tempfile.TemporaryDirectory(prefix='le-build-') as work:
        run(sys.executable, '-m', 'PyInstaller', '--noconfirm', '--onefile', '--noupx',
            '--name', name, '--distpath', output, '--workpath', Path(work) / 'work',
            '--specpath', work, '--add-data', str(license_artifact) + ':licenses', ROOT / 'main.py', env=env)
    binary = output / (name + ('.exe' if operating_system == 'windows' else ''))
    if operating_system == 'linux':
        binary.chmod(0o755)
    if identity(binary) != (operating_system, arch):
        raise ValueError('Built binary architecture does not match the native runner')
    reported = smoke(binary, release_version)
    metadata = {
        'version': release_version, 'artifact': binary.name, 'os': operating_system,
        'architecture': arch, 'sha256': sha256(binary), 'source_sha256': sha256(ROOT / 'main.py'),
        'python': platform.python_version(), 'cli_version': reported,
        'license_artifact': license_artifact.name, 'license_sha256': sha256(license_artifact),
        'build_platform': platform.platform(), 'source_date_epoch': args.epoch,
        'minimum_glibc': platform.libc_ver()[1] if operating_system == 'linux' else None,
        'linkage': 'dynamic; PyInstaller bundles Python, not the operating-system C runtime'
    }
    (output / (name + '.build.json')).write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(metadata, indent=2))


def checksums(args):
    directory = Path(args.directory)
    files = sorted(path for path in directory.iterdir() if path.is_file() and path.name != 'SHA256SUMS')
    if not files:
        raise ValueError('No release artifacts to hash')
    text = ''.join(f'{sha256(path)}  {path.name}\n' for path in files)
    (directory / 'SHA256SUMS').write_text(text, encoding='utf-8', newline='\n')
    print(text, end='')


def bundle(args):
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    sources = {name: ROOT / name for name in ['install.ps1', 'uninstall.ps1', 'install.bat', 'uninstall.bat', 'install.sh', 'uninstall.sh', 'install-apt.sh', 'LICENSE']}
    sources.update({'setup-apt.sh': ROOT / 'packaging/setup-apt.sh', 'DISTRIBUTION.md': ROOT / 'docs/DISTRIBUTION.md'})
    timestamp = time.gmtime(max(args.epoch, 315532800))[:6]
    with zipfile.ZipFile(output / 'le-manual-installers.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, source in sorted(sources.items()):
            shutil.copyfile(source, output / name)
            info = zipfile.ZipInfo(name, timestamp)
            info.external_attr = (0o755 if name.endswith('.sh') else 0o644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    print(output / 'le-manual-installers.zip')


def release_url(data, release_version, filename):
    owner, repo = data['github_owner'], data['github_repository']
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
        raise ValueError('Invalid GitHub owner/repository')
    return f'https://github.com/{owner}/{repo}/releases/download/v{version(release_version)}/{filename}'


def winget(args):
    import yaml
    data = config(args.config, ('github_owner', 'github_repository', 'publisher', 'winget_identifier', 'license'))
    release_version = version(args.version)
    identifier = data['winget_identifier']
    if not re.fullmatch(r'[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)+', identifier):
        raise ValueError('WinGet identifier must look like Publisher.Le')
    output = Path(args.output) / 'manifests' / identifier[0].lower() / Path(*identifier.split('.')) / release_version
    output.mkdir(parents=True, exist_ok=True)
    installers = []
    checksum_path = Path(args.artifacts) / 'SHA256SUMS'
    published_hashes = {}
    if checksum_path.exists():
        for line in checksum_path.read_text(encoding='utf-8').splitlines():
            digest, filename = line.split(None, 1)
            name = filename.strip().removeprefix('*')
            if name in published_hashes:
                raise ValueError('Duplicate release checksum entry')
            published_hashes[name] = digest.lower()
    elif not data.get('test_fixture'):
        raise ValueError('Download the published SHA256SUMS alongside release binaries before generating manifests.')
    for arch in ('amd64', 'arm64'):
        binary = Path(args.artifacts) / f'le-windows-{arch}.exe'
        if binary.exists():
            if identity(binary) != ('windows', arch):
                raise ValueError('WinGet binary header/name mismatch')
            if published_hashes and published_hashes.get(binary.name) != sha256(binary):
                raise ValueError('Downloaded Windows artifact does not match published SHA256SUMS')
            installers.append({'Architecture': 'x64' if arch == 'amd64' else 'arm64',
                               'InstallerUrl': release_url(data, release_version, binary.name),
                               'InstallerSha256': sha256(binary).upper()})
    if not installers:
        raise ValueError('No tested Windows artifacts were supplied')
    documents = {
        '': {'PackageIdentifier': identifier, 'PackageVersion': release_version,
             'DefaultLocale': 'en-US', 'ManifestType': 'version', 'ManifestVersion': SCHEMA},
        '.installer': {'PackageIdentifier': identifier, 'PackageVersion': release_version,
                       'InstallerType': 'portable', 'Commands': ['le'],
                       'UpgradeBehavior': 'install', 'Installers': installers,
                       'ManifestType': 'installer', 'ManifestVersion': SCHEMA},
        '.locale.en-US': {'PackageIdentifier': identifier, 'PackageVersion': release_version,
                          'PackageLocale': 'en-US', 'Publisher': data['publisher'],
                          'PackageName': 'le', 'License': data['license'],
                          'ShortDescription': data['description'][:256],
                          'PackageUrl': f"https://github.com/{data['github_owner']}/{data['github_repository']}",
                          'ManifestType': 'defaultLocale', 'ManifestVersion': SCHEMA}
    }
    for suffix, document in documents.items():
        schema_name = document['ManifestType']
        header = f'# yaml-language-server: $schema=https://aka.ms/winget-manifest.{schema_name}.{SCHEMA}.schema.json\n'
        (output / (identifier + suffix + '.yaml')).write_text(header + yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding='utf-8')
    print(output)


def license_text(data):
    if not data.get('license_file'):
        raise ValueError('Configure license_file with the real, repository-owned license before packaging.')
    path = (ROOT / data['license_file']).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file():
        raise ValueError('license_file must name a real file within the repository')
    return path.read_text(encoding='utf-8')


def deb(args):
    data = config(args.config, ('maintainer_name', 'maintainer_email', 'license', 'license_file'))
    if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+', data['maintainer_email']):
        raise ValueError('Configure a real Debian maintainer email')
    for key in ('maintainer_name', 'license', 'description'):
        if '\n' in data[key] or '\r' in data[key]:
            raise ValueError('Control metadata must not contain newlines')
    binary = Path(args.binary).resolve()
    operating_system, arch = identity(binary)
    if operating_system != 'linux' or arch not in ('amd64', 'arm64'):
        raise ValueError('A supported Linux ELF artifact is required')
    metadata_path = binary.with_name(binary.name + '.build.json')
    metadata = json.loads(metadata_path.read_text(encoding='utf-8'))
    if metadata['sha256'] != sha256(binary) or metadata['version'] != version(args.version):
        raise ValueError('Binary build metadata/hash/version mismatch')
    minimum_glibc = metadata.get('minimum_glibc')
    if not minimum_glibc or not re.fullmatch(r'\d+\.\d+', minimum_glibc):
        raise ValueError('Build metadata must record the conservative glibc baseline')
    target = Path(args.output).resolve()
    target.mkdir(parents=True, exist_ok=True)
    artifact = target / f'le-cli_{deb_version(args.version)}_{arch}.deb'
    with tempfile.TemporaryDirectory(prefix='le-deb-') as temporary:
        root = Path(temporary)
        root.chmod(0o755)
        (root / 'DEBIAN').mkdir()
        (root / 'usr/bin').mkdir(parents=True)
        docs = root / 'usr/share/doc/le-cli'
        docs.mkdir(parents=True)
        shutil.copyfile(binary, root / 'usr/bin/le')
        (root / 'usr/bin/le').chmod(0o755)
        control = (f'Package: le-cli\nVersion: {deb_version(args.version)}\nArchitecture: {arch}\n'
                   f"Maintainer: {data['maintainer_name']} <{data['maintainer_email']}>\n"
                   f'Depends: libc6 (>= {minimum_glibc})\nSection: utils\nPriority: optional\n'
                   'Description: enhanced directory listing with metadata and JSON export\n' +
                   ''.join(' ' + line + '\n' for line in textwrap.wrap(data['description'], width=76)))
        (root / 'DEBIAN/control').write_text(control, encoding='utf-8')
        # No Replaces/Conflicts field: APT must never automatically remove the
        # unrelated Debian editor. Refuse both package and unmanaged collisions.
        preinst = r'''#!/bin/sh
set -eu
if dpkg-query -W -f='${db:Status-Status}' le 2>/dev/null | grep -qx installed; then
    echo 'le-cli cannot coexist with the unrelated Debian le editor. Nothing was overwritten. Keep the editor and use the per-user manual install, or resolve the conflict explicitly.' >&2
    exit 1
fi
if [ -e /usr/bin/le ] || [ -L /usr/bin/le ]; then
    owner=$(dpkg-query -S /usr/bin/le 2>/dev/null || true)
    case "$owner" in le-cli:\ /usr/bin/le) ;; *)
        echo '/usr/bin/le exists and is not owned by le-cli; refusing to overwrite it.' >&2
        exit 1;; esac
fi
exit 0
'''
        (root / 'DEBIAN/preinst').write_text(preinst, encoding='utf-8')
        (root / 'DEBIAN/preinst').chmod(0o755)
        (docs / 'copyright').write_text(f"License: {data['license']}\n\n" + license_text(data), encoding='utf-8')
        if metadata.get('license_artifact'):
            notices = binary.parent / metadata['license_artifact']
            if notices.parent != binary.parent or sha256(notices) != metadata.get('license_sha256'):
                raise ValueError('Bundled dependency license artifact/hash mismatch')
            shutil.copyfile(notices, docs / 'THIRD_PARTY_LICENSES')
        elif not data.get('test_fixture'):
            raise ValueError('Rebuild with current tooling to include bundled dependency license notices.')
        (docs / 'README.Debian').write_text('Command: /usr/bin/le\nPackage: le-cli\nThe unrelated Debian le editor cannot coexist at this command path.\n', encoding='utf-8')
        date = datetime.datetime.fromtimestamp(args.epoch, datetime.timezone.utc)
        changelog = (f'le-cli ({deb_version(args.version)}) stable; urgency=medium\n\n'
                     '  * Package the existing le application without changing its CLI.\n\n'
                     f" -- {data['maintainer_name']} <{data['maintainer_email']}>  {date.strftime('%a, %d %b %Y %H:%M:%S +0000')}\n")
        (docs / 'changelog.gz').write_bytes(gzip.compress(changelog.encode(), mtime=args.epoch))
        man = root / 'usr/share/man/man1'
        man.mkdir(parents=True)
        manual = ('.TH LE 1 "' + date.strftime('%Y-%m-%d') + '" "' + version(args.version) + '"\n'
                  '.SH NAME\nle \\- enhanced directory listing\n.SH SYNOPSIS\n.B le\n[directory] [options]\n'
                  '.SH DESCRIPTION\nLists directory contents with file icons and optional metadata.\n'
                  '.SH OPTIONS\n.TP\n.B \\-r, \\-\\-recurse\nTraverse subdirectories.\n.TP\n.B \\-n, \\-\\-depth N\nLimit recursion depth; ignored without \\-r.\n'
                  '.TP\n.B \\-d, \\-\\-only-dirs\nPrint directories only.\n.TP\n.B \\-p, \\-\\-show-permissions\nShow permissions.\n'
                  '.TP\n.B \\-o, \\-\\-show-owner\nShow ownership.\n.TP\n.B \\-t, \\-\\-show-time\nShow modification times.\n'
                  '.TP\n.B \\-s, \\-\\-show-size\nShow file and directory sizes.\n.TP\n.B \\-\\-output-json PATH\nAlso save the hierarchy, using absolute directory keys and filename values.\n'
                  '.SH EXAMPLES\nle \\-portn 3 \\-\\-output-json tree.json\n')
        (man / 'le.1.gz').write_bytes(gzip.compress(manual.encode(), mtime=args.epoch))
        md5sums = ''.join(hashlib.md5(path.read_bytes(), usedforsecurity=False).hexdigest() + '  ' + path.relative_to(root).as_posix() + '\n'
                          for path in sorted((root / 'usr').rglob('*')) if path.is_file())
        (root / 'DEBIAN/md5sums').write_text(md5sums, encoding='ascii')
        for path in root.rglob('*'):
            if path.is_dir():
                path.chmod(0o755)
            elif path.name not in ('le', 'preinst'):
                path.chmod(0o644)
            os.utime(path, (args.epoch, args.epoch), follow_symlinks=False)
        run('dpkg-deb', '--root-owner-group', '--uniform-compression', '-Zxz', '--build', root, artifact,
            env=dict(os.environ, SOURCE_DATE_EPOCH=str(args.epoch)))
    run('dpkg-deb', '--info', artifact)
    run('dpkg-deb', '--contents', artifact)
    print(artifact)


def apt_repository(args):
    data = config(args.config, ('apt_base_url', 'apt_signing_fingerprint'))
    if not data['apt_base_url'].startswith('https://'):
        raise ValueError('The published APT repository must use HTTPS')
    fingerprint = data['apt_signing_fingerprint'].replace(' ', '').upper()
    if not re.fullmatch(r'[0-9A-F]{40,64}', fingerprint):
        raise ValueError('Use the full trusted OpenPGP fingerprint')
    if not os.environ.get('GNUPGHOME'):
        raise ValueError('Use a dedicated, temporary GNUPGHOME for release signing')
    run('gpg', '--batch', '--list-secret-keys', fingerprint, stdout=subprocess.DEVNULL)
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    conf = root / 'conf'
    conf.mkdir(exist_ok=True)
    suite = data.get('apt_suite', 'stable')
    if not re.fullmatch(r'[a-z][a-z0-9-]*', suite):
        raise ValueError('Invalid APT suite')
    packages = sorted(Path(args.packages).glob('le-cli_*.deb'))
    if not packages:
        raise ValueError('No .deb packages were supplied')
    architectures = set()
    for package in packages:
        architecture = run('dpkg-deb', '--field', package, 'Architecture', capture_output=True, text=True).stdout.strip()
        if architecture not in ('amd64', 'arm64'):
            raise ValueError('Unsupported package architecture')
        architectures.add(architecture)
    for existing in (root / 'dists' / suite / 'main').glob('binary-*'):
        architectures.add(existing.name.removeprefix('binary-'))
    distributions = (f'Origin: {data.get("publisher") or "le-cli"}\nLabel: le-cli\nSuite: {suite}\n'
                     f'Codename: {suite}\nArchitectures: {" ".join(sorted(architectures))}\nComponents: main\n'
                     f'Description: le CLI APT repository\nSignWith: {fingerprint}\nValidFor: 30d\n')
    (conf / 'distributions').write_text(distributions, encoding='utf-8')
    for package in packages:
        run('reprepro', '--basedir', root, '--keepunreferencedfiles', 'includedeb', suite, package)
    run('reprepro', '--basedir', root, 'export')
    public_key = run('gpg', '--batch', '--export', fingerprint, capture_output=True).stdout
    (root / 'le-archive-keyring.gpg').write_bytes(public_key)
    (root / 'keys').mkdir(exist_ok=True)
    (root / 'keys' / (fingerprint + '.gpg')).write_bytes(public_key)
    release = root / 'dists' / suite
    run('gpgv', '--keyring', root / 'le-archive-keyring.gpg', release / 'InRelease')
    run('gpgv', '--keyring', root / 'le-archive-keyring.gpg', release / 'Release.gpg', release / 'Release')
    (root / 'KEY_FINGERPRINT').write_text(fingerprint + '\n', encoding='ascii')
    # GitHub Pages publishes a snapshot of this directory after signature checks.
    (root / '.nojekyll').touch()
    print(root)


def validate_public(args):
    required = ('github_owner', 'github_repository', 'publisher', 'winget_identifier',
                'license', 'license_file', 'maintainer_name', 'maintainer_email')
    if getattr(args, 'require_apt', False):
        required += ('apt_base_url', 'apt_signing_fingerprint')
    data = config(args.config, required)
    if data.get('test_fixture'):
        raise ValueError('Synthetic test metadata must never be published as project metadata.')
    license_text(data)
    version(args.version)
    print('Release metadata is complete. APT publication separately requires its protected signing key and repository settings.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build_parser = commands.add_parser('build')
    build_parser.add_argument('--version', required=True)
    build_parser.add_argument('--arch', choices=['amd64', 'arm64'])
    build_parser.add_argument('--output', default=str(ROOT / 'release'))
    build_parser.add_argument('--epoch', type=int, default=default_epoch())
    build_parser.set_defaults(function=build)
    checksum_parser = commands.add_parser('checksums')
    checksum_parser.add_argument('directory')
    checksum_parser.set_defaults(function=checksums)
    bundle_parser = commands.add_parser('bundle')
    bundle_parser.add_argument('--output', default=str(ROOT / 'release'))
    bundle_parser.add_argument('--epoch', type=int, default=default_epoch())
    bundle_parser.set_defaults(function=bundle)
    for name, function in [('winget', winget), ('deb', deb), ('apt', apt_repository), ('validate-public', validate_public)]:
        command = commands.add_parser(name)
        command.add_argument('--config')
        if name != 'apt':
            command.add_argument('--version', required=True)
        if name == 'validate-public':
            command.add_argument('--require-apt', action='store_true', help='Also require production APT signing metadata')
        if name == 'winget':
            command.add_argument('--artifacts', required=True)
            command.add_argument('--output', required=True)
        elif name == 'deb':
            command.add_argument('--binary', required=True)
            command.add_argument('--output', required=True)
            command.add_argument('--epoch', type=int, default=default_epoch())
        elif name == 'apt':
            command.add_argument('--packages', required=True)
            command.add_argument('--output', required=True)
        command.set_defaults(function=function)
    args = parser.parse_args()
    try:
        args.function(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Packaging failed: {error}\n')


if __name__ == '__main__':
    main()
