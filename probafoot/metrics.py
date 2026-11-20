"""Métriques d'évaluation de probabilités 1X2 (issues ordonnées 0=dom, 1=nul, 2=ext)."""
import math

EPS = 1e-12


def log_loss(probs, outcome):
    return -math.log(max(probs[outcome], EPS))


def brier(probs, outcome):
    return sum((p - (1.0 if i == outcome else 0.0)) ** 2 for i, p in enumerate(probs))


def rps(probs, outcome):
    """Ranked Probability Score pour 3 issues ordonnées."""
    cum_p = cum_o = 0.0
    total = 0.0
    for i in range(len(probs) - 1):
        cum_p += probs[i]
        cum_o += 1.0 if i == outcome else 0.0
        total += (cum_p - cum_o) ** 2
    return total / (len(probs) - 1)


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else float("nan")


def score(preds, outcomes):
    return {
        "n": len(outcomes),
        "log_loss": mean(log_loss(p, o) for p, o in zip(preds, outcomes)),
        "rps": mean(rps(p, o) for p, o in zip(preds, outcomes)),
        "brier": mean(brier(p, o) for p, o in zip(preds, outcomes)),
    }


def calibration(preds, outcomes, bins=10):
    """Table (bin, n, p_moyenne, fréquence observée) toutes issues confondues."""
    acc = [[0, 0.0, 0.0] for _ in range(bins)]
    for p, o in zip(preds, outcomes):
        for i, pi in enumerate(p):
            b = min(int(pi * bins), bins - 1)
            acc[b][0] += 1
            acc[b][1] += pi
            acc[b][2] += 1.0 if i == o else 0.0
    rows = []
    for b, (n, sp, sh) in enumerate(acc):
        if n:
            rows.append((b / bins, (b + 1) / bins, n, sp / n, sh / n))
    return rows


def ece(preds, outcomes, bins=10):
    rows = calibration(preds, outcomes, bins)
    total = sum(r[2] for r in rows)
    return sum(r[2] * abs(r[3] - r[4]) for r in rows) / total if total else float("nan")


def bootstrap_ci(values, n_boot=1000, seed=7, alpha=0.05):
    """Intervalle de confiance bootstrap de la moyenne (graine fixe : reproductible)."""
    import random
    if not values:
        return (float("nan"), float("nan"))
    rnd = random.Random(seed)
    n = len(values)
    means = sorted(sum(values[rnd.randrange(n)] for _ in range(n)) / n for _ in range(n_boot))
    return (means[int(alpha / 2 * n_boot)], means[int((1 - alpha / 2) * n_boot) - 1])
