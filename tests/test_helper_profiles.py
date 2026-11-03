"""Independent opt-in profile validation: never inject untrusted build scripts."""
import json
from pathlib import Path
import tempfile
import unittest

from helper_profiles import (checked_profile, helper_profile_source, job_env,
                             load_helper_profile, snapshot_profile)

VALID = {
    "schema": "peginelab.wifcam-helper.build-preset.v1",
    "camera": "galayou_g2_t23n_sc2336_atbm6012bx",
    "branch": "mymarrchWFcam",
    "build_env": {"WIFICAM_WEBRTC": "0"},
    "requires_hardware_verification": True,
    "notes": "Pinned candidate; hardware validation still pending",
}
ID = "a" * 32


class HelperProfileTests(unittest.TestCase):
    def test_only_expected_env_can_cross_projects(self):
        self.assertEqual(checked_profile(VALID, branch="mymarrchWFcam"), VALID)
        for env in (
            {"LD_PRELOAD": "/tmp/malicious.so"},
            {"WIFICAM_WEBRTC": "1", "PUBLISH": "1"},
            {"WIFICAM_WEBRTC": "0; rm -rf /"},
            {"WIFICAM_WEBRTC": 1},
        ):
            with self.subTest(env=env), self.assertRaises(ValueError):
                checked_profile({**VALID, "build_env": env}, branch="mymarrchWFcam")

    def test_wrong_camera_branch_and_verified_claim_refused(self):
        for patched in (
            {"branch": "main"},
            {"camera": "t31"},
            {"requires_hardware_verification": False},
            {"notes": "x" * 900},
            {"unexpected": "env"},
        ):
            with self.subTest(patched=patched), self.assertRaises(ValueError):
                checked_profile({**VALID, **patched}, branch="mymarrchWFcam")
        with self.assertRaises(ValueError):
            checked_profile(VALID, branch="main")

    def test_job_snapshots_are_immutable_and_private(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.assertEqual(job_env(ID, root=root), {})
            path = snapshot_profile(ID, VALID, root=root)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(job_env(ID, root=root), {"WIFICAM_WEBRTC": "0"})
            with self.assertRaises(FileExistsError):
                snapshot_profile(ID, VALID, root=root)
            path.unlink()
            path.symlink_to(root / "evil.json")
            with self.assertRaises(ValueError):
                job_env(ID, root=root)

    def test_helper_source_is_sibling_and_not_executable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = helper_profile_source(root)
            self.assertEqual(path, root / "projects/wifcam_helper/profiles/t23n_lean.json")
            with self.assertRaises(ValueError):
                load_helper_profile(root=root)
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(VALID))
            self.assertEqual(load_helper_profile(root=root), VALID)
            path.unlink()
            path.symlink_to(root / "other")
            with self.assertRaises(ValueError):
                load_helper_profile(root=root)

    def test_worker_never_runs_helper_scripts(self):
        worker = (Path(__file__).resolve().parents[1] / "worker.py").read_text()
        self.assertIn('job_env(job_id, root=ROOT, branch=job["repo_ref"])', worker)
        self.assertIn('"PUBLISH": "0"', worker)
        self.assertNotIn('shell=True', worker)


if __name__ == "__main__":
    unittest.main()
