import json
import os
from pathlib import Path

configuration = json.loads((Path(__file__).parent / 'distribution.json').read_text(encoding='utf-8'))
entries = [
    {'runner': 'windows-2025', 'platform': 'windows', 'arch': 'amd64', 'python': '3.10'},
    {'runner': 'ubuntu-22.04', 'platform': 'linux', 'arch': 'amd64', 'python': '3.10'},
]
if os.environ.get('LE_ENABLE_ARM64', '').lower() == 'true' and 'arm64' in configuration['architectures']:
    entries += [
        {'runner': 'windows-11-arm', 'platform': 'windows', 'arch': 'arm64', 'python': '3.12'},
        {'runner': 'ubuntu-24.04-arm', 'platform': 'linux', 'arch': 'arm64', 'python': '3.12'},
    ]
print(json.dumps({'include': entries}))
