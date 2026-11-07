import hashlib
import argparse
import importlib.util
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('le_release', ROOT / 'packaging/release.py')
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


class MetadataTests(unittest.TestCase):
    def test_versions_and_untrusted_tag_rejection(self):
        self.assertEqual('1.2.3', release.version('v1.2.3'))
        self.assertEqual('1.2.3~rc.1', release.deb_version('v1.2.3-rc.1'))
        for value in ['latest', '../1.2.3', '1.2', 'v1.2.3;exit', '-1.2.3']:
            with self.assertRaises(ValueError):
                release.version(value)

    def test_publication_refuses_missing_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.json'
            path.write_text('{"publisher": null}', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'publisher'):
                release.config(path, ('publisher',))

    def test_application_source_is_not_rewritten_by_packaging(self):
        result = subprocess.run([sys.executable, str(ROOT / 'main.py'), '--version'], capture_output=True)
        self.assertEqual(0, result.returncode)
        self.assertRegex(result.stdout, rb'\d+\.\d+')

    def test_native_publication_does_not_require_apt_credentials(self):
        data = release.config()
        data['apt_signing_fingerprint'] = None
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'config.json'
            path.write_text(json.dumps(data), encoding='utf-8')
            args = argparse.Namespace(config=path, version='1.0.0', require_apt=False)
            release.validate_public(args)
            args.require_apt = True
            with self.assertRaisesRegex(ValueError, 'apt_signing_fingerprint'):
                release.validate_public(args)

    def test_build_records_match_source_binary_headers_and_licenses(self):
        records = list((ROOT / 'release').glob('*.build.json'))
        if not records:
            self.skipTest('Build a native release artifact first')
        for path in records:
            record = json.loads(path.read_text(encoding='utf-8'))
            binary = path.parent / record['artifact']
            self.assertEqual(release.sha256(ROOT / 'main.py'), record['source_sha256'])
            self.assertEqual(release.sha256(binary), record['sha256'])
            self.assertEqual((record['os'], record['architecture']), release.identity(binary))
            self.assertEqual(release.sha256(path.parent / record['license_artifact']), record['license_sha256'])


class ManualInstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.windows = os.name == 'nt'
        arch = 'arm64' if platform.machine().lower() in ('arm64', 'aarch64') else 'amd64'
        cls.binary = ROOT / 'release' / (f'le-windows-{arch}.exe' if cls.windows else f'le-linux-{arch}')
        if not cls.binary.exists():
            raise unittest.SkipTest('Build the native release artifact first')
        cls.digest = release.sha256(cls.binary)

    def setUp(self):
        # Tests never change the actual user's HOME, registry PATH, or /usr/bin.
        self.temporary = tempfile.TemporaryDirectory(prefix='le-installer-test-', dir=ROOT if os.name == 'nt' else None)
        self.base = Path(self.temporary.name)
        self.command_dir = self.base / 'command directory'
        self.state = self.base / 'state'
        self.test_home = self.base / 'profile directory'
        self.test_home.mkdir()
        self.path_store = self.base / 'user-path.txt'
        self.path_store.write_text('C:\\Existing;C:\\Unrelated', encoding='utf-8')
        self.target = self.command_dir / ('le.exe' if self.windows else 'le')
        self.original_profile = b'# user settings without trailing newline'
        for name in ['.profile', '.bashrc', '.zshrc']:
            (self.test_home / name).write_bytes(self.original_profile)

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, action, *extra, success=True, binary=None, environment=None):
        candidate = binary or self.binary
        digest = release.sha256(candidate)
        if self.windows:
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / (action + '.ps1')),
                       '-InstallDir', str(self.command_dir), '-StateDir', str(self.state), '-PathStore', str(self.path_store)]
            if action == 'install':
                command += ['-LocalBinary', str(candidate)]
                if '-ExpectedSha256' not in extra:
                    command += ['-ExpectedSha256', digest]
        else:
            command = ['bash', str(ROOT / (action + '.sh')), '--bin-dir', str(self.command_dir),
                       '--state-dir', str(self.state), '--home-dir', str(self.test_home)]
            if action == 'install':
                command += ['--binary', str(candidate)]
                if '--sha256' not in extra:
                    command += ['--sha256', digest]
        command += list(extra)
        result = subprocess.run(command, capture_output=True, text=True, env=environment)
        if success:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        else:
            self.assertNotEqual(0, result.returncode, result.stdout + result.stderr)
        return result

    def test_fresh_repeated_install_and_remove_preserves_unrelated_data(self):
        self.invoke('install')
        self.assertTrue(self.target.is_file())
        self.assertEqual(self.digest, release.sha256(self.target))
        self.invoke('install')
        unrelated = self.command_dir / 'keep-user-data.txt'
        unrelated.write_bytes(b'keep')
        if self.windows:
            path = self.path_store.read_text(encoding='utf-8')
            self.assertEqual(1, path.count(str(self.command_dir)))
        else:
            for name in ['.profile', '.bashrc', '.zshrc']:
                profile = self.test_home / name
                self.assertEqual(1, profile.read_text().count('# >>> le manual installer PATH >>>'))
            shell = subprocess.run(['bash', '--noprofile', '--norc', '-c', '. "$1"; command -v le', 'test', str(self.test_home / '.bashrc')], capture_output=True, text=True)
            self.assertEqual(str(self.target), shell.stdout.strip())
        self.invoke('uninstall')
        self.assertFalse(self.target.exists())
        self.assertEqual(b'keep', unrelated.read_bytes())
        if self.windows:
            self.assertEqual('C:\\Existing;C:\\Unrelated', self.path_store.read_text(encoding='utf-8'))
        else:
            for name in ['.profile', '.bashrc', '.zshrc']:
                self.assertEqual(self.original_profile, (self.test_home / name).read_bytes())
        self.invoke('uninstall')

    def test_unmanaged_conflict_is_never_replaced(self):
        self.command_dir.mkdir()
        self.target.write_bytes(b'unrelated executable')
        self.invoke('install', success=False)
        self.assertEqual(b'unrelated executable', self.target.read_bytes())

    def test_bad_checksum_does_not_install(self):
        option = '-ExpectedSha256' if self.windows else '--sha256'
        self.invoke('install', option, '0' * 64, success=False)
        self.assertFalse(self.target.exists())

    def test_missing_binary_can_still_be_uninstalled(self):
        self.invoke('install')
        self.target.unlink()
        self.invoke('uninstall')
        self.assertFalse(self.state.exists())

    def test_modified_owned_binary_is_preserved(self):
        self.invoke('install')
        self.target.write_bytes(b'user modification')
        self.invoke('uninstall', success=False)
        self.assertEqual(b'user modification', self.target.read_bytes())

    def test_package_manager_ownership_isolation(self):
        self.invoke('install')
        if self.windows:
            record_path = self.state / 'ownership.json'
            record = json.loads(record_path.read_text(encoding='utf-8-sig'))
            record['manager'] = 'winget'
            record_path.write_text(json.dumps(record), encoding='utf-8')
            result = self.invoke('uninstall', success=False)
            self.assertIn('WinGet', result.stderr)
            self.assertTrue(self.target.exists())
        else:
            record = self.state / 'ownership'
            record.write_text(record.read_text().replace('LE-MANUAL-BASH-1', 'APT-MANAGED'), encoding='utf-8')
            self.invoke('uninstall', success=False)
            self.assertTrue(self.target.exists())

    def test_real_old_version_upgrade_and_failed_upgrade_rollback(self):
        suffix = '.exe' if self.windows else ''
        old = ROOT / 'build/test-fixtures' / ('old-version' + suffix)
        broken = ROOT / 'build/test-fixtures' / ('failed-upgrade' + suffix)
        if not old.exists() or not broken.exists():
            self.skipTest('Run packaging/build_test_fixtures.py for native upgrade tests')
        self.invoke('install', binary=old)
        self.assertIn(b'0.9.0', subprocess.check_output([str(self.target), '--version']))
        self.invoke('install')
        self.assertEqual(self.digest, release.sha256(self.target))
        self.invoke('install', binary=broken, success=False)
        self.assertEqual(self.digest, release.sha256(self.target))
        self.invoke('uninstall')

    def test_existing_path_and_empty_user_directory_are_preserved(self):
        self.command_dir.mkdir()
        environment = None
        if self.windows:
            original = 'C:\\Existing;' + str(self.command_dir) + ';C:\\Unrelated'
            self.path_store.write_text(original, encoding='utf-8')
        else:
            environment = dict(os.environ, PATH=str(self.command_dir) + os.pathsep + os.environ['PATH'])
        self.invoke('install', environment=environment)
        self.invoke('uninstall', environment=environment)
        self.assertTrue(self.command_dir.is_dir())
        if self.windows:
            self.assertEqual(original, self.path_store.read_text(encoding='utf-8'))
        else:
            self.assertEqual(self.original_profile, (self.test_home / '.bashrc').read_bytes())
    @unittest.skipIf(os.name == 'nt', 'Bash profile test')
    def test_user_changes_outside_owned_path_block_are_preserved(self):
        self.invoke('install')
        profile = self.test_home / '.bashrc'
        with profile.open('ab') as stream:
            stream.write(b'\n# later user setting\n')
        self.invoke('uninstall')
        self.assertEqual(self.original_profile + b'\n# later user setting\n', profile.read_bytes())

    @unittest.skipIf(os.name == 'nt', 'Bash login profile test')
    def test_existing_bash_login_profile_precedence_and_restoration(self):
        for name in ('.bash_login', '.bash_profile'):
            with self.subTest(profile=name):
                profile = self.test_home / name
                profile.write_bytes(self.original_profile)
                self.invoke('install')
                shell = subprocess.run(['bash', '--noprofile', '--norc', '-c',
                                        '. "$1"; command -v le', 'test', str(profile)],
                                       capture_output=True, text=True)
                self.assertEqual(0, shell.returncode)
                self.assertEqual(str(self.target), shell.stdout.strip())
                self.invoke('uninstall')
                self.assertEqual(self.original_profile, profile.read_bytes())
                profile.unlink()
        self.assertFalse((self.test_home / '.bash_profile').exists())
        self.assertFalse((self.test_home / '.bash_login').exists())


if __name__ == '__main__':
    unittest.main()
