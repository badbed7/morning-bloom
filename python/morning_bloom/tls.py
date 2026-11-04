"""Verified Windows native trust for every game HTTPS request."""
import ssl
import sys


def create_context(cafile=None):
    if sys.platform == 'win32':
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        if cafile is not None:
            context.load_verify_locations(cafile=cafile)
    else:
        context = ssl.create_default_context(cafile=cafile)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return context
