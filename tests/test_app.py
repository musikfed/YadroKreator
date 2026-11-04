"""API smoke tests for VPN/LAN dashboard without web authentication."""
import os
from pathlib import Path
from unittest.mock import patch
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

    def test_register_wificam_branch_and_independent_project(self):
        from unittest.mock import patch
        from project_registry import add_branch, add_project
        import app as dashboard
        with tempfile.TemporaryDirectory() as temp:
            data=Path(temp)
            with patch.object(dashboard,"DATA",data), \
                 patch.object(dashboard,"register_branch",
                     side_effect=lambda branch,data: add_branch(branch,data=data,verify=lambda *_:True)), \
                 patch.object(dashboard,"register_project",
                     side_effect=lambda slug,title,repository,branch,data:
                         add_project(slug,title,repository,branch,data=data,verify=lambda *_:True)):
                route="/api/projects/register"
                self.assertEqual(self.client.post(route,json={"kind":"branch",
                    "branch":"feature/new", "confirm":"REGISTER-BRANCH"}).status_code,403)
                self.assertEqual(self.client.post(route,
                    headers={"X-PegineLab-Action":"1"},
                    json={"kind":"branch","branch":"feature/new",
                          "confirm":"WRONG"}).status_code,400)
                with patch.object(dashboard,"update_view",return_value={"phase":"success"}):
                    first=self.client.post(route,
                        headers={"X-PegineLab-Action":"1"},
                        json={"kind":"branch","branch":"feature/new",
                              "confirm":"REGISTER-BRANCH"})
                    self.assertEqual(first.status_code,200)
                    self.assertIn("feature/new",first.json["registry"]["branches"])
                    another=self.client.post(route,
                        headers={"X-PegineLab-Action":"1"},
                        json={"kind":"project","slug":"new-linux","title":"Linux ядро",
                              "repository":"musikfed/linux_kernel","branch":"main",
                              "confirm":"REGISTER-PROJECT"})
                    self.assertEqual(another.status_code,200)
                view=self.client.get("/api/overview")
                self.assertIn("feature/new",view.json["allowed_branches"])
                self.assertEqual(view.json["registered_projects"][0]["build_mode"],
                                 "pending_adapter")
                denied=self.client.post("/api/jobs",json={"profile":"new-linux"},
                                        headers={"X-PegineLab-Action":"1"})
                self.assertEqual(denied.status_code,400)
                with patch.object(dashboard,"git_ref_sha",return_value="e"*40) as sha:
                    result=self.client.get("/api/projects/new-linux/git-ref")
                    self.assertEqual(result.status_code,200)
                    self.assertEqual(result.json["sha"],"e"*40)
                    sha.assert_called_once_with("linux_kernel","main")

    def test_dynamic_registry_rejects_external_github_and_does_not_run_code(self):
        import app as dashboard
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(dashboard,"DATA",Path(temp)), \
                 patch.object(dashboard,"update_view",return_value={"phase":"success"}):
                for repo in ("evil/repo","https://evil.example/kernel","musikfed/../oops"):
                    with self.subTest(repo=repo):
                        denied=self.client.post("/api/projects/register",
                            headers={"X-PegineLab-Action":"1"},
                            json={"kind":"project","slug":"new-linux","title":"Linux",
                                  "repository":repo,"branch":"main",
                                  "confirm":"REGISTER-PROJECT"})
                        self.assertEqual(denied.status_code,422)
                self.assertFalse((Path(temp)/"registered-projects.json").exists())

    def test_helper_status_is_read_only_and_lifecycle_requires_confirmation(self):
        from unittest.mock import patch
        import app as dashboard
        fake={
            "source_present":True,"service_installed":True,
            "service_state":"active","service_unit":"peginelab-wifcam-helper.service",
            "report_count":3,"independent_from_firmware":True
        }
        with patch.object(dashboard,"helper_status",return_value=fake):
            data=self.client.get("/api/helper/status")
            self.assertEqual(data.status_code,200)
            self.assertEqual(data.json["report_count"],3)
            post="/api/helper/service/stop"
            self.assertEqual(self.client.post(post).status_code,403)
            self.assertEqual(self.client.post(post,headers={"X-PegineLab-Action":"1"},
                              json={"confirm":"FACTORY-STOP"}).status_code,400)
            with patch.object(dashboard,"helper_lifecycle",return_value=True) as life, \
                 patch.object(dashboard,"update_view",return_value={"phase":"success"}):
                result=self.client.post(post,headers={"X-PegineLab-Action":"1"},
                                        json={"confirm":"HELPER-STOP"})
                self.assertEqual(result.status_code,200)
                life.assert_called_once_with("stop")
        self.assertEqual(self.client.post("/api/helper/service/prune",
                         headers={"X-PegineLab-Action":"1"}).status_code,404)

    def test_overview_without_login(self):
        overview = self.client.get("/api/overview")
        self.assertEqual(overview.status_code, 200)
        self.assertIn("metrics", overview.json)
        self.assertEqual(overview.json["jobs"], [])

    def test_home_is_project_neutral_and_shows_live_job_without_sqlite_reset(self):
        import core
        from unittest.mock import patch
        import app as webmodule
        html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="activeJobName"', html)
        self.assertIn('id="activeJobOpen"', html)
        self.assertIn('href="#builds"', html)
        self.assertIn('href="#irila"', html)
        self.assertIn('href="#helper"', html)
        self.assertNotIn("Новая сборка T23N", html)
        self.assertNotIn('id="heroBuild"', html)
        self.assertNotIn('id="profileBuild"', html)
        self.assertIn("Сейчас выполняется", html)

        jid = "6" * 32
        db = core.connect()
        try:
            db.execute(
                "INSERT INTO jobs (id,profile,status,created_at,started_at,unit,log_path,repo_ref) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (jid, "irila_preflight", "running", core.now(), core.now(),
                 "peginelab-irila-" + jid, "/tmp/no-real-log", "main"),
            )
            db.commit()
            with patch.object(webmodule, "unit_active", return_value=True):
                data = self.client.get("/api/overview").json
            self.assertEqual(data["active_job"]["id"], jid)
            self.assertEqual(data["active_job"]["profile"], "irila_preflight")
            self.assertEqual(data["active_job"]["repo_ref"], "main")
            self.assertEqual(data["concurrency"]["active_profile"], "irila_preflight")
            self.assertNotIn("log_path", data["active_job"])
        finally:
            db.execute("DELETE FROM jobs WHERE id=?", (jid,))
            db.commit()
            db.close()

    def test_active_old_task_is_visible_even_after_forty_recent_finished_jobs(self):
        import core
        from unittest.mock import patch
        import app as webmodule
        active_id = "7" * 32
        ids = [f"{i:032x}" for i in range(200, 240)]
        db = core.connect()
        try:
            db.execute(
                "INSERT INTO jobs (id,profile,status,created_at,started_at,unit,log_path,repo_ref) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (active_id, "t23n_sd", "running", "2025-01-01T00:00:00+00:00",
                 core.now(), "peginelab-t23n-" + active_id, "/tmp/none", "mymarrchWFcam"),
            )
            for i, jid in enumerate(ids):
                db.execute(
                    "INSERT INTO jobs (id,profile,status,created_at,unit,log_path,repo_ref) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (jid, "irila_preflight", "success", f"2026-01-01T00:{i:02d}:00+00:00",
                     "peginelab-irila-" + jid, "/tmp/none", "main"),
                )
            db.commit()
            with patch.object(webmodule, "unit_active", return_value=True):
                response = self.client.get("/api/overview")
            self.assertEqual(response.status_code, 200)
            data = response.json
            self.assertEqual(data["active_job"]["id"], active_id)
            self.assertIn(active_id, [j["id"] for j in data["jobs"]])
            self.assertEqual(data["concurrency"]["max_builds"], 1)
        finally:
            db.execute("DELETE FROM jobs WHERE id=? OR id IN (" +
                       ",".join("?" for _ in ids) + ")", (active_id, *ids))
            db.commit()
            db.close()

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
        image = (Path(self.tmp.name) / "build/projects/wificam_T23N/jobs" / job_id /
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
            self.assertEqual(images, [], "tracked baseline is not a new build even on success")
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
            path = Path(self.tmp.name) / "build/projects/wificam_T23N/jobs" / job_id / \
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
        path = Path(self.tmp.name) / "factory-state/projects/wificam_T23N/logs" / (job_id + ".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"OLD_HEADER\\n" + b"x" * 80000 + b"\\nFINISHED_SUCCESS\\n")
        job = {"id": job_id, "status": "success", "profile": "t23n_sd"}
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
        path = Path(self.tmp.name) / "factory-state/projects/wificam_T23N/logs" / (job_id + ".log")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("line before browser refresh\\n")
        with patch.object(webmodule, "safe_job", return_value={"id": job_id, "status": "running", "profile": "t23n_sd"}):
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

    def test_irila_and_wificam_share_one_atomic_build_queue(self):
        import sys
        from unittest.mock import patch
        import core
        webmodule = sys.modules["app"]
        jid = "9" * 32
        db = core.connect()
        try:
            db.execute("INSERT INTO jobs (id,profile,status,created_at,unit,log_path,repo_ref) "
                       "VALUES (?,?,?,?,?,?,?)",
                       (jid, "t23n_sd", "running", core.now(),
                        "peginelab-t23n-" + jid, "test.log", "mymarrchWFcam"))
            db.commit()
            with patch.object(webmodule, "reconcile"), \
                 patch.object(webmodule, "update_view", return_value={}), \
                 patch.object(webmodule.subprocess, "run",
                              return_value=__import__("subprocess").CompletedProcess([], 1)):
                reply = self.client.post("/api/jobs",
                    json={"profile": "irila_preflight", "branch": "main"},
                    headers={"X-PegineLab-Action": "1"})
            self.assertEqual(reply.status_code, 409)
            self.assertEqual(reply.json["job_id"], jid)
        finally:
            db.execute("DELETE FROM jobs WHERE id=?", (jid,))
            db.commit()
            db.close()

    def test_irila_source_audit_cannot_be_used_as_sd_firmware(self):
        from unittest.mock import patch
        import sys
        webmodule = sys.modules["app"]
        jid = "8" * 32
        job = {"id": jid, "profile": "irila_preflight",
               "status": "success", "source_sha": "a" * 40}
        with patch.object(webmodule, "safe_job", return_value=job):
            self.assertEqual(self.client.post("/api/jobs/" + jid + "/download",
                             headers={"X-PegineLab-Action": "1"}).status_code, 404)
            self.assertEqual(self.client.post("/api/jobs/" + jid + "/validate",
                             headers={"X-PegineLab-Action": "1"}).status_code, 422)
            self.assertEqual(self.client.get("/api/jobs/" + jid + "/layout.svg").status_code, 409)
        blocked = self.client.post("/api/jobs",
                                  json={"profile": "irila_preflight", "branch": "main",
                                        "helper_preset": True},
                                  headers={"X-PegineLab-Action": "1"})
        self.assertEqual(blocked.status_code, 400)

    def test_dashboard_no_login(self):
        result = self.client.get("/")
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(b'id="password"', result.data)
        self.assertIn(b'PegineLab', result.data)

if __name__ == "__main__":
    unittest.main()
