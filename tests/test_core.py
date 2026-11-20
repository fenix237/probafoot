import json
import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probafoot import backtest, db, features, ingest, market, metrics
from probafoot.dixoncoles import DixonColes, markets, outcome_probs, score_matrix
from probafoot.elo import Elo


class TestMarket(unittest.TestCase):
    def test_devig_sums_to_one(self):
        for f in (market.devig_proportional, market.devig_power):
            p = f([2.0, 3.4, 3.8])
            self.assertAlmostEqual(sum(p), 1.0, places=9)
            self.assertTrue(all(0 < x < 1 for x in p))

    def test_devig_power_fair_odds_unchanged(self):
        p = market.devig_power([2.0, 4.0, 4.0])
        self.assertAlmostEqual(p[0], 0.5, places=6)

    def test_ev_and_kelly_documented_example(self):
        # cahier des charges : p=0,50, cote 2,20 -> EV +10 %, Kelly plein ~8,3 %, quart ~2,1 %
        self.assertAlmostEqual(market.ev(0.5, 2.2), 0.10, places=9)
        self.assertAlmostEqual(market.kelly_fraction(0.5, 2.2, fraction=1.0, cap=1.0), 0.1 / 1.2, places=9)
        self.assertAlmostEqual(market.kelly_fraction(0.5, 2.2, fraction=0.25, cap=1.0), 0.1 / 1.2 / 4, places=9)

    def test_kelly_cap_and_negative_ev(self):
        self.assertEqual(market.kelly_fraction(0.5, 2.2), 0.02)
        self.assertEqual(market.kelly_fraction(0.3, 2.0), 0.0)

    def test_clv_sign(self):
        self.assertGreater(market.clv(2.2, 0.50), 0)
        self.assertLess(market.clv(1.9, 0.50), 0)


class TestMetrics(unittest.TestCase):
    def test_perfect_and_uniform(self):
        self.assertAlmostEqual(metrics.log_loss([1, 0, 0], 0), 0.0, places=9)
        self.assertAlmostEqual(metrics.rps([1, 0, 0], 0), 0.0)
        self.assertAlmostEqual(metrics.log_loss([1 / 3] * 3, 1), math.log(3), places=9)
        self.assertAlmostEqual(metrics.brier([0, 1, 0], 1), 0.0)

    def test_rps_penalises_far_errors_more(self):
        near = metrics.rps([0.0, 1.0, 0.0], 0)   # annonce nul, victoire dom
        far = metrics.rps([0.0, 0.0, 1.0], 0)    # annonce ext, victoire dom
        self.assertLess(near, far)

    def test_bootstrap_reproducible(self):
        v = [random.Random(1).random() for _ in range(50)]
        self.assertEqual(metrics.bootstrap_ci(v), metrics.bootstrap_ci(v))


class TestElo(unittest.TestCase):
    def test_probs_sum_and_home_edge(self):
        e = Elo()
        p = e.predict("A", "B")
        self.assertAlmostEqual(sum(p), 1.0, places=9)
        self.assertGreater(p[0], p[2])

    def test_winner_gains_loser_loses_zero_sum(self):
        e = Elo()
        e.update("A", "B", 3, 0)
        self.assertGreater(e.rating("A"), 1500)
        self.assertAlmostEqual(e.rating("A") + e.rating("B"), 3000.0, places=9)


class TestDixonColes(unittest.TestCase):
    def test_matrix_normalised_and_markets_coherent(self):
        m = score_matrix(1.6, 1.1, rho=-0.1)
        self.assertAlmostEqual(sum(map(sum, m)), 1.0, places=9)
        mk = markets(m)
        self.assertAlmostEqual(mk["1"] + mk["X"] + mk["2"], 1.0, places=9)
        self.assertAlmostEqual(mk["over_2.5"] + mk["under_2.5"], 1.0, places=9)
        self.assertEqual(outcome_probs(m)[0], mk["1"])

    def test_recovers_strong_team(self):
        rnd = random.Random(42)
        teams = ["S", "M1", "M2", "M3", "W"]
        strength = {"S": 0.5, "M1": 0.0, "M2": 0.0, "M3": 0.0, "W": -0.5}
        data, day = [], 0

        def pois(lam):
            l, k, p = math.exp(-lam), 0, 1.0
            while True:
                p *= rnd.random()
                if p <= l:
                    return k
                k += 1
        for _ in range(12):
            for h in teams:
                for a in teams:
                    if h != a:
                        day += 1
                        data.append((day, h, a, pois(math.exp(0.2 + strength[h] - strength[a] * 0.0 + 0.25)),
                                     pois(math.exp(0.2 + strength[a]))))
        dc = DixonColes().fit(data, day)
        self.assertGreater(dc.att["S"], dc.att["W"])
        self.assertGreater(dc.gamma, 0.0)
        p = dc.predict("S", "W")
        self.assertAlmostEqual(sum(p), 1.0, places=9)
        self.assertGreater(p[0], p[2])

    def test_unknown_team_falls_back_without_error(self):
        dc = DixonColes().fit([(1, "A", "B", 1, 0), (2, "B", "A", 2, 2)], 3)
        self.assertAlmostEqual(sum(dc.predict("A", "Z")), 1.0, places=9)


FAKE_CSV = """Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A
E0,10/08/2024,15:00,Man United,Fulham,1,0,1.5,4.2,7.0,1.4,4.5,8.0,1.55,4.0,6.5
E0,10/08/2024,17:30,Arsenal,Chelsea,2,2,2.0,3.5,3.8,2.1,3.4,3.6,2.05,3.4,3.7
E0,11/08/2024,15:00,Liverpool,Everton,,,1.4,5,8,1.4,5,8,1.4,5,8
"""


