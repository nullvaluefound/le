"""Local build helper; creates only an isolated cache environment, never apt-installs on the host."""
from pathlib import Path
import subprocess
import sys
import venv

root = Path(__file__).resolve().parents[1]
environment = Path.home() / '.cache/le-distribution-build'
if not (environment / 'bin/python').exists():
    venv.create(environment, with_pip=True)
python = environment / 'bin/python'
subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(root / 'packaging/requirements-build.txt'), '-r', str(root / 'requirements.txt')], check=True)
subprocess.run([str(python), str(root / 'packaging/release.py'), 'build', '--version', '1.0.0', '--output', str(root / 'release')], check=True)
