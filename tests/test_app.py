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

    def test_candidate_image_appears_separately_from_baseline(self):
        image = Path(self.tmp.name) / "projects/wificam_T23N/out/candidate-sd/thingino-t23-sd.bin"
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"candidate-test")
        try:
            response = self.client.get("/api/overview")
            self.assertEqual(response.status_code, 200)
            matches = [item for item in response.json["images"]
                       if item["location"] == str(image)]
            self.assertEqual(len(matches), 1)
            self.assertIn("кандидат", matches[0]["label"].lower())
            self.assertEqual(matches[0]["bytes"], len(b"candidate-test"))
        finally:
            image.unlink()

    def test_mutation_header_blocks_csrf(self):
        result = self.client.post("/api/jobs", json={"profile":"t23n_sd"})
        self.assertEqual(result.status_code, 403)

    def test_only_allowlisted_build_profile(self):
        result = self.client.post("/api/jobs", json={"profile":"arbitrary-shell"},
                                  headers={"X-PegineLab-Action":"1"})
        self.assertEqual(result.status_code, 400)

    def test_branch_allowlist_and_default_source(self):
        result = self.client.post("/api/jobs",
                                  json={"profile": "t23n_sd", "branch": "../outside"},
                                  headers={"X-PegineLab-Action": "1"})
        self.assertEqual(result.status_code, 400)
        overview = self.client.get("/api/overview")
        self.assertEqual(overview.json["allowed_branches"],
                         ["mymarrchWFcam", "main"])

    def test_dashboard_no_login(self):
        result = self.client.get("/")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(b'id="password"', result.data)
        self.assertIn(b'PegineLab', result.data)

if __name__ == "__main__":
    unittest.main()
