"""Source-level regression: do not leak host loader paths into Buildroot."""
from pathlib import Path
import unittest


class WorkerBuildEnvTests(unittest.TestCase):
    def test_ld_library_path_removed_before_child(self):
        text = (Path(__file__).resolve().parents[1] / "worker.py").read_text()
        self.assertIn('env.pop("LD_LIBRARY_PATH", None)', text)
        self.assertLess(text.index('env.pop("LD_LIBRARY_PATH", None)'),
                        text.index('subprocess.Popen('))
        self.assertIn('"THINGINO_FAST": "0"', text)
        self.assertIn('"PUBLISH": "0"', text)
        self.assertIn('no new per-job SD candidate', text)
        self.assertIn('out/candidate-sd/thingino-t23-sd.bin', text)
        self.assertIn('out/private-sd/thingino-t23-sd.bin', text)

    def test_factory_source_isolated_per_job(self):
        text = (Path(__file__).resolve().parents[1] / "git_sources.py").read_text()
        self.assertIn('git("', text)
        self.assertIn('"worktree", "add", "--detach"', text)


if __name__ == "__main__":
    unittest.main()
