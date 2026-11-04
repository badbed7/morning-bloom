"""Windows native-chain regression fixture, also exercising frozen and isolated BAT launchers.

Creates temporary certificates and localhost servers only. No system CA store edits.
Run: PYTHONPATH=release python release/tools/verify_tls.py [--launcher EXE | --bat DIR]
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import ssl
import subprocess
import sys
import tempfile
from threading import Thread
import urllib.request
from uuid import uuid4

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import AuthorityInformationAccessOID, ExtendedKeyUsageOID, NameOID
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from update_tls import create_context


def key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def certificate(name, public_key, issuer, issuer_key, *, ca=False, aia=None, expired=False):
    now = datetime.now(timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    builder = (x509.CertificateBuilder().subject_name(subject)
        .issuer_name(issuer.subject if issuer else subject).public_key(public_key)
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=3))
        .not_valid_after(now - timedelta(days=1) if expired else now + timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(public_key), critical=False)
        .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key.public_key()), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False, key_encipherment=not ca,
            data_encipherment=False, key_agreement=False, key_cert_sign=ca, crl_sign=ca,
            encipher_only=None, decipher_only=None), critical=True))
    if not ca:
        builder = (builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(name)]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False))
    if aia:
        builder = builder.add_extension(x509.AuthorityInformationAccess([
            x509.AccessDescription(AuthorityInformationAccessOID.CA_ISSUERS,
                                  x509.UniformResourceIdentifier(aia))]), critical=False)
    return builder.sign(issuer_key, hashes.SHA256())


def pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM)


def private_pem(value):
    return value.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                               serialization.NoEncryption())


@contextmanager
def server(response, context=None):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header('Content-Type', 'application/pkix-cert' if context is None else 'application/json')
            self.send_header('Content-Length', str(len(response)))
            self.end_headers()
            self.wfile.write(response)
        def log_message(self, *args):
            pass
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    if context:
        instance.socket = context.wrap_socket(instance.socket, server_side=True)
    worker = Thread(target=instance.serve_forever, daemon=True)
    worker.start()
    try:
        yield instance.server_port
    finally:
        instance.shutdown()
        instance.server_close()
        worker.join(timeout=5)


def request(url, context):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                        urllib.request.HTTPSHandler(context=context))
    with opener.open(url, timeout=15) as response:
        return response.read()


def probe(args, url, root_file, log):
    if args.game:
        game = Path(args.game).resolve()
        command = [sys.executable, '-I', str(game)] if game.suffix == '.py' else [str(game)]
    elif args.launcher:
        command = [str(Path(args.launcher).resolve())]
    else:
        script = (Path(args.bat) / 'release/launcher.py' if args.bat
                  else Path(__file__).resolve().parents[1] / 'launcher.py')
        command = [sys.executable, '-I', str(script.resolve())]
    command += ['--cloud-tls-probe' if args.game else '--tls-probe', url, '--diagnostic-log', str(log)]
    if root_file:
        command += ['--tls-ca', str(root_file)]
    run = subprocess.run(command, timeout=60, stdin=subprocess.DEVNULL)
    details = log.read_text(encoding='utf-8') if log.exists() else 'diagnostic log missing'
    print(details.strip(), flush=True)
    return run.returncode


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--launcher')
    parser.add_argument('--bat')
    parser.add_argument('--game')
    args = parser.parse_args()
    native = sys.platform == 'win32'
    if (args.launcher or args.bat or args.game) and not native:
        raise SystemExit('Packaged native chain checks require Windows')
    with tempfile.TemporaryDirectory(prefix='bloom-tls-') as temporary:
        folder = Path(temporary)
        root_key, issuer_key = key(), key()
        root = certificate('Bloom TLS test root ' + uuid4().hex, root_key.public_key(), None, root_key, ca=True)
        issuer = certificate('Bloom TLS test intermediate', issuer_key.public_key(), root, root_key, ca=True)
        root_file = folder / 'root.pem'
        root_file.write_bytes(pem(root))
        with server(issuer.public_bytes(serialization.Encoding.DER)) as aia_port:
            for scenario in ('missing-intermediate', 'valid-chain', 'untrusted-root', 'wrong-host', 'expired'):
                leaf_key = key()
                hostname = 'wrong.invalid' if scenario == 'wrong-host' else 'localhost'
                leaf = certificate(hostname, leaf_key.public_key(), issuer, issuer_key,
                    aia=f'http://127.0.0.1:{aia_port}/{uuid4().hex}.der', expired=scenario == 'expired')
                chain_file, key_file = folder / 'chain.pem', folder / 'key.pem'
                chain_file.write_bytes(pem(leaf) + (b'' if scenario == 'missing-intermediate' else pem(issuer)))
                key_file.write_bytes(private_pem(leaf_key))
                tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                tls.load_cert_chain(chain_file, key_file)
                with server(b'{"verified": true}', tls) as port:
                    url = f'https://localhost:{port}/'
                    if scenario == 'missing-intermediate':
                        # Reproduce the reported issuer failure before Windows can cache AIA.
                        old = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                        old.load_verify_locations(cafile=root_file)
                        try:
                            request(url, old)
                        except Exception as error:
                            reason = getattr(error, 'reason', error)
                            assert isinstance(reason, ssl.SSLCertVerificationError), error
                            print('OLD OpenSSL: missing issuer reproduced: ' + str(reason), flush=True)
                        else:
                            raise AssertionError('Old chain unexpectedly succeeded')
                        if not native:
                            print('SKIP native Windows intermediate retrieval on this platform', flush=True)
                            continue
                    trusted = scenario != 'untrusted-root'
                    expected = scenario in ('missing-intermediate', 'valid-chain')
                    if native:
                        actual = probe(args, url, root_file if trusted else None, folder / 'probe.log') == 0
                    else:
                        try:
                            request(url, create_context(cafile=str(root_file) if trusted else None))
                            actual = True
                        except Exception as error:
                            reason = getattr(error, 'reason', error)
                            assert isinstance(reason, ssl.SSLCertVerificationError), error
                            actual = False
                    assert actual == expected, f'{scenario}: expected {expected}, got {actual}'
                    print(f'PASS {scenario}: {"verified" if actual else "rejected"}', flush=True)
    print('TLS regression checks passed', flush=True)


if __name__ == '__main__':
    main()
