"""Cross-project isolation and conservative single-build policy."""
from __future__ import annotations
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from project_profiles import PROFILES, profile_workspace
from irila_preflight import REQUIRED, audit
from irila_sources import checkout_irila


class SeparateProjectsTests(unittest.TestCase):
    def test_no_ambiguous_project_or_image_paths(self):
        root = Path("/1tbdisk/PegineLab")
        jid = "a" * 32
        w = profile_workspace(jid, "t23n_sd", root=root)
        i = profile_workspace(jid, "irila_preflight", root=root)
        self.assertNotEqual(i, w)
        self.assertEqual(w, root / "build/jobs" / jid / "wificam_T23N")
        self.assertEqual(i, root / "build/jobs" / jid / "Irila_baikal_v1.0")
        self.assertNotEqual(PROFILES["irila_preflight"]["repository"],
                            PROFILES["t23n_sd"]["repository"])
        self.assertNotIn("irila_img", PROFILES)
        with self.assertRaises(ValueError):
            profile_workspace("../../outside", "irila_preflight", root=root)

    def test_irila_detached_git_checkout_and_read_only_report(self):
        jid = "b" * 32
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            upstream = root / "source_repo"
            upstream.mkdir()
            subprocess.run(["git", "init", "--initial-branch=main", str(upstream)],
                           check=True, capture_output=True)
            subprocess.run(["git", "-C", str(upstream), "config", "user.email", "ci@example.invalid"], check=True)
            subprocess.run(["git", "-C", str(upstream), "config", "user.name", "Test"], check=True)
            for name in REQUIRED:
                file = upstream / name
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text("fixture\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(upstream), "add", "."], check=True)
            subprocess.run(["git", "-C", str(upstream), "commit", "-m", "fixture"], check=True,
                           capture_output=True)
            with tempfile.TemporaryFile(mode="w+b") as log:
                snapshot, sha = checkout_irila(jid, log, root=root, repo_url=str(upstream))
            self.assertEqual(snapshot, profile_workspace(jid, "irila_preflight", root=root))
            self.assertTrue((snapshot / "hardware/acer_swift3_sf314-41.json").is_file())
            self.assertEqual(subprocess.check_output(["git", "-C", str(snapshot), "rev-parse", "HEAD"]).decode().strip(), sha)
            report = audit(jid, sha, root=root)
            self.assertTrue(report["ready_for_manual_ci"])
            self.assertFalse(report["linux_kernel_build_started"])
            self.assertFalse(report["usb_image_built"])
            self.assertFalse(report["hardware_boot_verified"])
            self.assertFalse((root / "build/jobs" / jid / "irina_baikal_1.0.img").exists())
            self.assertEqual(json.loads((root / "build/jobs" / jid / "irila-source-audit.json").read_text())["source_sha"], sha)
            with self.assertRaises(RuntimeError):
                checkout_irila(jid, log, root=root, repo_url=str(upstream))

    def test_worker_file_lock_rejects_second_worker(self):
        import fcntl
        import worker
        jid = "c" * 32
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            lock_path = root / "build/locks/factory-build.lock"
            lock_path.parent.mkdir(parents=True)
            with lock_path.open("a+b") as held:
                fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                with patch.object(worker, "ROOT", root), patch.object(worker, "get_job", return_value={
                    "profile": "irila_preflight", "repo_ref": "main", "id": jid
                }), patch.object(worker, "record_status") as status:
                    self.assertEqual(worker.main(jid), 3)
                    self.assertEqual(status.call_args.args[:2], (jid, "failed"))

    def test_sources_are_never_treated_as_firmware_images(self):
        from artifact_checks import artifact_path
        with self.assertRaises(ValueError):
            artifact_path({"profile": "irila_preflight", "status": "success", "id": "d"*32})


if __name__ == "__main__":
    unittest.main()
