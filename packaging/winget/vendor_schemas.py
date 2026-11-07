"""Refresh schemas from a fixed official Microsoft revision, never from moving master."""
import hashlib
import json
from pathlib import Path
import urllib.request

revision = 'afc9a471496c4cd80ac363df269362f84ea5a457'
base = f'https://raw.githubusercontent.com/microsoft/winget-cli/{revision}'
output = Path(__file__).parent / 'schemas'
output.mkdir(exist_ok=True)
hashes = {}
for kind in ('version', 'installer', 'defaultLocale'):
    name = f'manifest.{kind}.1.28.0.json'
    data = urllib.request.urlopen(f'{base}/schemas/JSON/manifests/v1.28.0/{name}', timeout=30).read()
    json.loads(data)
    (output / name).write_bytes(data)
    hashes[name] = hashlib.sha256(data).hexdigest()
license_bytes = urllib.request.urlopen(base + '/LICENSE', timeout=30).read()
(output / 'UPSTREAM-LICENSE.txt').write_bytes(license_bytes)
(output / 'SOURCE.json').write_text(json.dumps({'repository': 'microsoft/winget-cli', 'revision': revision, 'sha256': hashes}, indent=2), encoding='utf-8')
print(json.dumps(hashes, indent=2))
