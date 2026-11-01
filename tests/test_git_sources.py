"""Offline Git-source build tests; no GitHub credentials or network needed."""
from __future__ import annotations

import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_sources import checkout_source, validate_branch, workspace_for


class GitSourceTests(unittest.TestCase):
    def git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd, check=True,
                              capture_output=True, text=True).stdout.strip()

    def test_branch_allowlist(self):
        for good in ("mymarrchWFcam", "main"):
            self.assertEqual(validate_branch(good), good)
        for bad in ("release/0.1_test", "../etc/passwd", "main;rm -rf /", "", None):
            with self.assertRaises(ValueError):
                validate_branch(bad)
        with self.assertRaises(ValueError):
            workspace_for("../../data")

    def test_local_git_fetch_and_immutable_source_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            origin = base / "origin"
            origin.mkdir()
            self.git("init", "-b", "main", cwd=origin)
            self.git("config", "user.name", "CI", cwd=origin)
            self.git("config", "user.email", "ci@example.invalid", cwd=origin)
            (origin / "README.md").write_text("main commit\n")
            self.git("add", "README.md", cwd=origin)
            self.git("commit", "-m", "base", cwd=origin)
            self.git("switch", "-c", "mymarrchWFcam", cwd=origin)
            (origin / "README.md").write_text("branch commit\n")
            self.git("commit", "-am", "branch", cwd=origin)
            wanted = self.git("rev-parse", "HEAD", cwd=origin)

            root = base / "factory"
            project = base / "older-checkout"
            secret = project / "local" / "wifi.env"
            secret.parent.mkdir(parents=True)
            secret.write_text("TEST_DUMMY_DO_NOT_USE=1\n")

            with tempfile.TemporaryFile("w+b") as log:
                checkout, sha = checkout_source(
                    "mymarrchWFcam", "a" * 32, log, root=root,
                    project=project, repo_url=str(origin))
                self.assertEqual(sha, wanted)
                self.assertEqual((checkout / "README.md").read_text(), "branch commit\n")
                self.assertEqual((checkout / "local/wifi.env").read_text(),
                                 "TEST_DUMMY_DO_NOT_USE=1\n")
                self.assertEqual((checkout / "local/wifi.env").stat().st_mode & 0o777, 0o600)
                with self.assertRaises(RuntimeError):
                    checkout_source("mymarrchWFcam", "a" * 32, log, root=root,
                                    project=project, repo_url=str(origin))
                self.assertEqual(self.git("rev-parse", "HEAD", cwd=checkout), wanted)

            self.git("switch", "main", cwd=origin)
            (origin / "README.md").write_text("new main\n")
            self.git("commit", "-am", "new-main", cwd=origin)
            with tempfile.TemporaryFile("w+b") as log:
                other, other_sha = checkout_source(
                    "main", "b" * 32, log, root=root,
                    project=project, repo_url=str(origin))
            self.assertEqual((checkout / "README.md").read_text(), "branch commit\n")
            self.assertEqual((other / "README.md").read_text(), "new main\n")
            self.assertNotEqual(other_sha, wanted)

    def test_symlinked_wifi_credentials_are_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            repo=base/"origin"
            repo.mkdir()
            self.git("init", "-b", "main", cwd=repo)
            self.git("config", "user.name", "CI", cwd=repo)
            self.git("config", "user.email", "ci@example.invalid", cwd=repo)
            (repo/"README").write_text("ok")
            self.git("add", "README", cwd=repo)
            self.git("commit", "-m", "init", cwd=repo)
            project=base/"existing"
            (project/"local").mkdir(parents=True)
            (project/"local"/"wifi.env").symlink_to(base/"something-secret")
            with tempfile.TemporaryFile("w+b") as log:
                with self.assertRaises(RuntimeError):
                    checkout_source("main", "c"*32, log, root=base/"factory",
                                    project=project, repo_url=str(repo))


if __name__ == "__main__":
    unittest.main()
