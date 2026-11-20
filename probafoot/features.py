"""Variables de contexte calculées « à la date » (phase 2 : calendrier / repos).

Seules les DATES des matchs précédents sont utilisées (le calendrier est connu à l'avance) :
aucun résultat, donc aucune fuite possible. Les compositions et blessures exigent une source
payante et ne sont pas encore branchées ; le schéma d'événements est déjà prêt à les recevoir.
"""
from collections import defaultdict, deque
from datetime import datetime

REST_CAP_LO, REST_CAP_HI = 2.0, 8.0
WINDOW_DAYS = 14
FEATURE_NAMES = ["rest_diff", "congestion_diff"]


def calendar_features(rows):
    """rows : matchs triés par coup d'envoi (id, kickoff, home, away).
    Retourne {match_id: (rest_h, rest_a, cong_h, cong_a)} calculé avec les seuls matchs antérieurs."""
    last = {}
    recent = defaultdict(deque)
    out = {}
    for r in rows:
        k = datetime.fromisoformat(r["kickoff"])
        vals = []
        for team in (r["home"], r["away"]):
            rest = (k - last[team]).total_seconds() / 86400.0 if team in last else 14.0
            dq = recent[team]
            while dq and (k - dq[0]).total_seconds() / 86400.0 > WINDOW_DAYS:
                dq.popleft()
            vals.append((min(rest, 14.0), len(dq)))
        (rest_h, cong_h), (rest_a, cong_a) = vals
        out[r["id"]] = (rest_h, rest_a, cong_h, cong_a)
        for team in (r["home"], r["away"]):  # mise à jour APRÈS le calcul : le match courant n'y figure pas
            last[team] = k
            recent[team].append(k)
    return out


def _clip(v):
    return max(REST_CAP_LO, min(REST_CAP_HI, v))


def to_vector(raw):
    """(rest_h, rest_a, cong_h, cong_a) -> vecteur centré, réduit : [rest_diff, congestion_diff]."""
    rest_h, rest_a, cong_h, cong_a = raw
    return ((_clip(rest_h) - _clip(rest_a)) / 3.0, (cong_h - cong_a) / 2.0)


def features_as_of(calendar, match_id):
    """Unique point d'accès aux variables d'un match (entraînement, backtest et production)."""
    return to_vector(calendar[match_id])
