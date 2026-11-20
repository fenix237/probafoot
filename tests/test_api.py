import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from fastapi.testclient import TestClient
except Exception:  # FastAPI absent : tests ignorés
    TestClient = None

from probafoot import backtest, db, ingest
from test_service import make_csv


@unittest.skipIf(TestClient is None, "fastapi non installé")
class TestApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import os
        cls.tmp = tempfile.TemporaryDirectory()
        path = Path(cls.tmp.name) / "api.sqlite"
        conn = db.connect(path)
        csv = Path(cls.tmp.name) / "2425_E0.csv"
        make_csv(csv)
        ingest.ingest_file(conn, csv, "E0", "2425")
        backtest.run(conn, "E0", ["2425"], refit_days=1)
        conn.close()
        os.environ["PROBAFOOT_DB"] = str(path)
        from probafoot.api import app
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_health_and_leagues(self):
        self.assertEqual(self.client.get("/v1/health").json()["status"], "ok")
        self.assertEqual(self.client.get("/v1/leagues").json()["items"][0]["league"], "E0")

    def test_matches_and_detail_include_disclaimer(self):
        r = self.client.get("/v1/matches?league=E0&limit=3").json()
        self.assertEqual(len(r["items"]), 3)
        self.assertIn("risques de perte", r["disclaimer"])
        d = self.client.get(f"/v1/matches/{r['items'][0]['id']}").json()
        self.assertIn("events", d)

    def test_performance_and_predict(self):
        self.assertIn("dc_vs_market", self.client.get("/v1/performance?league=E0").json()["paired"])
        r = self.client.get("/v1/predict?league=E0&home=Alpha&away=Beta").json()
        self.assertAlmostEqual(sum(r["markets"][k]["p"] for k in ("1", "X", "2")), 1.0, places=6)

    def test_errors_are_404_and_validation_422(self):
        self.assertEqual(self.client.get("/v1/matches/999999").status_code, 404)
        self.assertEqual(self.client.get("/v1/predict?league=E0&home=Alpha&away=Zzz").status_code, 404)
        self.assertEqual(self.client.get("/v1/matches?limit=9999").status_code, 422)

    def test_cors_header_for_local_front(self):
        r = self.client.get("/v1/health", headers={"Origin": "http://localhost:3000"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:3000")


if __name__ == "__main__":
    unittest.main()
