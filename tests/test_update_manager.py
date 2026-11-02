"""Offline test of Git update detection, one-level rollback and safety gates."""
from __future__ import annotations

import importlib
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class UpdaterTests(unittest.TestCase):
    def git(self, path, *args):
        return subprocess.run(["git", "-C", str(path), *args], check=True,
                              capture_output=True, text=True).stdout.strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.origin = self.base / "origin"
        self.origin.mkdir()
        self.git(self.origin, "init", "-b", "main")
        self.git(self.origin, "config", "user.name", "CI")
        self.git(self.origin, "config", "user.email", "ci@example.invalid")
        (self.origin / "app.py").write_text("v1\n")
        self.git(self.origin, "add", ".")
        self.git(self.origin, "commit", "-m", "first")
        self.first = self.git(self.origin, "rev-parse", "HEAD")
        self.app = self.base / "factory" / "projects" / "YadroKreator"
        self.app.parent.mkdir(parents=True)
        subprocess.run(["git", "clone", str(self.origin), str(self.app)],
                       check=True, capture_output=True)
        self.git(self.app, "config", "user.name", "CI")
        self.git(self.app, "config", "user.email", "ci@example.invalid")
        import update_manager
        self.updater = update_manager
        self.patches = {
            "ROOT": self.base / "factory",
            "APP": self.app,
            "VENV": self.base / "venv",
            "DATA": self.base / "factory-state",
            "STATE_FILE": self.base / "factory-state" / "updates.json",
            "LOCK_FILE": self.base / "factory-state" / "updates.lock",
            "DB": self.base / "factory-state" / "factory.sqlite3",
            "ORIGIN": str(self.origin),
        }
        self.old = {key: getattr(update_manager, key) for key in self.patches}
        for key, value in self.patches.items():
            setattr(update_manager, key, value)
        (self.base / "venv/bin").mkdir(parents=True)
        (self.base / "venv/bin/python").write_text("dummy python")
        self.restart_patch = patch.object(update_manager, "verify_and_restart")
        self.restart = self.restart_patch.start()

    def tearDown(self):
        self.restart_patch.stop()
        for key, value in self.old.items():
            setattr(self.updater, key, value)
        self.temp.cleanup()

    def op(self, name, expected=""):
        operation = self.updater.start(name, expected)["operation"]
        self.updater.perform(operation)
        return self.updater.view()

    def second_commit(self):
        (self.origin / "app.py").write_text("v2\n")
        self.git(self.origin, "commit", "-am", "second")
        return self.git(self.origin, "rev-parse", "HEAD")

    def test_notification_update_and_previous_version_rollback(self):
        state = self.op("check")
        self.assertFalse(state["update_available"])
        target = self.second_commit()
        state = self.op("check")
        self.assertTrue(state["update_available"])
        self.assertEqual(state["remote_sha"], target)
        self.assertEqual(state["installed_sha"], self.first)
        state = self.op("apply", target)
        self.assertEqual(state["phase"], "success")
        self.assertEqual(state["installed_sha"], target)
        self.assertEqual(state["rollback_sha"], self.first)
        self.assertTrue(state["rollback_available"])
        state = self.op("rollback")
        self.assertEqual(state["phase"], "success")
        self.assertEqual(state["installed_sha"], self.first)
        self.assertFalse(state["rollback_available"])
        self.assertEqual((self.app / "app.py").read_text(), "v1\n")
        self.assertEqual(self.restart.call_count, 2)

    def test_changed_head_or_dirty_files_refused(self):
        target = self.second_commit()
        self.op("check")
        with self.assertRaises(RuntimeError):
            self.updater.start("apply", "a" * 40)
        (self.app / "app.py").write_text("custom modification\n")
        state = self.op("apply", target)
        self.assertEqual(state["phase"], "failed")
        self.assertEqual((self.app / "app.py").read_text(), "custom modification\n")

    def test_active_build_blocks_apply_and_rollback(self):
        target = self.second_commit()
        self.op("check")
        db = sqlite3.connect(self.updater.DB)
        db.execute("CREATE TABLE jobs (id TEXT, status TEXT)")
        db.execute("INSERT INTO jobs VALUES (?, ?)", ("a" * 32, "running"))
        db.commit()
        db.close()
        with self.assertRaises(RuntimeError):
            self.updater.start("apply", target)

    def test_update_steps_are_persistent(self):
        operation = self.updater.start("check")["operation"]
        self.updater.mark_step(operation, "fetch", "GitHub fetch")
        v = self.updater.view()
        self.assertEqual(v["step"], "fetch")
        self.assertEqual(v["step_index"], 1)
        self.assertEqual(v["phase"], "queued")
        self.updater.finish(operation, "failed", "network unavailable")
        v = self.updater.view()
        self.assertEqual(v["step"], "failed")
        self.assertEqual(v["message"], "network unavailable")

    def test_finished_apply_reports_complete_step(self):
        target = self.second_commit()
        self.op("check")
        state = self.op("apply", target)
        self.assertEqual(state["phase"], "success")
        self.assertEqual(state["step"], "done")
        self.assertEqual(state["step_index"], state["step_total"])
        self.assertTrue(state["rollback_available"])

    def test_concurrent_update_is_rejected(self):
        s = self.updater.start("check")
        with self.assertRaises(RuntimeError):
            self.updater.start("check")
        self.updater.perform(s["operation"])
        self.assertEqual(self.updater.view()["phase"], "success")


if __name__ == "__main__":
    unittest.main()
