import argparse
import json
from pathlib import Path
import subprocess

import jsonschema
import yaml

parser = argparse.ArgumentParser()
parser.add_argument('directory')
parser.add_argument('--winget-client', action='store_true')
args = parser.parse_args()
root = Path(__file__).resolve().parent
groups = {}
for path in Path(args.directory).rglob('*.yaml'):
    document = yaml.safe_load(path.read_text(encoding='utf-8-sig'))
    kind = document['ManifestType']
    schema = json.loads((root / 'winget/schemas' / f'manifest.{kind}.1.28.0.json').read_text(encoding='utf-8'))
    jsonschema.Draft7Validator(schema).validate(document)
    groups.setdefault(path.parent, []).append(document)
if not groups:
    raise SystemExit('No generated manifests found')
for directory, documents in groups.items():
    assert {item['ManifestType'] for item in documents} == {'version', 'installer', 'defaultLocale'}
    assert len({item['PackageIdentifier'] for item in documents}) == 1
    assert len({item['PackageVersion'] for item in documents}) == 1
    installer = next(item for item in documents if item['ManifestType'] == 'installer')
    assert installer['InstallerType'] == 'portable' and installer['Commands'] == ['le']
    for item in installer['Installers']:
        assert '/releases/download/v' in item['InstallerUrl'] and '/latest/' not in item['InstallerUrl']
    if args.winget_client:
        subprocess.run(['winget', 'validate', '--manifest', str(directory), '--disable-interactivity'], check=True)
print(f'Validated {len(groups)} complete WinGet manifest set(s), schema 1.28.0.')
