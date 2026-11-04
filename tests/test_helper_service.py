"""Dedicated WifCam Helper control does not become a third firmware profile."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

import helper_service


class HelperIsolationTests(unittest.TestCase):
    def test_read_only_status_and_separate_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/"projects/wifcam_helper/wifcam_helper").mkdir(parents=True)
            (root/"projects/wifcam_helper/wifcam_helper/web.py").write_text("# standalone")
            state=root/"helperstate"
            state.mkdir()
            with sqlite3.connect(state/"history.sqlite3") as con:
                con.execute("CREATE TABLE reports(id TEXT, created_utc TEXT, test_name TEXT, payload TEXT)")
                con.execute("INSERT INTO reports VALUES(?,?,?,?)",("one","test","probe","{}"))
            with patch.object(helper_service, "_cmd", side_effect=[(0,""),(0,str(root/"projects/wifcam_helper")),(0,"/usr/bin/python3 -m wifcam_helper web"),(0,"active")]):
                info=helper_service.status(root,state=state)
            self.assertEqual(info["report_count"],1)
            self.assertEqual(info["service_state"],"active")
            self.assertTrue(info["independent_from_firmware"])
            self.assertNotEqual(info["report_database"],info["factory_database"])
            self.assertEqual(info["bind"],"127.0.0.1:8765")

    def test_lifecycle_uses_exact_user_unit(self):
        with patch.object(helper_service, "_cmd", return_value=(0,"")) as run:
            self.assertTrue(helper_service.lifecycle("restart"))
            run.assert_called_once_with("systemctl","--user","restart",
                                        "peginelab-wifcam-helper.service")
        with self.assertRaises(ValueError):
            helper_service.lifecycle("docker-prune")

    def test_uninstalled_helper_does_not_claim_success(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(helper_service, "_cmd", return_value=(1,"")):
                info=helper_service.status(Path(temp),state=Path(temp)/"none")
            self.assertEqual(info["service_state"],"not-installed")
            self.assertIsNone(info["report_count"])

    def test_dashboard_html_is_not_redirect_to_firmware_builder(self):
        html=(Path(__file__).resolve().parents[1]/"templates/index.html").read_text()
        section=html.split('data-panel="helper"')[1].split('data-panel="artifacts"')[0]
        self.assertIn('id="helperReportCount"',section)
        self.assertIn('id="helperStop"',section)
        self.assertNotIn('href="#builds"',section)

    def test_factory_rebuild_is_explicit_scoped_and_ssh_first(self):
        script=(Path(__file__).resolve().parents[1]/"scripts/rebuild-from-git.sh").read_text()
        self.assertIn("bash deploy.sh --apply",script)
        self.assertIn("src.backup(dst)",script)
        self.assertIn("git status --porcelain",script)
        self.assertIn("--clean-cache",script)
        self.assertIn("factory-venv",script)
        self.assertNotIn("docker system prune",script)
        self.assertNotIn("docker compose down",script)


if __name__=="__main__":
    unittest.main()
