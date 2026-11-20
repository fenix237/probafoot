"""Modèle ancré sur le marché : on part du prix du marché et on ne corrige que ce que le modèle apporte en plus.

    p_i  ∝  m_i^wm · d_i^wd · exp(b_i)        (mise en commun log-linéaire, b_H = 0)

m : probabilités du marché sans marge (cotes avant match), d : probabilités du modèle statistique (Dixon-Coles),
wm, wd : poids de chacune, b_D et b_A : biais de classe (nul, extérieur).
Valeurs par défaut (wm=1, wd=0, b=0) : le modèle reproduit exactement le marché.
Ajustement par maximum de vraisemblance avec un a priori qui ramène vers ces valeurs (ridge) : peu de données,
donc le modèle ne s'éloigne du marché que si les données l'y obligent. Problème convexe, résolu par Newton.
"""
import math

from .dixoncoles import solve

PRIOR = (1.0, 0.0, 0.0, 0.0)   # wm, wd, b_D, b_A
EPS = 1e-9


def _features(m, d):
    lm = [math.log(max(x, EPS)) for x in m]
    ld = [math.log(max(x, EPS)) for x in d]
    return [(lm[0], ld[0], 0.0, 0.0), (lm[1], ld[1], 1.0, 0.0), (lm[2], ld[2], 0.0, 1.0)]


def _softmax(z):
    mx = max(z)
    e = [math.exp(v - mx) for v in z]
    s = sum(e)
    return [v / s for v in e]


def _probs(theta, f):
    return _softmax([sum(t * x for t, x in zip(theta, fi)) for fi in f])


class Anchor:
    def __init__(self, ridge=40.0, iters=12, min_samples=200):
        self.ridge, self.iters, self.min_samples = ridge, iters, min_samples
        self.theta = list(PRIOR)
        self.n = 0

    def fit(self, samples):
        """samples : liste de (m, d, issue) avec m et d des triplets de probabilités. Sous min_samples : marché pur."""
        self.n = len(samples)
        if self.n < self.min_samples:
            self.theta = list(PRIOR)
            return self
        feats = [(_features(m, d), y) for m, d, y in samples]
        th = list(PRIOR)
        lam = self.ridge
        for _ in range(self.iters):
            g = [lam * (th[i] - PRIOR[i]) for i in range(4)]
            H = [[lam if i == j else 0.0 for j in range(4)] for i in range(4)]
            for f, y in feats:
                p = _probs(th, f)
                mean = [sum(p[c] * f[c][i] for c in range(3)) for i in range(4)]
                for c in range(3):
                    r = p[c] - (1.0 if c == y else 0.0)
                    for i in range(4):
                        g[i] += r * f[c][i]
                for i in range(4):
                    for j in range(4):
                        H[i][j] += sum(p[c] * f[c][i] * f[c][j] for c in range(3)) - mean[i] * mean[j]
            step = solve(H, g)
            th = [th[i] - step[i] for i in range(4)]
            if max(abs(s) for s in step) < 1e-7:
                break
        self.theta = th
        return self

    def predict(self, m, d):
        return _probs(self.theta, _features(m, d))
