"""Extract packaging utilities into a private cache; never modify host apt/dpkg state."""
from pathlib import Path
import os
import subprocess
import sys

cache = Path.home() / '.cache/le-distribution-tools'
archives = cache / 'archives'
extracted = cache / 'root'
archives.mkdir(parents=True, exist_ok=True)
extracted.mkdir(exist_ok=True)
packages = ['reprepro', 'libgpgme11t64', 'libarchive13t64', 'libdb5.3t64']
subprocess.run(['apt-get', 'download', *packages], cwd=archives, check=True)
for archive in archives.glob('*.deb'):
    subprocess.run(['dpkg-deb', '--extract', str(archive), str(extracted)], check=True)
environment = dict(os.environ, PATH=str(extracted / 'usr/bin') + os.pathsep + os.environ['PATH'],
                   LD_LIBRARY_PATH=str(extracted / 'usr/lib/x86_64-linux-gnu'))
subprocess.run([sys.executable, str(Path(__file__).with_name('test_apt.py')),
                '--binary', str(Path(__file__).resolve().parents[1] / 'release/le-linux-amd64'),
                '--version', '1.0.0'], env=environment, check=True)
