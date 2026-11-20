import math
import random
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from probafoot import backtest, db, ingest, metrics
from probafoot.anchor import Anchor, PRIOR


def synth(n, informative, seed=3):
    """Marché = vérité bruitée ; le modèle d est soit informatif (voit l'écart), soit du bruit pur."""
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        truth = [rnd.uniform(.2, .6), rnd.uniform(.2, .3)]
        truth.append(1 - truth[0] - truth[1])
        y = rnd.choices([0, 1, 2], weights=truth)[0]
        noise = [math.exp(rnd.gauss(0, .15)) for _ in range(3)]
        m = [t * e for t, e in zip(truth, noise)]
        m = [x / sum(m) for x in m]
        if informative:      # d corrige exactement le bruit du marché
            d = truth
        else:
            d = [rnd.random() for _ in range(3)]
            d = [x / sum(d) for x in d]
        out.append((m, d, y))
    return out


class TestAnchor(unittest.TestCase):
    def test_default_is_pure_market(self):
        a = Anchor()
        m, d = [.5, .3, .2], [.2, .3, .5]
        for x, y in zip(a.predict(m, d), m):
            self.assertAlmostEqual(x, y, places=9)
        self.assertEqual(a.theta, list(PRIOR))

    def test_too_few_samples_stays_market(self):
        a = Anchor(min_samples=200).fit(synth(50, True))
        self.assertEqual(a.theta, list(PRIOR))

    def test_probabilities_sum_to_one(self):
        a = Anchor().fit(synth(600, True))
        p = a.predict([.4, .3, .3], [.5, .25, .25])
        self.assertAlmostEqual(sum(p), 1.0, places=9)
        self.assertTrue(all(0 < x < 1 for x in p))

    def test_informative_model_gets_weight_and_improves_log_loss(self):
        tr, te = synth(1500, True, seed=1), synth(1500, True, seed=2)
        a = Anchor().fit(tr)
        self.assertGreater(a.theta[1], 0.1)
        self.assertGreater(Anchor(ridge=2.0).fit(tr).theta[1], a.theta[1])   # a priori moins serré -> poids plus fort
        ll_a = metrics.mean(metrics.log_loss(a.predict(m, d), y) for m, d, y in te)
        ll_m = metrics.mean(metrics.log_loss(m, y) for m, d, y in te)
        self.assertLess(ll_a, ll_m)

    def test_noise_model_is_ignored_and_never_much_worse_than_market(self):
        tr, te = synth(1500, False, seed=1), synth(1500, False, seed=2)
        a = Anchor().fit(tr)
        self.assertLess(abs(a.theta[1]), 0.15)       # la ridge empêche de suivre du bruit
        ll_a = metrics.mean(metrics.log_loss(a.predict(m, d), y) for m, d, y in te)
        ll_m = metrics.mean(metrics.log_loss(m, y) for m, d, y in te)
        self.assertLess(ll_a - ll_m, 0.01)

    def test_fit_is_deterministic(self):
        s = synth(400, True)
        self.assertEqual(Anchor().fit(s).theta, Anchor().fit(s).theta)


CSV_HEAD = "Div,Date,Time,HomeTeam,AwayTeam,FTHG,FTAG,PSH,PSD,PSA,PSCH,PSCD,PSCA,B365H,B365D,B365A"


def make_two_seasons(dirp):
    teams = ["Alpha", "Beta", "Gamma", "Delta", "Eps", "Zeta"]
    out = {}
    for season, year in (("2324", 2023), ("2425", 2024)):
        rows = [CSV_HEAD]
        n = 0
        for rnd in range(14):
            for i, h in enumerate(teams):
                a = teams[(i + 1 + rnd % 5) % 6]
                if a == h:
                    continue
                n += 1
                d, mo = 1 + n % 28, 8 + (n // 28) % 4
                rows.append(f"E0,{d:02d}/{mo:02d}/{year},15:00,{h},{a},{(n * 7) % 4},{(n * 3) % 3},2.1,3.4,3.6,2.0,3.4,3.7,2.05,3.4,3.7")
        f = Path(dirp) / f"{season}_E0.csv"
        f.write_text("\n".join(rows) + "\n", encoding="utf-8")
        out[season] = f
    return out


class TestAnchorBacktest(unittest.TestCase):
    def test_anchor_trains_only_on_results_known_before_each_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "t.sqlite")
            for season, f in make_two_seasons(tmp).items():
                ingest.ingest_file(conn, f, "E0", season)
            r = backtest.run(conn, "E0", ["2425"], refit_days=1, save=False, warmup_seasons=["2324"])
            self.assertEqual(len(r["preds"]["anchor"]), len(r["outcomes"]))
            self.assertEqual(set(r["preds"]), {"market", "market_pre", "elo", "dc", "dc_ctx", "anchor"})
            # échantillons de calage <= nombre de matchs réellement joués avant le dernier match évalué (jamais plus)
            total = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            self.assertLessEqual(r["anchor_samples"], total - 1)
            for p in r["preds"]["anchor"]:
                self.assertAlmostEqual(sum(p), 1.0, places=9)
            conn.close()

    def test_without_enough_history_anchor_equals_pre_match_market(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "t.sqlite")
            f = make_two_seasons(tmp)["2425"]
            ingest.ingest_file(conn, f, "E0", "2425")
            r = backtest.run(conn, "E0", ["2425"], refit_days=1, save=False, warmup_seasons=[])
            # pas de saison de calage : les premiers matchs reproduisent exactement l'ancre (marché avant match)
            for pa, pm in list(zip(r["preds"]["anchor"], r["preds"]["market_pre"]))[:20]:
                for x, y in zip(pa, pm):
                    self.assertAlmostEqual(x, y, places=9)
            conn.close()


if __name__ == "__main__":
    unittest.main()
