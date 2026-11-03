"""Require explicit cloud support or explicit local-only packaging."""

import re


def validate_cloud_config(client_id, client_secret, disabled=False):
    if disabled:
        if client_id or client_secret:
            raise ValueError(
                "Local-only build must not include Google OAuth credentials"
            )
        return
    if not client_id or not client_secret:
        raise ValueError(
            "Cloud builds require GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET; set BLOOM_CLOUD_DISABLED=1 for an explicit local-only build"
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]+\.apps\.googleusercontent\.com", client_id):
        raise ValueError("Invalid GOOGLE_OAUTH_CLIENT_ID")
