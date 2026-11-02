"""One-use/private download authorization, including expiry and replay guards."""
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import download_access as tickets


class DownloadTicketTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = {k:getattr(tickets,k) for k in ("ROOT","DATA","STORE","LOCK")}
        self.data = Path(self.temp.name)/"factory-state"
        tickets.ROOT = Path(self.temp.name)
        tickets.DATA = self.data
        tickets.STORE = self.data/"download-access.json"
        tickets.LOCK = self.data/"download-access.lock"
        self.job="a"*32
        self.mocks = [
            patch.object(tickets,"get_job",return_value={"id":self.job,"status":"success","profile":"t23n_sd"}),
            patch.object(tickets,"artifact_path",return_value=Path(self.temp.name)/"image.bin"),
            patch.object(tickets,"saved_report",return_value={"verified":True}),
        ]
        for p in self.mocks:p.start()

    def tearDown(self):
        for p in self.mocks:p.stop()
        for key,value in self.old.items():setattr(tickets,key,value)
        self.temp.cleanup()

    def test_valid_token_is_one_use_only(self):
        token=tickets.issue(self.job)
        self.assertTrue(len(token)>=30)
        self.assertNotIn(token,tickets.STORE.read_text())
        self.assertEqual(tickets.STORE.stat().st_mode & 0o777,0o600)
        self.assertFalse(tickets.consume("b"*32,token))
        self.assertFalse(tickets.consume(self.job,"not-the-token"))
        self.assertTrue(tickets.consume(self.job,token))
        self.assertFalse(tickets.consume(self.job,token))

    def test_expired_token_rejected(self):
        token=tickets.issue(self.job)
        obj=json.loads(tickets.STORE.read_text())
        obj["expires"]=int(time.time())-1
        tickets.STORE.write_text(json.dumps(obj))
        self.assertFalse(tickets.consume(self.job,token))

    def test_private_export_requires_preflight(self):
        with patch.object(tickets,"saved_report",return_value=None):
            with self.assertRaisesRegex(ValueError,"preflight"):
                tickets.issue(self.job)

    def test_failed_build_cannot_mint_ticket(self):
        with patch.object(tickets,"get_job",return_value={"id":self.job,"status":"failed"}):
            with self.assertRaises(ValueError):
                tickets.issue(self.job)


if __name__=="__main__":
    unittest.main()
