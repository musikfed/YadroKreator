"""No network or real server access: deletion is exercised only in temp dirs."""
from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.cleanup_legacy_builds import run, plan, CleanupError


class LegacyCleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.data = self.root / "factory-state"
        self.data.mkdir()
        self.dbpath = self.data / "factory.sqlite3"
        db = sqlite3.connect(self.dbpath)
        db.execute("CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT, log_path TEXT)")
        db.commit()
        db.close()

    def job(self, id: str, status="success", legacy=True):
        path = (self.data / "logs" / (id + ".log")) if legacy else (
            self.data / "projects" / "wificam_T23N" / "logs" / (id + ".log"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("test job log")
        db = sqlite3.connect(self.dbpath)
        db.execute("INSERT INTO jobs VALUES(?,?,?)", (id, status, str(path)))
        db.commit()
        db.close()
        return path

    def test_dry_run_and_exact_explicit_deletion(self):
        old = "a" * 32
        new = "b" * 32
        old_log = self.job(old)
        new_log = self.job(new, legacy=False)
        old_out = self.root / "build/jobs" / old / "wificam_T23N/out/private-sd"
        old_out.mkdir(parents=True)
        (old_out / "thingino-t23-sd.bin").write_bytes(b"old dummy image")
        new_out = self.root / "build/projects/wificam_T23N/jobs" / new
        new_out.mkdir(parents=True)
        (new_out / "new.img").write_bytes(b"new dummy image")
        baseline = self.root / "projects/wificam_T23N/Thingino/thingino-t23-sd.bin"
        baseline.parent.mkdir(parents=True)
        baseline.write_bytes(b"do not destroy")
        thingino = self.root / "build/thingino-firmware/build/config"
        thingino.parent.mkdir(parents=True)
        thingino.write_text("pinned sources")
        preview = run(self.root)
        self.assertEqual(preview["finished_legacy_job_ids"], [old])
        self.assertTrue(old_log.exists())
        with self.assertRaisesRegex(CleanupError, "confirm"):
            run(self.root, apply=True)
        self.assertTrue(old_log.exists())
        deleted = run(self.root, apply=True, confirm="DELETE-LEGACY-JOBS")
        self.assertTrue(deleted["applied"])
        self.assertFalse(old_log.exists())
        self.assertFalse(old_out.exists())
        self.assertTrue(new_log.exists())
        self.assertTrue((new_out / "new.img").exists())
        self.assertEqual(baseline.read_bytes(), b"do not destroy")
        self.assertEqual(thingino.read_text(), "pinned sources")
        db = sqlite3.connect(self.dbpath)
        rows = db.execute("SELECT id FROM jobs").fetchall()
        db.close()
        self.assertEqual(rows, [(new,)])

    def test_refuse_cleanup_if_active_old_or_new_job(self):
        self.job("c" * 32, status="running")
        self.job("d" * 32, status="queued", legacy=False)
        with self.assertRaisesRegex(CleanupError, "active"):
            run(self.root)
        with self.assertRaises(CleanupError):
            run(self.root, apply=True, confirm="DELETE-LEGACY-JOBS")

    def test_refuse_symlinked_old_artifact(self):
        jid = "e" * 32
        self.job(jid)
        foreign = self.root / "projects/wificam_T23N"
        foreign.mkdir(parents=True)
        legacy = self.root / "build/jobs" / jid
        legacy.parent.mkdir(parents=True)
        legacy.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(CleanupError, "symlink"):
            plan(self.root)
        self.assertTrue(foreign.exists())

    def test_refuse_symlinked_old_build_root(self):
        jid = "f" * 32
        self.job(jid)
        foreign = self.root / "foreign"
        foreign.mkdir()
        old_build = self.root / "build"
        old_build.symlink_to(foreign, target_is_directory=True)
        with self.assertRaisesRegex(CleanupError, "symlinked cleanup anchor"):
            run(self.root, apply=True, confirm="DELETE-LEGACY-JOBS")
        self.assertTrue(foreign.exists())

    def test_old_git_cache_requires_separate_flag(self):
        old_cache = self.root / "build/git-cache/wificam_T23N.git"
        old_cache.mkdir(parents=True)
        (old_cache / "HEAD").write_text("ref")
        self.assertNotIn(str(old_cache), plan(self.root)["delete_paths"])
        self.assertIn(str(old_cache), plan(self.root, caches=True)["delete_paths"])
        run(self.root, apply=True, confirm="DELETE-LEGACY-JOBS")
        self.assertTrue(old_cache.is_dir())
        run(self.root, apply=True, confirm="DELETE-LEGACY-JOBS", caches=True)
        self.assertFalse(old_cache.exists())


if __name__ == "__main__":
    unittest.main()
