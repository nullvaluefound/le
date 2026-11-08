"""Test APT orchestration without touching host repositories or package state."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipIf(os.name == 'nt', 'Linux APT installer test')
class AptInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='le-apt-orchestration-')
        self.base = Path(self.temporary.name)
        self.bin = self.base / 'mock-bin'
        self.bin.mkdir()
        self.log = self.base / 'calls'
        self.log.touch()
        scripts = {
            'id': 'printf "%s\\n" "${LE_TEST_UID:-0}"',
            'dpkg': 'printf "%s\\n" "${LE_TEST_ARCH:-amd64}"',
            'dpkg-query': 'if [ "${LE_TEST_DEPS:-present}" = present ]; then printf installed; else printf not-installed; fi',
            'apt-get': r'''printf 'apt-get' >> "$LE_TEST_LOG"
printf ' %s' "$@" >> "$LE_TEST_LOG"
printf '\n' >> "$LE_TEST_LOG"
case "${LE_TEST_FAIL:-}" in
    update) if [ "${@: -1}" = update ]; then exit 17; fi;;
    prerequisites) if [ "$1" = install ] && [ "${@: -1}" != le-cli ]; then exit 18; fi;;
    package) if [ "${@: -1}" = le-cli ]; then exit 19; fi;;
esac''',
        }
        for name, text in scripts.items():
            path = self.bin / name
            path.write_text('#!/usr/bin/env bash\nset -eu\n' + text + '\n', encoding='utf-8')
            path.chmod(0o755)
        data = json.loads((ROOT / 'packaging/distribution.json').read_text(encoding='utf-8'))
        self.environment = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                                LE_TEST_LOG=str(self.log), LE_INSTALL_APT_URL=data['apt_base_url'],
                                LE_INSTALL_APT_SUITE=data['apt_suite'],
                                LE_INSTALL_APT_FINGERPRINT=data.get('apt_signing_fingerprint') or '0' * 40,
                                LE_INSTALL_APT_ARCHITECTURES='amd64')
        self.harness = self.base / 'run.sh'
        self.harness.write_text(r'''#!/usr/bin/env bash
set -euo pipefail
le_configure_apt_repository() {
    printf 'configure' >> "$LE_TEST_LOG"
    printf ' %s' "$@" >> "$LE_TEST_LOG"
    printf '\n' >> "$LE_TEST_LOG"
    [ "${LE_TEST_FAIL:-}" != configure ] || return 20
}
source "$LE_TEST_INSTALLER_BODY"
''', encoding='utf-8')
        self.environment['LE_TEST_INSTALLER_BODY'] = str(ROOT / 'packaging/linux/install-apt.body.sh')

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, *arguments, success=True, **environment):
        result = subprocess.run(['bash', str(self.harness), *arguments],
                                env=dict(self.environment, **environment), capture_output=True, text=True)
        if success:
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        else:
            self.assertNotEqual(0, result.returncode)
            self.assertNotIn('le-cli is installed.', result.stdout)
        return result

    def calls(self):
        return self.log.read_text(encoding='utf-8').splitlines()

    def test_dependencies_and_trust_complete_before_package_install(self):
        self.invoke(LE_TEST_DEPS='missing')
        calls = self.calls()
        self.assertEqual('apt-get -o APT::Update::Error-Mode=any update', calls[0])
        self.assertEqual('apt-get install -y --no-install-recommends ca-certificates curl gnupg', calls[1])
        self.assertIn('--fingerprint ' + self.environment['LE_INSTALL_APT_FINGERPRINT'], calls[2])
        self.assertEqual('apt-get -o APT::Update::Error-Mode=any update', calls[3])
        self.assertEqual('apt-get install -y --no-install-recommends le-cli', calls[4])

    def test_installed_prerequisites_are_not_reinstalled_or_upgraded(self):
        self.invoke()
        calls = self.calls()
        self.assertEqual(3, len(calls))
        self.assertTrue(calls[0].startswith('configure '))
        self.assertFalse(any('install -y --no-install-recommends ca-certificates' in call for call in calls))

    def test_bad_repository_trust_prevents_package_operations(self):
        self.invoke(success=False, LE_TEST_FAIL='configure')
        self.assertEqual(1, len(self.calls()))
        self.assertTrue(self.calls()[0].startswith('configure '))

    def test_failed_refresh_prevents_installation(self):
        self.invoke(success=False, LE_TEST_FAIL='update')
        self.assertFalse(any('install ' in call for call in self.calls()))

    def test_failed_prerequisites_prevent_repository_setup(self):
        self.invoke(success=False, LE_TEST_DEPS='missing', LE_TEST_FAIL='prerequisites')
        self.assertFalse(any(call.startswith('configure ') or call.endswith(' le-cli') for call in self.calls()))

    def test_package_failure_is_not_reported_as_success(self):
        self.invoke(success=False, LE_TEST_FAIL='package')
        self.assertTrue(self.calls()[-1].endswith(' le-cli'))

    def test_nonroot_unsupported_architecture_and_bad_options_make_no_changes(self):
        for environment, arguments in [({'LE_TEST_UID': '1000'}, []),
                                       ({'LE_TEST_ARCH': 'arm64'}, []),
                                       ({}, ['--unknown'])]:
            with self.subTest(environment=environment, arguments=arguments):
                self.invoke(*arguments, success=False, **environment)
                self.assertEqual([], self.calls())

    def test_help_works_without_root_or_package_operations(self):
        result = self.invoke('--help', LE_TEST_UID='1000')
        self.assertIn('sudo bash install-apt.sh', result.stdout)
        self.assertEqual([], self.calls())

    def test_missing_signing_pin_prevents_package_operations(self):
        self.invoke(success=False, LE_INSTALL_APT_FINGERPRINT='')
        self.assertEqual([], self.calls())


if __name__ == '__main__':
    unittest.main()
