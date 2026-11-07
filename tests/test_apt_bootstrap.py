import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == 'nt' or not shutil.which('gpg'), 'Linux GPG bootstrap test')
class AptBootstrapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='le-bootstrap-key-')
        cls.base = Path(cls.temporary.name)
        cls.signing = cls.base / 'temporary-test-gnupg'
        cls.signing.mkdir(mode=0o700)
        cls.environment = dict(os.environ, GNUPGHOME=str(cls.signing))
        subprocess.run(['gpg', '--batch', '--pinentry-mode', 'loopback', '--passphrase', '', '--quick-generate-key',
                        'LE Bootstrap Test Fixture <test-fixture@example.invalid>', 'ed25519', 'sign', '1d'],
                       env=cls.environment, check=True, capture_output=True)
        listing = subprocess.check_output(['gpg', '--batch', '--with-colons', '--list-secret-keys'], env=cls.environment, text=True)
        cls.fingerprint = next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
        cls.public_key = cls.base / 'public.gpg'
        cls.public_key.write_bytes(subprocess.check_output(['gpg', '--batch', '--export', cls.fingerprint], env=cls.environment))

    @classmethod
    def tearDownClass(cls):
        subprocess.run(['gpgconf', '--kill', 'gpg-agent'], env=cls.environment, check=False)
        cls.temporary.cleanup()

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='le-bootstrap-root-')
        self.base = Path(self.temporary.name)
        self.root = self.base / 'isolated-root'
        self.mock_bin = self.base / 'mock-https-download'
        self.mock_bin.mkdir()
        curl = self.mock_bin / 'curl'
        curl.write_text('#!/usr/bin/env bash\nset -eu\nif [ "${LE_TEST_CURL_FAIL:-0}" = 1 ]; then exit 22; fi\ncp -- "$LE_TEST_PUBLIC_KEY" "${@: -1}"\n', encoding='utf-8')
        curl.chmod(0o755)
        self.environment = dict(os.environ, PATH=str(self.mock_bin) + os.pathsep + os.environ['PATH'], LE_TEST_PUBLIC_KEY=str(self.public_key))
        self.key = self.root / 'etc/apt/keyrings/le-archive-keyring.gpg'
        self.source = self.root / 'etc/apt/sources.list.d/le.sources'

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *args, success=True, environment=None):
        result = subprocess.run(['bash', str(ROOT / 'packaging/setup-apt.sh'), '--root', str(self.root), *args],
                                env=environment or self.environment, capture_output=True, text=True)
        if success:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        else:
            self.assertNotEqual(0, result.returncode)
        return result

    def test_pinned_key_idempotence_and_separate_repository_removal(self):
        self.invoke('--fingerprint', self.fingerprint)
        first = self.source.read_bytes()
        self.assertIn(b'Signed-By:', first)
        self.assertIn(b'https://nullvaluefound.github.io/le', first)
        self.assertEqual(self.public_key.read_bytes(), self.key.read_bytes())
        self.invoke('--fingerprint', self.fingerprint)
        self.assertEqual(first, self.source.read_bytes())
        unrelated = self.source.parent / 'keep-user.sources'
        unrelated.write_bytes(b'user configuration')
        self.invoke('--remove-repository')
        self.assertFalse(self.source.exists())
        self.assertFalse(self.key.exists())
        self.assertEqual(b'user configuration', unrelated.read_bytes())
        self.invoke('--remove-repository')

    def test_wrong_key_or_insecure_url_never_writes_configuration(self):
        self.invoke('--fingerprint', '0' * 40, success=False)
        self.assertFalse(self.source.exists())
        self.invoke('--fingerprint', self.fingerprint, '--url', 'http://example.invalid', success=False)
        self.assertFalse(self.source.exists())

    def test_failed_key_refresh_preserves_previous_configuration(self):
        self.invoke('--fingerprint', self.fingerprint)
        previous = (self.key.read_bytes(), self.source.read_bytes())
        failed_environment = dict(self.environment, LE_TEST_CURL_FAIL='1')
        self.invoke('--fingerprint', self.fingerprint, environment=failed_environment, success=False)
        self.assertEqual(previous, (self.key.read_bytes(), self.source.read_bytes()))

    def test_user_modified_sources_are_preserved(self):
        self.invoke('--fingerprint', self.fingerprint)
        self.source.write_bytes(self.source.read_bytes() + b'# user change\n')
        self.invoke('--remove-repository', success=False)
        self.assertIn(b'# user change', self.source.read_bytes())


if __name__ == '__main__':
    unittest.main()
