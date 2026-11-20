import copy
import json
import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probafoot import capture, db, service

FIX = Path(__file__).parent / "fixtures" / "odds_epl.json"
NOW = datetime(2026, 11, 20, 12, 0)
KEY = "SECRETKEY123"
TEAMS = ["Arsenal", "Chelsea", "Wolves", "Brighton"]


def seed_matches(conn):
    n = 0
    for rnd in range(30):
        for i, h in enumerate(TEAMS):
            a = TEAMS[(i + 1 + rnd % 3) % 4]
            if a == h:
                continue
            n += 1
            ko = f"2025-{1 + (n // 28) % 12:02d}-{1 + n % 28:02d}T15:00"
            conn.execute("INSERT OR IGNORE INTO matches (league,season,kickoff,home,away,hg,ag) VALUES ('E0','2526',?,?,?,?,?)",
                         (ko, h, a, (n * 7) % 4, (n * 3) % 3))
    conn.commit()


class TestCapture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "c.sqlite")
        seed_matches(self.conn)
        self.payload = json.loads(FIX.read_text(encoding="utf-8"))
        service._MODEL_CACHE.clear()

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def fetcher(self, payload=None, remaining=480):
        return lambda lg, key, regions: (copy.deepcopy(payload if payload is not None else self.payload),
                                         {"remaining": remaining, "used": 500 - remaining})

    def test_parse_skips_malformed_and_invalid_odds(self):
        ids = [e["event_id"] for e in capture.parse(self.payload)]
        self.assertEqual(ids, ["evt-arsenal-chelsea", "evt-wolves-brighton", "evt-unknown"])

    def test_resolve_team_alias_exact_and_unknown(self):
        self.assertEqual(capture.resolve_team("Wolverhampton Wanderers", TEAMS), "Wolves")
        self.assertEqual(capture.resolve_team("Brighton and Hove Albion", TEAMS), "Brighton")
        self.assertEqual(capture.resolve_team("Arsenal FC", TEAMS), "Arsenal")
        self.assertIsNone(capture.resolve_team("Mystery Town", TEAMS))

    def test_store_is_idempotent_and_records_only_changes(self):
        r1 = capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(), now=NOW)
        self.assertTrue(r1[0]["ok"])
        self.assertEqual(r1[0]["events"], 3)
        self.assertEqual(r1[0]["new_ticks"], 4)  # 2 + 1 + 1 bookmakers
        r2 = capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(), now=datetime(2026, 11, 20, 15, 0))
        self.assertEqual(r2[0]["new_ticks"], 0)
        changed = copy.deepcopy(self.payload)
        changed[0]["bookmakers"][0]["markets"][0]["outcomes"][0]["price"] = 1.70
        r3 = capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(changed), now=datetime(2026, 11, 20, 18, 0))
        self.assertEqual(r3[0]["new_ticks"], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM odds_ticks").fetchone()[0], 5)

    def test_unresolved_team_is_kept_for_review(self):
        capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(), now=NOW)
        row = self.conn.execute("SELECT home_db, away_db FROM fixtures WHERE event_id='evt-unknown'").fetchone()
        self.assertIsNone(row["home_db"])
        self.assertEqual(row["away_db"], "Arsenal")
        self.assertEqual(service.capture_status(self.conn)["unresolved_fixtures"], 1)

    def test_quota_guard_suspends_capture(self):
        capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(remaining=15), now=NOW)
        called = []
        res = capture.run_capture(self.conn, ["E0", "F1"], KEY, min_credits=20,
                                  fetcher=lambda *a: called.append(a) or ([], {}), now=NOW)
        self.assertFalse(res[0]["ok"])
        self.assertIn("quota", res[0]["message"])
        self.assertEqual(called, [])  # aucun appel réseau : aucun crédit consommé

    def test_fatal_error_stops_and_never_leaks_key(self):
        def boom(lg, key, regions):
            raise capture.CaptureError("clé API refusée", fatal=True)
        res = capture.run_capture(self.conn, ["E0", "F1"], KEY, fetcher=boom, now=NOW)
        self.assertEqual(len(res), 1)
        log = json.dumps([dict(r) for r in self.conn.execute("SELECT * FROM capture_log")])
        self.assertNotIn(KEY, log)

    def test_fetch_scrubs_key_from_errors(self):
        err = urllib.error.HTTPError(f"https://api.the-odds-api.com/v4/x?apiKey={KEY}", 401, "Unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(capture.CaptureError) as cm:
                capture.fetch("E0", KEY)
        self.assertNotIn(KEY, str(cm.exception))
        self.assertTrue(cm.exception.fatal)
        with self.assertRaises(capture.CaptureError):
            capture.fetch("ZZ", KEY)

    def test_upcoming_best_odds_fair_probs_and_movement(self):
        capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(), now=NOW)
        changed = copy.deepcopy(self.payload)
        for bk in changed[0]["bookmakers"]:
            o = bk["markets"][0]["outcomes"]
            o[0]["price"] = round(o[0]["price"] - 0.15, 2)   # Arsenal raccourcit
        capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(changed), now=datetime(2026, 11, 21, 9, 0))
        up = service.upcoming(self.conn, "E0", now=NOW)["items"]
        self.assertEqual([i["home"] for i in up], ["Arsenal", "Wolverhampton Wanderers", "Mystery Town"])
        a = up[0]
        self.assertAlmostEqual(sum(a["fair"]), 1.0, places=9)
        self.assertEqual(a["best"][2]["odds"], 4.60)           # meilleure cote pour Chelsea (extérieur)
        self.assertEqual(a["best"][1]["odds"], 3.70)           # et pour le nul
        self.assertGreater(a["move"][0], 0)                     # la probabilité d'Arsenal a monté
        self.assertAlmostEqual(sum(a["move"]), 0.0, places=9)
        self.assertTrue(a["resolved"])
        self.assertAlmostEqual(sum(a["model"]), 1.0, places=6)
        self.assertEqual(len(a["ev"]), 3)
        self.assertIsNone(up[2]["model"])                       # équipe non résolue : pas d'estimation inventée

    def test_replay_from_file_needs_no_key(self):
        r = capture.capture_from_file(self.conn, "E0", FIX, now=NOW)
        self.assertEqual(r["events"], 3)

    def test_past_fixtures_are_hidden(self):
        capture.run_capture(self.conn, ["E0"], KEY, fetcher=self.fetcher(), now=NOW)
        up = service.upcoming(self.conn, "E0", now=datetime(2026, 12, 6, 15, 0))["items"]
        self.assertEqual([i["home"] for i in up], ["Mystery Town"])  # Wolves-Brighton (14:00) a commencé : masqué


if __name__ == "__main__":
    unittest.main()
