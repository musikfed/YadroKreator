"""Isolated artifacts ledger: only one job file can be removed, logs survive."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from artifact_catalog import classify, purge_file, safe_owned, expected_path
from project_profiles import job_root
from git_sources import workspace_for

ID="a"*32
SHA="b"*40

def sample(profile="t23n_sd",status="success"):
    return dict(id=ID,profile=profile,status=status,source_sha=SHA,
                created_at="2026-11-04T10:00:00+00:00",details="",exit_code=0)

class ArtifactLedgerTests(unittest.TestCase):
    def test_only_single_t23n_candidate_removed_no_logs_or_baseline(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job=sample()
            src=workspace_for(ID,root)/"out/candidate-sd"
            src.mkdir(parents=True)
            image=src/"thingino-t23-sd.bin"
            image.write_bytes(b"image-from-one-job")
            checksum=src/(image.name+".sha256")
            checksum.write_text("b"*64+"  thingino-t23-sd.bin\n")
            baseline=root/"projects/wificam_T23N/Thingino/thingino-t23-sd.bin"
            baseline.parent.mkdir(parents=True)
            baseline.write_bytes(b"protected-factory-reference")
            log=root/"factory-state/projects/wificam_T23N/logs"/(ID+".log")
            log.parent.mkdir(parents=True)
            log.write_text("Build diagnostic survives")
            with patch("artifact_catalog.saved_report",return_value=None):
                rec=classify(job,root=root,data=root/"factory-state")
            self.assertTrue(rec["available"])
            nbytes,kind=purge_file(job,root=root,data=root/"factory-state")
            self.assertEqual(nbytes,len(b"image-from-one-job"))
            self.assertEqual(kind,"sd_image")
            self.assertFalse(image.exists())
            self.assertFalse(checksum.exists())
            self.assertEqual(log.read_text(),"Build diagnostic survives")
            self.assertEqual(baseline.read_bytes(),b"protected-factory-reference")
            with self.assertRaises(FileNotFoundError):
                purge_file(job,root=root,data=root/"factory-state")

    def test_only_one_irila_audit_removed_without_other_tree(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job=sample("irila_preflight")
            path=expected_path(job,root=root)
            path.parent.mkdir(parents=True)
            import json
            path.write_text(json.dumps({"profile":"irila_preflight","source_sha":SHA}))
            other=root/"build/projects/wificam_T23N/jobs"/ID/"wificam_T23N"/"file"
            other.parent.mkdir(parents=True)
            other.write_text("protected")
            record=classify(job,root=root)
            self.assertTrue(record["available"])
            freed,kind=purge_file(job,root=root)
            self.assertGreater(freed,0)
            self.assertEqual(kind,"audit_json")
            self.assertEqual(other.read_text(),"protected")
            self.assertFalse(path.exists())

    def test_symlinked_artifact_is_not_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job=sample("irila_preflight")
            target=root/"other-project-data"
            target.write_text("do not remove")
            path=expected_path(job,root=root)
            path.parent.mkdir(parents=True)
            path.symlink_to(target)
            self.assertFalse(safe_owned(path,job,root=root))
            with self.assertRaises(FileNotFoundError):
                purge_file(job,root=root)
            self.assertEqual(target.read_text(),"do not remove")

    def test_failed_build_is_not_a_downloadable_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            job=sample(status="failed")
            image=workspace_for(ID,root)/"out/candidate-sd/thingino-t23-sd.bin"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"partial-failed-bytes")
            record=classify(job,root=root)
            self.assertFalse(record["available"])
            self.assertEqual(record["status"],"failed")
            with self.assertRaises(FileNotFoundError):
                purge_file(job,root=root)
            self.assertTrue(image.is_file())

if __name__=="__main__":
    unittest.main()
