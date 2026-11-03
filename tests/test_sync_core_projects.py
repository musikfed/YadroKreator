"""Offline integration: sibling Git sync and immutable protected branch contract."""
from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import sync_core_projects as sync
from scripts import prune_merged_branches as pruning


def git(*args, cwd=None):
    result = subprocess.run(["git", *map(str, args)], cwd=cwd, capture_output=True,
                            text=True, check=True, timeout=30)
    return result.stdout.strip()


class LocalGitFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "peginelab"
        (self.root / "projects").mkdir(parents=True)
        self.upstream = self.base / "upstream"
        self.upstream.mkdir()
        self.bare = self.base / "source.git"
        git("init", "--bare", "--initial-branch=main", self.bare)
        git("init", "--initial-branch=main", self.upstream)
        git("config", "user.email", "test@example.invalid", cwd=self.upstream)
        git("config", "user.name", "Test", cwd=self.upstream)
        (self.upstream / "file.txt").write_text("v1\n")
        git("add", ".", cwd=self.upstream)
        git("commit", "-m", "initial", cwd=self.upstream)
        git("remote", "add", "origin", self.bare, cwd=self.upstream)
        git("push", "-u", "origin", "main", cwd=self.upstream)

    def commit(self, filename, contents, *, message):
        (self.upstream / filename).write_text(contents)
        git("add", filename, cwd=self.upstream)
        git("commit", "-m", message, cwd=self.upstream)

    def fetch(self, name="wifcam_helper"):
        with patch.dict(sync.REPOS, {name: str(self.bare)}):
            return sync.sync_one(self.root, name, apply=True)


class CoreSyncTests(LocalGitFixture):
    def test_clone_exact_repo_and_fast_forward_without_rewriting(self):
        with patch.dict(sync.REPOS, {"wifcam_helper": str(self.bare)}):
            preview = sync.sync_one(self.root, "wifcam_helper", apply=False)
            self.assertEqual(preview["action"], "WOULD CLONE")
            cloned = sync.sync_one(self.root, "wifcam_helper", apply=True)
            self.assertEqual(cloned["action"], "CLONED")
        local = self.root / "projects/wifcam_helper"
        self.assertEqual((local / "file.txt").read_text(), "v1\n")
        self.assertEqual(git("branch", "--show-current", cwd=local), "main")
        self.commit("file.txt", "v2\n", message="update main")
        git("push", "origin", "main", cwd=self.upstream)
        updated = self.fetch()
        self.assertEqual(updated["action"], "UPDATED / NO RESET")
        self.assertEqual((local / "file.txt").read_text(), "v2\n")
        (local / "file.txt").write_text("local change\n")
        with self.assertRaisesRegex(sync.SyncError, "local modifications"):
            self.fetch()
        self.assertEqual((local / "file.txt").read_text(), "local change\n")

    def test_symlinked_directory_and_wrong_origin_are_refused(self):
        directory = self.root / "projects/wifcam_helper"
        directory.symlink_to(self.upstream, target_is_directory=True)
        with self.assertRaisesRegex(sync.SyncError, "Symlinked"):
            sync.sync_one(self.root, "wifcam_helper", apply=True)
        directory.unlink()
        git("clone", str(self.bare), directory)
        with self.assertRaisesRegex(sync.SyncError, "unexpected Git origin"):
            sync.inspect_checkout(directory, "https://github.com/musikfed/wifcam_helper.git")

    def test_never_fastforward_legacy_reference_branch(self):
        self.assertNotIn("release/0.1_test", sync.ALLOWED)
        self.assertIn("mymarrchWFcam", sync.ALLOWED)
        self.assertIn("main", sync.ALLOWED)

    def test_sqlite_active_job_refuses_sync(self):
        import sqlite3
        state = self.root / "factory-state"
        state.mkdir()
        db = sqlite3.connect(state / "factory.sqlite3")
        db.execute("CREATE TABLE jobs (id TEXT,status TEXT)")
        db.execute("INSERT INTO jobs VALUES (?,?)", ("a" * 32, "running"))
        db.commit()
        db.close()
        with self.assertRaisesRegex(sync.SyncError, "active"):
            sync.ensure_idle(self.root)


class ProtectedBranchTests(LocalGitFixture):
    def setup_branches(self):
        # A merged feature and an unmerged feature; neither should be
        # touched without explicit identity and Git SHA lease.
        git("switch", "-c", "feature/merged", cwd=self.upstream)
        self.commit("merged.txt", "done\n", message="merged feature")
        git("push", "-u", "origin", "feature/merged", cwd=self.upstream)
        git("switch", "main", cwd=self.upstream)
        git("merge", "--no-ff", "-m", "merge feature", "feature/merged", cwd=self.upstream)
        git("push", "origin", "main", cwd=self.upstream)
        git("switch", "-c", "feature/unmerged", cwd=self.upstream)
        self.commit("unmerged.txt", "unmerged\n", message="unmerged feature")
        git("push", "-u", "origin", "feature/unmerged", cwd=self.upstream)
        git("switch", "main", cwd=self.upstream)

    def test_report_merged_unmerged_protected_and_explicit_deletion(self):
        self.setup_branches()
        self.fetch()
        with patch.dict(pruning.REPOSITORIES, {"wifcam_helper": str(self.bare)}):
            rows = pruning.review(self.root, "wifcam_helper")
            statuses = {x["branch"]: x["status"] for x in rows}
            self.assertEqual(statuses["main"], "PROTECTED")
            self.assertTrue(statuses["feature/merged"].startswith("MERGED"))
            self.assertTrue(statuses["feature/unmerged"].startswith("UNMERGED"))
            with self.assertRaises(pruning.BranchError):
                pruning.delete_named(self.root, "wifcam_helper", ["main"], apply=True,
                                     confirm=pruning.CONFIRM)
            with self.assertRaises(pruning.BranchError):
                pruning.delete_named(self.root, "wifcam_helper", ["feature/unmerged"], apply=True,
                                     confirm=pruning.CONFIRM)
            preview = pruning.delete_named(self.root, "wifcam_helper", ["feature/merged"],
                                           apply=False)
            self.assertEqual(preview[0]["branch"], "feature/merged")
            self.assertTrue(git("ls-remote", "--heads", str(self.bare), "feature/merged"))
            with self.assertRaisesRegex(pruning.BranchError, "confirm"):
                pruning.delete_named(self.root, "wifcam_helper", ["feature/merged"],
                                     apply=True)
            pruning.delete_named(self.root, "wifcam_helper", ["feature/merged"],
                                 apply=True, confirm=pruning.CONFIRM)
            self.assertFalse(git("ls-remote", "--heads", str(self.bare), "feature/merged"))
            self.assertTrue(git("ls-remote", "--heads", str(self.bare), "feature/unmerged"))

    def test_wificam_hardware_branches_always_protected(self):
        self.fetch("wificam_T23N")
        for name in ("main", "mymarrchWFcam", "release/0.1_test"):
            self.assertIn(name, pruning.PROTECTED["wificam_T23N"])
        self.assertTrue(pruning.PROTECTED["YadroKreator"] == frozenset(("main",)))


if __name__ == "__main__":
    unittest.main()