class TestIngestAndLeakage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        self.csv = Path(self.tmp.name) / "2425_E0.csv"
        self.csv.write_text(FAKE_CSV, encoding="utf-8")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_ingest_is_idempotent_and_skips_unplayed(self):
        n1 = ingest.ingest_file(self.conn, self.csv, "E0", "2425")
        n2 = ingest.ingest_file(self.conn, self.csv, "E0", "2425")
        self.assertEqual((n1, n2), (2, 0))
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM events").fetchone()[0], 2)
        self.assertEqual(self.conn.execute("SELECT home FROM matches ORDER BY kickoff").fetchone()[0], "Manchester United")

    def test_events_are_bitemporal(self):
        ingest.ingest_file(self.conn, self.csv, "E0", "2425")
        for r in self.conn.execute("SELECT occurred_at, known_at, payload FROM events"):
            self.assertGreaterEqual(r["known_at"], r["occurred_at"])
            self.assertIn("hg", json.loads(r["payload"]))
        with self.assertRaises(Exception):  # CHECK known_at >= occurred_at
            self.conn.execute("INSERT INTO events (event_id,event_type,payload,occurred_at,known_at,source) "
                              "VALUES ('x','T','{}','2024-01-02T00:00','2024-01-01T00:00','s')")

    def test_odds_stored(self):
        ingest.ingest_file(self.conn, self.csv, "E0", "2425")
        n = self.conn.execute("SELECT COUNT(*) FROM odds_snapshots WHERE bookmaker='PS' AND kind='close'").fetchone()[0]
        self.assertEqual(n, 2)

    def test_no_future_result_is_used(self):
        """Anti-fuite : le résultat d'un match ne doit jamais nourrir sa propre prédiction."""
        rows = []
        # 2 saisons synthétiques, A bat toujours B à domicile et à l'extérieur
        conn = self.conn
        mid = 0
        for i in range(60):
            mid += 1
            ko = f"2024-{1 + i // 28:02d}-{1 + i % 28:02d}T15:00"
            conn.execute("INSERT INTO matches (id,league,season,kickoff,home,away,hg,ag) VALUES (?,?,?,?,?,?,?,?)",
                         (mid, "T", "2425", ko, "A" if i % 2 == 0 else "B", "B" if i % 2 == 0 else "A", 3, 0))
            conn.execute("INSERT INTO events (event_id,event_type,match_id,payload,occurred_at,known_at,source) "
                         "VALUES (?,?,?,?,?,?,?)", (f"e{mid}", "MATCH_RESULT", mid, "{}", ko, ko[:11] + "23:00", "t"))
            conn.execute("INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?)", (mid, "PS", "close", 2.0, 3.5, 3.8))
            conn.execute("INSERT INTO odds_snapshots VALUES (?,?,?,?,?,?)", (mid, "PS", "pre", 2.0, 3.5, 3.8))
        conn.commit()
        r = backtest.run(conn, "T", ["2425"], refit_days=1, save=False)
        # premier match : aucun historique -> probabilités quasi uniformes côté Elo (pas de fuite du 3-0 du match lui-même)
        first_elo = r["preds"]["elo"][0]
        self.assertAlmostEqual(first_elo[0], Elo().predict("A", "B")[0], places=9)
        self.assertEqual(len(r["preds"]["dc"]), len(r["outcomes"]))


class TestFeatures(unittest.TestCase):
    ROWS = [
        {"id": 1, "kickoff": "2024-08-01T15:00", "home": "A", "away": "B"},
        {"id": 2, "kickoff": "2024-08-04T15:00", "home": "A", "away": "C"},
        {"id": 3, "kickoff": "2024-08-20T15:00", "home": "B", "away": "A"},
    ]

    def test_rest_and_congestion_use_only_previous_matches(self):
        f = features.calendar_features(self.ROWS)
        self.assertEqual(f[1], (14.0, 14.0, 0, 0))            # aucun match avant
        self.assertEqual(f[2], (3.0, 14.0, 1, 0))             # A a joué 3 j avant, C jamais
        rest_h, rest_a, cong_h, cong_a = f[3]
        self.assertAlmostEqual(rest_h, 19.0 if False else 14.0)  # B : dernier match il y a 19 j -> plafonné à 14
        self.assertAlmostEqual(rest_a, 14.0)                  # A : dernier match il y a 16 j -> plafonné
        self.assertEqual((cong_h, cong_a), (0, 0))            # hors fenêtre de 14 j

    def test_vector_is_clipped_and_antisymmetric(self):
        v = features.to_vector((2.0, 8.0, 3, 1))
        w = features.to_vector((8.0, 2.0, 1, 3))
        self.assertAlmostEqual(v[0], -w[0])
        self.assertAlmostEqual(v[1], -w[1])
        self.assertEqual(features.to_vector((0.5, 30.0, 0, 0))[0], (2.0 - 8.0) / 3.0)

    def test_dc_with_context_runs_and_theta_has_right_size(self):
        data = [(i, "A" if i % 2 else "B", "B" if i % 2 else "A", i % 3, (i + 1) % 2, (0.5, -0.2)) for i in range(1, 80)]
        dc = DixonColes(n_ctx=2).fit(data, 80)
        self.assertEqual(len(dc.theta), 2)
        self.assertAlmostEqual(sum(dc.predict("A", "B", x=(1.0, 0.0))), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
