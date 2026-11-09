"""Offline regression tests for manual camera firmware Git refresh.

Git is local to each temporary test fixture; no network or SD build is used.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import firmware_sources


def git(*args):
    return subprocess.run(["git", *map(str, args)], check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True).stdout.strip()


def repository(folder: Path, *, branch: str):
    folder.mkdir(parents=True)
    git("init", str(folder))
    git("-C", folder, "config", "user.name", "Firmware test")
    git("-C", folder, "config", "user.email", "test@example.invalid")
    git("-C", folder, "checkout", "-b", branch)
    (folder / "readme.txt").write_text("first revision\n")
    git("-C", folder, "add", ".")
    git("-C", folder, "commit", "-m", "first")
    return git("-C", folder, "rev-parse", "HEAD")


class FirmwareSourcesTests(unittest.TestCase):
    def test_helper_refresh_pins_both_sources_without_build(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helper = root / "origin-helper.git"
            camera = root / "origin-camera.git"
            helper_sha = repository(helper, branch="main")
            camera_sha = repository(camera, branch="mymarrchWFcam")
            with patch.object(firmware_sources, "ORIGIN", str(helper)), \
                 patch.object(firmware_sources, "REPO_URL", str(camera)):
                empty = firmware_sources.get_source_status("t23n_helper_sd", root=root)
                self.assertEqual([item["sha"] for item in empty["sources"]], [None, None])
                result = firmware_sources.refresh_sources("t23n_helper_sd", root=root)
                self.assertEqual([item["sha"] for item in result["sources"]],
                                 [helper_sha, camera_sha])
                saved = firmware_sources.get_source_status("t23n_helper_sd", root=root)
                self.assertEqual([item["sha"] for item in saved["sources"]],
                                 [helper_sha, camera_sha])
                # No systemd units, Buildroot worktrees or output files.
                self.assertFalse((root / "build/projects/wifcam_helper/jobs").exists())

    def test_unsupported_profile_and_nonfixed_helper_branch_are_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError):
                firmware_sources.refresh_sources("irila_preflight", root=root)
            with self.assertRaises(ValueError):
                firmware_sources.refresh_sources("t23n_helper_sd", "mymarrchWFcam", root=root)
            self.assertFalse((root / "build").exists())

    def test_refuses_mismatched_origin_without_fetch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            helper = root / "origin-helper.git"
            camera = root / "origin-camera.git"
            other = root / "origin-other.git"
            repository(helper, branch="main")
            repository(camera, branch="mymarrchWFcam")
            repository(other, branch="main")
            with patch.object(firmware_sources, "ORIGIN", str(helper)), \
                 patch.object(firmware_sources, "REPO_URL", str(camera)):
                firmware_sources.refresh_sources("t23n_helper_sd", root=root)
            with patch.object(firmware_sources, "ORIGIN", str(other)), \
                 patch.object(firmware_sources, "REPO_URL", str(camera)):
                with self.assertRaisesRegex(ValueError, "origin mismatch"):
                    firmware_sources.refresh_sources("t23n_helper_sd", root=root)


if __name__ == "__main__":
    unittest.main()
