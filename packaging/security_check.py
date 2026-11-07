"""Prevent accidental private signing-key commits; release secrets stay in protected environments."""
from pathlib import Path
import re
import subprocess

root = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=root).split(b'\0')
private = re.compile(rb'^-----BEGIN (?:PGP PRIVATE KEY BLOCK|(?:RSA |EC |OPENSSH )?PRIVATE KEY)-----\r?$', re.M)
for name in files:
    if not name:
        continue
    path = root / name.decode('utf-8')
    if path.is_file() and private.search(path.read_bytes()):
        raise SystemExit('Private key material must not be committed: ' + str(path.relative_to(root)))
print('No committed armored private-key material detected.')
