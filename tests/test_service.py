import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probafoot import backtest, db, ingest, service

CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A
"""


def make_csv(path):
    rows = [CSV.rstrip("\n")]
    teams = ["Alpha", "Beta", "Gamma", "Delta"]
    day = 0
    for rnd in range(14):
        for i, h in enumerate(teams):
            a = teams[(i + 1 + rnd % 3) % 4]
            if a == h:
                continue
            day += 1
            d = 1 + day % 28
            m = 1 + day // 28
            hg, ag = (day * 7) % 4, (day * 3) % 3
            rows.append(f"E0,{d:02d}/{m:02d}/2024,15:00,{h},{a},{hg},{ag},2.0,3.4,3.8,2.1,3.3,3.6,2.05,3.4,3.7")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class TestService(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        csv = Path(self.tmp.name) / "2425_E0.csv"
        make_csv(csv)
        ingest.ingest_file(self.conn, csv, "E0", "2425")
        self.run = backtest.run(self.conn, "E0", ["2425"], refit_days=1)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_run_is_registered_with_summary(self):
        runs = service.runs(self.conn, "E0")
        self.assertEqual(runs[0]["run_id"], self.run["run_id"])
        self.assertIn("scores", runs[0]["summary"])

    def test_matches_list_and_pagination(self):
        r = service.matches(self.conn, league="E0", limit=5, offset=0)
        self.assertEqual(len(r["items"]), 5)
        self.assertGreater(r["total"], 5)
        it = r["items"][0]
        for m in ("market", "elo", "dc"):
            self.assertAlmostEqual(sum(it["probs"][m]), 1.0, places=6)
        r2 = service.matches(self.conn, league="E0", limit=5, offset=5)
        self.assertNotEqual(r["items"][0]["id"], r2["items"][0]["id"])

    def test_match_detail_has_events_with_both_dates(self):
        mid = service.matches(self.conn, league="E0", limit=1)["items"][0]["id"]
        d = service.match_detail(self.conn, mid)
        self.assertTrue(d["events"])
        self.assertGreaterEqual(d["events"][0]["known_at"], d["events"][0]["occurred_at"])
        self.assertAlmostEqual(sum(d["close_fair_probs"]), 1.0, places=6)

    def test_performance_structure(self):
        p = service.performance(self.conn, league="E0")
        self.assertEqual(p["n"], len(self.run["outcomes"]))
        self.assertIn("dc_vs_market", p["paired"])
        self.assertTrue(p["calibration"])
        self.assertGreater(p["models"]["dc"]["log_loss"], 0)

    def test_predict_and_errors(self):
        r = service.predict(self.conn, "E0", "Alpha", "Beta")
        self.assertAlmostEqual(r["markets"]["1"]["p"] + r["markets"]["X"]["p"] + r["markets"]["2"]["p"], 1.0, places=6)
        self.assertIn("garantie", r["notice"])
        with self.assertRaises(service.NotFound):
            service.predict(self.conn, "E0", "Alpha", "Nope")
        with self.assertRaises(service.NotFound):
            service.predict(self.conn, "E0", "Alpha", "Alpha")
        with self.assertRaises(service.NotFound):
            service.match_detail(self.conn, 999999)

    def test_no_run_gives_clear_error(self):
        other = db.connect(Path(self.tmp.name) / "empty.sqlite")
        with self.assertRaises(service.NotFound):
            service.matches(other, league="E0")
        other.close()


if __name__ == "__main__":
    unittest.main()
