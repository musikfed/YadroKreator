"""Trusted LAN export policy tests; this is NOT web user authentication."""
import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from export_policy import allow_private_export, permitted_networks


def req(addr, headers=None):
    return SimpleNamespace(remote_addr=addr, headers=headers or {},
                           scheme="http", host="192.168.0.100:62404")


class TrustedImageExportPolicyTests(unittest.TestCase):
    def test_existing_huananzhi_lan_is_allowed(self):
        self.assertTrue(allow_private_export(req("192.168.0.12")))
        self.assertTrue(allow_private_export(req("127.0.0.1")))
        self.assertFalse(allow_private_export(req("192.168.1.44")))

    def test_wan_and_spoofed_proxy_headers_are_rejected(self):
        self.assertFalse(allow_private_export(req("8.8.8.8")))
        self.assertFalse(allow_private_export(req("8.8.8.8",
                          {"X-Forwarded-For":"192.168.0.55"})))
        self.assertFalse(allow_private_export(req("192.168.0.5",
                          {"Forwarded":"for=8.8.8.8"})))

    def test_origin_different_from_dashboard_is_rejected(self):
        self.assertTrue(allow_private_export(req("192.168.0.15",
            {"Origin":"http://192.168.0.100:62404"})))
        self.assertFalse(allow_private_export(req("192.168.0.15",
            {"Origin":"https://evil.invalid"})))

    def test_subnets_are_configurable_but_never_entire_internet(self):
        with patch.dict(os.environ, {"PEGINELAB_EXPORT_TRUSTED_NETWORKS":
                                      "10.77.0.0/24,127.0.0.0/8"}):
            self.assertTrue(allow_private_export(req("10.77.0.12")))
            self.assertFalse(allow_private_export(req("192.168.0.15")))
        with patch.dict(os.environ, {"PEGINELAB_EXPORT_TRUSTED_NETWORKS":
                                      "0.0.0.0/0"}):
            self.assertFalse(allow_private_export(req("8.8.8.8")))
            self.assertEqual(permitted_networks(), ())
        with patch.dict(os.environ, {"PEGINELAB_EXPORT_TRUSTED_NETWORKS":
                                      "not-a-network"}):
            self.assertFalse(allow_private_export(req("192.168.0.20")))


if __name__ == "__main__":
    unittest.main()
