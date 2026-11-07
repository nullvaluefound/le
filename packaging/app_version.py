import re
import subprocess
import sys
from pathlib import Path

output = subprocess.check_output([sys.executable, str(Path(__file__).resolve().parents[1] / 'main.py'), '--version'], text=True)
match = re.search(r'(\d+)\.(\d+)(?:\.(\d+))?\s*$', output)
if not match:
    raise SystemExit('Update packaging/app_version.py deliberately if the existing CLI version format changes.')
print('.'.join([match[1], match[2], match[3] or '0']))
