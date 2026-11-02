"""Time and estimated progress are retrospective, not a compiler percentage."""
import unittest
from build_metrics import decorate_jobs


class TimingTests(unittest.TestCase):
    def test_no_history_is_indeterminate(self):
        running=[dict(id="a",profile="t23n_sd",repo_ref="main",
                      status="running",started_at="2026-11-02T10:00:00+00:00",
                      finished_at=None)]
        decorate_jobs(running,current="2026-11-02T10:05:00+00:00")
        self.assertIsNone(running[0]["progress_percent"])
        self.assertEqual(running[0]["elapsed_seconds"], 300)
        self.assertIsNone(running[0]["eta_seconds"])

    def test_historical_same_branch_and_status_only(self):
        now="2026-11-02T10:05:00+00:00"
        jobs=[
            dict(id="current",profile="t23n_sd",repo_ref="mymarrchWFcam",
                 status="running",started_at="2026-11-02T10:00:00+00:00",finished_at=None),
            dict(id="old1",profile="t23n_sd",repo_ref="mymarrchWFcam",
                 status="success",started_at="2026-11-01T10:00:00+00:00",
                 finished_at="2026-11-01T10:10:00+00:00"),
            dict(id="other",profile="t23n_sd",repo_ref="main",
                 status="success",started_at="2026-11-01T10:00:00+00:00",
                 finished_at="2026-11-01T10:30:00+00:00"),
            dict(id="failed",profile="t23n_sd",repo_ref="mymarrchWFcam",
                 status="failed",started_at="2026-11-01T10:00:00+00:00",
                 finished_at="2026-11-01T10:01:00+00:00"),
        ]
        decorate_jobs(jobs,current=now)
        self.assertEqual(jobs[0]["estimate_seconds"],600)
        self.assertEqual(jobs[0]["estimate_samples"],1)
        self.assertEqual(jobs[0]["eta_seconds"],300)
        self.assertLess(jobs[0]["progress_percent"],100)
        self.assertEqual(jobs[1]["progress_percent"],100)
        self.assertIsNone(jobs[3]["progress_percent"])

    def test_elapsed_exceeds_eta_never_completes_automatically(self):
        jobs=[dict(id="running",profile="t23n_sd",repo_ref="main",status="running",
                   started_at="2026-11-02T09:00:00+00:00",finished_at=None),
              dict(id="old",profile="t23n_sd",repo_ref="main",status="success",
                   started_at="2026-11-01T10:00:00+00:00",
                   finished_at="2026-11-01T10:01:00+00:00")]
        decorate_jobs(jobs,current="2026-11-02T10:05:00+00:00")
        self.assertEqual(jobs[0]["progress_percent"],95)
        self.assertIsNone(jobs[0]["eta_seconds"])


if __name__ == "__main__":
    unittest.main()
