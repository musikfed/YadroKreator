"""YadroKreator FULL lifecycle: stop only project-owned user services & labels."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProjectLifecycleTests(unittest.TestCase):
    def test_full_stop_includes_workers_timer_and_no_autostart(self):
        s = (ROOT / "scripts/project-control.sh").read_text()
        for token in (
            "peginelab-factory.service",
            "peginelab-t23n-",
            "peginelab-factory-update-",
            "peginelab-factory-update.timer",
            "disable --now",
            "stop_workers",
            "stop_containers",
            "warn_legacy_system_service",
            "start_all",
            "stop_all",
            "stop-panel",
            "EUID",
        ):
            self.assertIn(token, s)
        self.assertLess(s.index("stop_workers\n"), s.index('systemctl --user disable --now "$WEB"'))

    def test_containers_are_project_labelled_only(self):
        s = (ROOT / "scripts/project-control.sh").read_text()
        self.assertIn("com.peginelab.project=YadroKreator", s)
        self.assertIn("com.docker.compose.project=yadrokreator", s)
        self.assertIn('ps --quiet --filter "label=$label"', s)
        self.assertNotIn("docker stop $(docker ps -q)", s)
        self.assertNotIn("docker compose down", s)
        self.assertNotIn("killall", s)
        self.assertNotIn("pkill", s)
        self.assertNotIn("systemctl stop docker", s)
        self.assertNotIn("sudo systemctl stop peginelab-factory.service", s)

    def test_windows_delegates_to_ubuntu_project_control(self):
        s = (ROOT / "scripts/project-control.ps1").read_text()
        self.assertIn("ssh.exe", s)
        self.assertIn("project-control.sh", s)
        self.assertIn("192.168.0.100", s)
        self.assertNotIn("Stop-Process -Id", s)
        self.assertNotIn("taskkill /", s)
        self.assertNotRegex(s, r"(?m)^\s*sudo\b")

    def test_web_full_stop_requires_explicit_permission(self):
        app = (ROOT / "app.py").read_text()
        js = (ROOT / "static/app.js").read_text()
        self.assertIn('action not in ("restart", "stop", "stop-all")', app)
        self.assertIn('allow_private_export(request)', app)
        self.assertIn('data.get("cancel_builds") is not True', app)
        self.assertIn("project-control.sh", app)
        self.assertIn('"stop-all"', js)
        self.assertIn('cancel_builds:action==="stop-all"&&buildBusy', js)

    def test_all_platform_wrappers_present(self):
        for path in ("start.sh", "stop.sh", "start.ps1", "stop.ps1"):
            self.assertTrue((ROOT / path).is_file(), path)


if __name__ == "__main__":
    unittest.main()
