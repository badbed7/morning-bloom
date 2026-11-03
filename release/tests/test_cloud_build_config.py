import unittest
from build_cloud_config import validate_cloud_config


class CloudBuildConfig(unittest.TestCase):
    def test_cloud_build_rejects_missing_mismatched_and_malformed_configuration(self):
        for client, secret in (
            ("", ""),
            ("x.apps.googleusercontent.com", ""),
            ("", "secret"),
            ("invalid", "secret"),
        ):
            with self.assertRaises(ValueError):
                validate_cloud_config(client, secret)
        validate_cloud_config("x.apps.googleusercontent.com", "secret")

    def test_local_only_is_explicit_and_cannot_accidentally_ship_credentials(self):
        validate_cloud_config("", "", disabled=True)
        with self.assertRaises(ValueError):
            validate_cloud_config(
                "x.apps.googleusercontent.com", "secret", disabled=True
            )
