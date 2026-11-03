"""Native TLS wiring and self-contained packaging; real handshakes run in Windows CI."""
import argparse
import io
import json
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from unittest.mock import patch

from bundle_updater import copy_bat_updater
from update_tls import create_context, describe_error
from update_core import _read_json, download


class UpdateTLS(unittest.TestCase):
    def test_context_always_requires_hostname_and_certificate(self):
        context = create_context()
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_windows_uses_native_context(self):
        import truststore
        with patch('update_tls.sys.platform', 'win32'), patch('truststore.SSLContext', wraps=truststore.SSLContext) as factory:
            context = create_context()
        factory.assert_called_once_with(ssl.PROTOCOL_TLS_CLIENT)
        self.assertTrue(context.check_hostname)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)

    def test_json_and_payload_use_the_verified_context(self):
        for payload in (False, True):
            with self.subTest(payload=payload), tempfile.TemporaryDirectory() as tmp:
                context = create_context()
                content = b'abc' if payload else b'{"ok":true}'
                response = io.BytesIO(content)
                response.url = 'https://github.com/badbed7/morning-bloom/releases/download/v0.8.13/update.json'
                with patch('update_core.create_context', return_value=context), \
                     patch('urllib.request.urlopen', return_value=response) as request:
                    if payload:
                        import hashlib
                        data = dict(url=response.url, size=3, sha256=hashlib.sha256(content).hexdigest())
                        download(data, Path(tmp) / 'payload.zip')
                    else:
                        self.assertEqual(_read_json(response.url), {'ok': True})
                self.assertIs(request.call_args.kwargs['context'], context)

    def test_certificate_failure_keeps_verification_details_and_removes_partial_zip(self):
        failure = ssl.SSLCertVerificationError('unable to get issuer certificate')
        failure.verify_code = 2
        failure.verify_message = 'unable to get issuer certificate'
        error = urllib.error.URLError(failure)
        self.assertIn('verify_code=2', describe_error(error))
        self.assertIn('unable to get issuer', describe_error(error))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bad.zip'
            path.write_bytes(b'partial')
            with patch('urllib.request.urlopen', side_effect=error), self.assertRaises(urllib.error.URLError):
                download(dict(url='https://github.com/test', size=10), path)
            self.assertFalse(path.exists())

    def test_bat_includes_native_backend_and_license_before_pip_setup(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy_bat_updater(tmp)
            for name in ('update_tls.py', 'truststore/__init__.py', 'truststore/_windows.py', 'truststore/LICENSE'):
                self.assertTrue((Path(tmp) / name).is_file(), name)

    def test_vendored_bat_imports_in_isolated_python(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            copy_bat_updater(folder)
            log = folder / 'probe.log'
            result = subprocess.run([sys.executable, '-I', str(folder / 'launcher.py'),
                '--tls-probe', 'https://example.com/', '--diagnostic-log', str(log)],
                capture_output=True, timeout=20)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertTrue(log.exists(), result.stderr)
            self.assertIn('restricted to HTTPS loopback', log.read_text())

    def test_tls_probe_cannot_contact_arbitrary_external_hosts(self):
        from launcher import diagnose
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'probe.log'
            args = argparse.Namespace(tls_probe='https://example.com/', tls_ca=None,
                                      diagnostic_log=log, download_test=False)
            self.assertEqual(diagnose(args), 1)
            self.assertIn('restricted to HTTPS loopback', log.read_text())

    def test_diagnostics_never_install_or_touch_garden(self):
        from launcher import diagnose
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / 'probe.log'
            args = argparse.Namespace(tls_probe=None, tls_ca=None, diagnostic_log=log, download_test=False)
            with patch('launcher.read_latest', return_value={'version': '0.8.13'}) as read, \
                 patch('launcher.Installer') as installer:
                self.assertEqual(diagnose(args), 0)
            self.assertEqual(read.call_count, 2)
            installer.assert_not_called()
            self.assertIn('EXE latest: 0.8.13', log.read_text())
            self.assertIn('BAT latest: 0.8.13', log.read_text())
