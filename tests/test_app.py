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

    def test_old_tracked_image_is_not_a_new_build_artifact(self):
        # The mymarrchWFcam Git tree already includes a previous .bin.
        # Fetching its worktree must not make it look newly compiled.
        import core
        job_id = "d" * 32
        image = (Path(self.tmp.name) / "build/jobs" / job_id /
                 "wificam_T23N/Thingino/thingino-t23-sd.bin")
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"historical-bin-in-git")
        db = core.connect()
        try:
            db.execute("INSERT INTO jobs "
                       "(id,profile,status,created_at,unit,log_path,repo_ref,source_sha) "
                       "VALUES (?,?,?,?,?,?,?,?)",
                       (job_id, "t23n_sd", "running", core.now(),
                        "unit-test", "log-test", "mymarrchWFcam", "a" * 40))
            db.commit()
        finally:
            db.close()
        try:
            for state in ("running", "failed", "stopped", "interrupted"):
                db = core.connect()
                try:
                    db.execute("UPDATE jobs SET status=? WHERE id=?", (state, job_id))
                    db.commit()
                finally:
                    db.close()
                data = self.client.get("/api/overview").json
                self.assertFalse(any(i["location"] == str(image)
                                     for i in data["images"]), state)
            db = core.connect()
            try:
                db.execute("UPDATE jobs SET status='success' WHERE id=?", (job_id,))
                db.commit()
            finally:
                db.close()
            data = self.client.get("/api/overview").json
            images = [i for i in data["images"] if i["location"] == str(image)]
            self.assertEqual(len(images), 1)
            self.assertEqual(images[0]["job_id"], job_id)
        finally:
            db = core.connect()
            try:
                db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                db.commit()
            finally:
                db.close()
            image.unlink()

    def test_private_sd_cannot_download_anonymously(self):
        # The dashboard intentionally has no login. A known job ID must NOT
        # be enough to download firmware containing personal Wi-Fi secrets.
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "b" * 32, "profile": "t23n_sd", "status": "success"}
        url = "/api/jobs/" + job["id"] + "/download"
        with patch.object(webmodule, "safe_job", return_value=job), \
             patch.object(webmodule, "saved_report", return_value={"verified": True}), \
             patch.object(webmodule, "consume_download_ticket", return_value=False):
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.post(url).status_code, 403)
            r = self.client.post(url, headers={"X-PegineLab-Action": "1"})
            self.assertEqual(r.status_code, 403)
            self.assertIn("token", r.json["error"])

    def test_download_requires_image_preflight(self):
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "c" * 32, "profile": "t23n_sd", "status": "success"}
        with patch.object(webmodule, "safe_job", return_value=job), \
             patch.object(webmodule, "saved_report", return_value=None):
            r = self.client.post("/api/jobs/" + job["id"] + "/download",
                                 headers={"X-PegineLab-Action": "1",
                                          "X-PegineLab-Download-Token": "test"})
            self.assertEqual(r.status_code, 409)

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
