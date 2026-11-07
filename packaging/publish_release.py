"""Publish tested assets only after a complete draft release has been assembled."""
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import release

parser = argparse.ArgumentParser()
parser.add_argument('--tag', required=True)
parser.add_argument('--artifacts', required=True)
args = parser.parse_args()
version = release.version(args.tag)
release.validate_public(argparse.Namespace(config=None, version=version))
root = release.ROOT
directory = Path(args.artifacts).resolve()
data = release.config()
repository = data['github_owner'] + '/' + data['github_repository']
if os.environ.get('GITHUB_REPOSITORY') != repository:
    raise SystemExit('Release workflow repository does not match configured project ownership.')
tag_commit = subprocess.check_output(['git', 'rev-list', '-n', '1', args.tag], text=True).strip()
subprocess.run(['git', 'merge-base', '--is-ancestor', tag_commit, 'HEAD'], check=True)
source = subprocess.check_output(['git', 'show', args.tag + ':main.py'])
import hashlib
source_hash = hashlib.sha256(source).hexdigest()
metadata = list(directory.glob('*.build.json'))
if not metadata:
    raise SystemExit('No native build metadata found')
seen = set()
for path in metadata:
    record = json.loads(path.read_text(encoding='utf-8'))
    artifact = directory / record['artifact']
    if artifact.parent != directory or not artifact.is_file():
        raise SystemExit('Invalid artifact path in build metadata')
    if record['version'] != version or record['source_sha256'] != source_hash or record['sha256'] != release.sha256(artifact):
        raise SystemExit('Release tag/source/version/hash validation failed')
    notices = directory / record['license_artifact']
    if notices.parent != directory or release.sha256(notices) != record['license_sha256']:
        raise SystemExit('Bundled runtime/dependency license integrity check failed')
    target = release.identity(artifact)
    if target != (record['os'], record['architecture']):
        raise SystemExit('Binary header/build metadata mismatch')
    seen.add(target)
if not {('windows', 'amd64'), ('linux', 'amd64')}.issubset(seen):
    raise SystemExit('Both tested AMD64 platforms are required before publication')
for binary in directory.glob('le-linux-*'):
    if not re.fullmatch(r'le-linux-(amd64|arm64)', binary.name):
        continue
    release.deb(argparse.Namespace(config=None, binary=str(binary), version=version, output=str(directory), epoch=int(os.environ['SOURCE_DATE_EPOCH'])))
manual_files = ['install.ps1', 'uninstall.ps1', 'install.bat', 'uninstall.bat', 'install.sh', 'uninstall.sh']
for name in manual_files:
    shutil.copyfile(root / name, directory / name)
shutil.copyfile(root / 'packaging/setup-apt.sh', directory / 'setup-apt.sh')
shutil.copyfile(root / 'docs/DISTRIBUTION.md', directory / 'DISTRIBUTION.md')
shutil.copyfile(root / 'LICENSE', directory / 'LICENSE')
with zipfile.ZipFile(directory / 'le-manual-installers.zip', 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for name in manual_files + ['setup-apt.sh', 'DISTRIBUTION.md', 'LICENSE']:
        archive.write(directory / name, name)
release.checksums(argparse.Namespace(directory=str(directory)))
existing = subprocess.run(['gh', 'release', 'view', args.tag, '--repo', repository, '--json', 'isDraft'], capture_output=True, text=True)
if existing.returncode == 0 and not json.loads(existing.stdout)['isDraft']:
    raise SystemExit('A public release with this tag already exists. Published binaries are immutable; use a new version.')
if existing.returncode != 0:
    subprocess.run(['gh', 'release', 'create', args.tag, '--repo', repository, '--draft', '--title', 'le ' + version,
                    '--notes', 'Native binaries, manual installers, Debian packages, and SHA-256 checksums. Package-manager availability is documented in DISTRIBUTION.md.'], check=True)
assets = [str(path) for path in sorted(directory.iterdir()) if path.is_file()]
subprocess.run(['gh', 'release', 'upload', args.tag, '--repo', repository, '--clobber', *assets], check=True)
# The published event fires only after all hashes and binaries are uploaded.
subprocess.run(['gh', 'release', 'edit', args.tag, '--repo', repository, '--draft=false'], check=True)
print(f'https://github.com/{repository}/releases/tag/{args.tag}')
