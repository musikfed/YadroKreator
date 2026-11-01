"""API smoke tests for VPN/LAN dashboard without web authentication."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        os.environ["PEGINELAB_HOME"] = cls.tmp.name
        app_dir = Path(__file__).resolve().parents[1]
        sys.path.insert(0, str(app_dir))
        for name in ("app", "core"):
            sys.modules.pop(name, None)
        import app
        app.app.config.update(TESTING=True)
        cls.web = app.app

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        self.client = self.web.test_client()

    def test_overview_without_login(self):
        overview = self.client.get("/api/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertIn("metrics", overview.json)
        self.assertEqual(overview.json["jobs"], [])

    def test_mutation_header_blocks_csrf(self):
        result = self.client.post("/api/jobs", json={"profile":"t23n_sd"})
        self.assertEqual(result.status_code, 403)

    def test_only_allowlisted_build_profile(self):
        result = self.client.post("/api/jobs", json={"profile":"arbitrary-shell"},
                                  headers={"X-PegineLab-Action":"1"})
        self.assertEqual(result.status_code, 400)

    def test_dashboard_no_login(self):
        result = self.client.get("/")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(b'id="password"', result.data)
        self.assertIn(b'PegineLab', result.data)

if __name__ == "__main__":
    unittest.main()
