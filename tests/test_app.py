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

    def test_panel_service_status_reads_only_dashboard_unit(self):
        from unittest.mock import patch
        import app as webmodule
        with patch.object(webmodule, "panel_service_status",
                          return_value={"state": "active", "message": "systemd --user"}):
            result = self.client.get("/api/panel/service")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["state"], "active")

    def test_panel_service_requires_trusted_lan_header_and_confirmation(self):
        from unittest.mock import patch
        import app as webmodule
        url = "/api/panel/service/stop"
        self.assertEqual(self.client.post(url).status_code, 403)
        with patch.object(webmodule, "panel_service_status",
                          return_value={"state": "active"}), \
             patch.object(webmodule, "update_view", return_value={"phase": "success"}):
            self.assertEqual(self.client.post(url, headers={"X-PegineLab-Action":"1"},
                environ_overrides={"REMOTE_ADDR":"8.8.8.8"},
                json={"confirm":"STOP"}).status_code, 403)
            self.assertEqual(self.client.post(url, headers={
                "X-PegineLab-Action":"1", "Origin":"https://evil.invalid"},
                json={"confirm":"STOP"}).status_code, 403)
            self.assertEqual(self.client.post(url, headers={"X-PegineLab-Action":"1"},
                json={"confirm":"nonsense"}).status_code, 400)
        self.assertEqual(self.client.post("/api/panel/service/exec",
            headers={"X-PegineLab-Action":"1"}).status_code, 404)

    def test_restart_panel_in_independent_unit_and_no_machine_shutdown(self):
        from unittest.mock import patch
        from subprocess import CompletedProcess
        import app as webmodule
        with patch.object(webmodule, "panel_service_status", return_value={"state":"active"}), \
             patch.object(webmodule, "update_view", return_value={"phase":"success"}), \
             patch.object(webmodule.subprocess, "run",
                          return_value=CompletedProcess([],0,"","")) as run:
            r = self.client.post("/api/panel/service/restart",
                headers={"X-PegineLab-Action":"1"}, json={"confirm":"RESTART"})
        self.assertEqual(r.status_code, 202)
        argv=run.call_args.args[0]
        self.assertEqual(argv[0], "systemd-run")
        self.assertIn("--user", argv)
        self.assertIn("peginelab-factory.service", argv[-1])
        self.assertNotIn("reboot", argv[-1])
        self.assertNotIn("docker", argv[-1])
        self.assertNotIn("peginelab-t23n", argv[-1])

    def test_panel_stop_rejected_during_update(self):
        from unittest.mock import patch
        import app as webmodule
        with patch.object(webmodule, "panel_service_status", return_value={"state":"active"}), \
             patch.object(webmodule, "update_view", return_value={"phase":"running"}):
            r=self.client.post("/api/panel/service/stop",
                headers={"X-PegineLab-Action":"1"}, json={"confirm":"STOP"})
        self.assertEqual(r.status_code, 409)

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

    def test_private_image_download_requires_trusted_lan_and_action_header(self):
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "b" * 32, "profile": "t23n_sd", "status": "success"}
        url = "/api/jobs/" + job["id"] + "/download"
        with patch.object(webmodule, "safe_job", return_value=job):
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.post(url).status_code, 403)
            # Real network policy, no token and no arbitrary URL/download.
            blocked = self.client.post(url,
                headers={"X-PegineLab-Action": "1"},
                environ_overrides={"REMOTE_ADDR":"8.8.8.8"})
            self.assertEqual(blocked.status_code, 403)
            self.assertIn("trusted LAN", blocked.json["error"])
            spoofed = self.client.post(url,
                headers={"X-PegineLab-Action":"1",
                         "X-Forwarded-For":"192.168.0.44"},
                environ_overrides={"REMOTE_ADDR":"8.8.8.8"})
            self.assertEqual(spoofed.status_code, 403)
            cross_site = self.client.post(url,
                headers={"X-PegineLab-Action":"1",
                         "Origin":"https://attacker.invalid"})
            self.assertEqual(cross_site.status_code, 403)

    def test_lan_one_click_streams_verified_image_without_ticket(self):
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "e" * 32, "profile": "t23n_sd", "status": "success"}
        file = Path(self.tmp.name) / "checked.img"
        file.write_bytes(b"preflight-passed-firmware-fixture")
        with patch.object(webmodule, "safe_job", return_value=job), \
             patch.object(webmodule, "saved_report", return_value={
                 "verified": True, "sha256": "f" * 64}), \
             patch.object(webmodule, "artifact_path", return_value=file), \
             patch.object(webmodule, "validate_t23n", return_value={
                 "sha256": "f" * 64, "verified": True}), \
             patch.object(webmodule, "save_report"):
            r = self.client.post("/api/jobs/" + job["id"] + "/download",
                headers={"X-PegineLab-Action":"1",
                         "Origin":"http://localhost"},
                environ_overrides={"REMOTE_ADDR":"192.168.0.77"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data, b"preflight-passed-firmware-fixture")
            self.assertIn(".img", r.headers["Content-Disposition"])
            self.assertIn("no-store", r.headers["Cache-Control"])
        file.unlink()

    def test_download_auto_validates_old_image_without_rebuild(self):
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "c" * 32, "profile": "t23n_sd", "status": "success"}
        image = Path(self.tmp.name) / "existing-image.bin"
        image.write_bytes(b"already-compiled-image")
        with patch.object(webmodule, "safe_job", return_value=job), \
             patch.object(webmodule, "saved_report", return_value=None), \
             patch.object(webmodule, "artifact_path", return_value=image), \
             patch.object(webmodule, "validate_t23n", return_value={
                 "sha256": "a" * 64, "verified": True}), \
             patch.object(webmodule, "save_report") as stored:
            r = self.client.post("/api/jobs/" + job["id"] + "/download",
                headers={"X-PegineLab-Action":"1"})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.data, b"already-compiled-image")
            self.assertEqual(r.headers["X-PegineLab-Preflight"], "passed")
            stored.assert_called_once()
        image.unlink()

    def test_corrupt_image_is_rejected_even_on_trusted_lan(self):
        from unittest.mock import patch
        import app as webmodule
        job = {"id": "c" * 32, "profile": "t23n_sd", "status": "success"}
        with patch.object(webmodule, "safe_job", return_value=job), \
             patch.object(webmodule, "artifact_path", return_value=Path("bad.bin")), \
             patch.object(webmodule, "validate_t23n",
                          side_effect=ValueError("bad MSPL at LBA34")):
            r = self.client.post("/api/jobs/" + job["id"] + "/download",
                headers={"X-PegineLab-Action":"1"})
            self.assertEqual(r.status_code, 422)
            self.assertIn("MSPL", r.json["error"])

    def test_overview_artifact_validation_belongs_to_correct_job(self):
        # Regression: old loop used validation=j["validation"] (last job),
        # so a verified job showed "not checked" in the Artifacts tab.
        import core
        import app as webmodule
        from unittest.mock import patch
        success_ids = ["7" * 32, "8" * 32]
        db = core.connect()
        try:
            for idx, job_id in enumerate(success_ids):
                db.execute(
                    "INSERT INTO jobs "
                    "(id,profile,status,created_at,unit,log_path,repo_ref,source_sha) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (job_id, "t23n_sd", "success", core.now(),
                     "unit-test", "log-test", "mymarrchWFcam", str(idx + 1) * 40))
            db.commit()
        finally:
            db.close()
        images = []
        for job_id in success_ids:
            path = Path(self.tmp.name) / "build/jobs" / job_id / \
                "wificam_T23N/out/private-sd/thingino-t23-sd.bin"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"artifact-" + job_id.encode())
            images.append(path)
        try:
            def report(job, *unused):
                return {"verified": job["id"] == success_ids[0],
                        "sha256": job["id"]}
            with patch.object(webmodule, "saved_report", side_effect=report):
                r = self.client.get("/api/overview")
            self.assertEqual(r.status_code, 200)
            found = {item["job_id"]: item for item in r.json["images"]
                     if item.get("job_id") in success_ids}
            self.assertEqual(set(found), set(success_ids))
            self.assertTrue(found[success_ids[0]]["validation"]["verified"])
            self.assertFalse(found[success_ids[1]]["validation"]["verified"])
        finally:
            db = core.connect()
            try:
                for job_id in success_ids:
                    db.execute("DELETE FROM jobs WHERE id=?", (job_id,))
                db.commit()
            finally:
                db.close()
            for image in images:
                image.unlink()


    def test_finished_job_refresh_reads_tail_not_full_history(self):
        import core
        from unittest.mock import patch
        import app as webmodule
        job_id = "f" * 32
        path = Path(self.tmp.name) / "factory-state/logs" / (job_id + ".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"OLD_HEADER\\n" + b"x" * 80000 + b"\\nFINISHED_SUCCESS\\n")
        job = {"id": job_id, "status": "success"}
        with patch.object(webmodule, "safe_job", return_value=job):
            tail = self.client.get("/api/jobs/" + job_id + "/log?tail=1")
            self.assertEqual(tail.status_code, 200)
            self.assertIn("FINISHED_SUCCESS", tail.json["text"])
            self.assertNotIn("OLD_HEADER", tail.json["text"])
            self.assertFalse(tail.json["more"])
            self.assertTrue(tail.json["archive"])
            self.assertTrue(tail.json["truncated"])
            self.assertEqual(tail.json["offset"], path.stat().st_size)
            # A user can still explicitly request the full historical log.
            full = self.client.get("/api/jobs/" + job_id + "/log?offset=0")
            self.assertIn("OLD_HEADER", full.json["text"])
            self.assertTrue(full.json["more"])
        path.unlink()

    def test_running_log_tail_can_follow_new_output(self):
        from unittest.mock import patch
        import app as webmodule
        job_id = "e" * 32
        path = Path(self.tmp.name) / "factory-state/logs" / (job_id + ".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("line before browser refresh\\n")
        with patch.object(webmodule, "safe_job", return_value={"id": job_id, "status": "running"}):
            first = self.client.get("/api/jobs/" + job_id + "/log?tail=1")
            self.assertFalse(first.json["archive"])
            with path.open("a") as out:
                out.write("only new output\\n")
            next_result = self.client.get(
                "/api/jobs/" + job_id + "/log?offset=" + str(first.json["offset"]))
            self.assertEqual(next_result.json["text"], "only new output\\n")
        path.unlink()

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
