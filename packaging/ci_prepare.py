import os
from pathlib import Path
import subprocess
import sys

from release import version

requested = os.environ.get('REQUESTED_VERSION', '')
resolved = version(requested) if requested else subprocess.check_output([sys.executable, str(Path(__file__).with_name('app_version.py'))], text=True).strip()
epoch = subprocess.check_output(['git', 'show', '-s', '--format=%ct', 'HEAD'], text=True).strip()
assert epoch.isdigit()
with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as output:
    output.write(f'version={resolved}\nepoch={epoch}\n')
