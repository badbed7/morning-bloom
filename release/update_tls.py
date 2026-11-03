"""Verified update HTTPS using native Windows chain building, without global SSL patches."""
import ssl
import sys
import urllib.error


def create_context(cafile=None):
    if sys.platform == 'win32':
        # Included in EXE and BAT bundles. Never silently disable verification or
        # fall back to the OpenSSL chain builder that failed on affected PCs.
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if cafile is not None:
            context.load_verify_locations(cafile=cafile)
    else:
        context = ssl.create_default_context(cafile=cafile)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context


def backend():
    if sys.platform == 'win32':
        try:
            import truststore
            return f'Windows CryptoAPI / truststore {truststore.__version__}'
        except ImportError:
            return 'Windows CryptoAPI unavailable: truststore is missing; replace the full launcher ZIP'
    return f'Python default / {ssl.OPENSSL_VERSION}'


def describe_error(error):
    reason = error.reason if isinstance(error, urllib.error.URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return (f'TLS certificate verification failed: {reason}; '
                f'verify_code={getattr(reason, "verify_code", "unknown")}; '
                f'verify_message={getattr(reason, "verify_message", "unknown")}')
    return f'{type(error).__name__}: {error}'
