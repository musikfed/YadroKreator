import importlib
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

class DatabaseTests(unittest.TestCase):
    def test_wal_persistence_and_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["PEGINELAB_HOME"] = tmp
            sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
            sys.modules.pop("core", None)
            import core
            core = importlib.reload(core)
            db = core.connect()
            try:
                db.execute("INSERT INTO jobs (id,profile,status,created_at,unit,log_path) VALUES (?,?,?,?,?,?)",
                           ("a"*32, "t23n_sd", "queued", core.now(), "peginelab-test", "test.log"))
                db.commit()
                mode = db.execute("PRAGMA journal_mode").fetchone()[0]
                self.assertEqual(mode, "wal")
            finally:
                db.close()
            core.record_status("a"*32, "running")
            self.assertEqual(core.get_job("a"*32)["status"], "running")
            core.record_status("a"*32, "success", exit_code=0)
            job = core.get_job("a"*32)
            self.assertEqual(job["status"], "success")
            self.assertEqual(job["exit_code"], 0)
            self.assertIsNotNone(job["finished_at"])
            self.assertEqual((Path(tmp)/"factory-state").stat().st_mode & 0o777, 0o700)

if __name__ == "__main__":
    unittest.main()
