"""Produce clearly marked synthetic metadata solely for installer/CI tests."""
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('output')
parser.add_argument('--fingerprint')
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
data = json.loads((root / 'packaging/distribution.json').read_text(encoding='utf-8'))
data.update(test_fixture=True, publisher='LE Distribution Test Fixture', winget_identifier='LeDistributionTests.Le',
            license='LicenseRef-Packaging-Test-Only', license_file='tests/fixtures/PACKAGING-TEST-LICENSE.txt',
            maintainer_name='LE Packaging Test Fixture', maintainer_email='test-fixture@example.invalid',
            apt_base_url='https://nullvaluefound.github.io/le', apt_signing_fingerprint=args.fingerprint)
Path(args.output).write_text(json.dumps(data, indent=2), encoding='utf-8')
