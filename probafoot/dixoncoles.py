"""Modèle 2 : Poisson / Dixon-Coles avec décroissance temporelle.

lambda = exp(att_i - dfn_j + gamma)   (buts attendus du domicile)
mu     = exp(att_j - dfn_i)           (buts attendus de l'extérieur)

Estimation : maximum de vraisemblance Poisson pondérée par mise à jour
itérative des moyennes (exacte pour la loi de Poisson), avec un a priori de
rétrécissement vers la moyenne, puis rho par recherche sur grille.
"""
import math
from collections import defaultdict


def poisson_pmf(lam, kmax):
    out = [math.exp(-lam)]
    for k in range(1, kmax + 1):
        out.append(out[-1] * lam / k)
    return out


def tau(x, y, lam, mu, rho):
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam, mu, rho=0.0, maxg=10):
    ph, pa = poisson_pmf(lam, maxg), poisson_pmf(mu, maxg)
    m = [[max(tau(x, y, lam, mu, rho), 0.0) * ph[x] * pa[y] for y in range(maxg + 1)] for x in range(maxg + 1)]
    s = sum(sum(r) for r in m)
    return [[v / s for v in r] for r in m]


def outcome_probs(m):
    h = d = a = 0.0
    for x, row in enumerate(m):
        for y, v in enumerate(row):
            if x > y:
                h += v
            elif x == y:
                d += v
            else:
                a += v
    return [h, d, a]


def markets(m):
    """Marchés dérivés d'une matrice de scores (une seule source de vérité)."""
    over25 = sum(v for x, r in enumerate(m) for y, v in enumerate(r) if x + y >= 3)
    btts = sum(v for x, r in enumerate(m) for y, v in enumerate(r) if x >= 1 and y >= 1)
    h, d, a = outcome_probs(m)
    return {"1": h, "X": d, "2": a, "over_2.5": over25, "under_2.5": 1 - over25,
            "btts_yes": btts, "btts_no": 1 - btts}


def solve(a, b):
    """Résout a x = b (élimination de Gauss avec pivot) pour de petites matrices."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[piv] = m[piv], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for i in range(n - 1, -1, -1):
        x[i] = (m[i][n] - sum(m[i][j] * x[j] for j in range(i + 1, n))) / m[i][i]
    return x


class DixonColes:
    """matches : (jour, home, away, hg, ag[, x]) où x est un vecteur de contexte de longueur n_ctx.
    Effet de contexte symétrique : log(lambda) += theta.x ; log(mu) -= theta.x (theta régularisé par ridge)."""

    def __init__(self, xi=0.0019, prior=1.0, iters=30, n_ctx=0, ridge=20.0):
        self.xi, self.prior, self.iters = xi, prior, iters
        self.n_ctx, self.ridge = n_ctx, ridge
        self.att, self.dfn, self.gamma, self.rho = {}, {}, 0.25, 0.0
        self.theta = [0.0] * n_ctx
        self.mean_att = 0.0

    def _tx(self, x):
        return sum(t * v for t, v in zip(self.theta, x)) if x else 0.0

    def fit(self, matches, ref_day):
        if not matches:
            return self
        zero = (0.0,) * self.n_ctx
        ms = [(m[0], m[1], m[2], m[3], m[4], m[5] if len(m) > 5 and self.n_ctx else zero) for m in matches]
        w = [math.exp(-self.xi * max(ref_day - m[0], 0)) for m in ms]
        teams = sorted({m[1] for m in ms} | {m[2] for m in ms})
        sw = sum(w)
        goals_per = sum(wi * (m[3] + m[4]) for wi, m in zip(w, ms)) / (2 * sw)
        att = {t: self.att.get(t, math.log(goals_per)) for t in teams}
        dfn = {t: self.dfn.get(t, 0.0) for t in teams}
        gamma = self.gamma
        theta = list(self.theta)
        s = self.prior
        for _ in range(self.iters):
            tx = [sum(t * v for t, v in zip(theta, m[5])) for m in ms]
            num, den = defaultdict(float), defaultdict(float)
            for wi, (_, h, a, hg, ag, _x), t in zip(w, ms, tx):
                num[h] += wi * hg
                den[h] += wi * math.exp(-dfn[a] + gamma + t)
                num[a] += wi * ag
                den[a] += wi * math.exp(-dfn[h] - t)
            for t_ in teams:
                att[t_] = math.log((num[t_] + s * goals_per) / (den[t_] + s))
            num, den = defaultdict(float), defaultdict(float)
            for wi, (_, h, a, hg, ag, _x), t in zip(w, ms, tx):
                num[h] += wi * ag
                den[h] += wi * math.exp(att[a] - t)
                num[a] += wi * hg
                den[a] += wi * math.exp(att[h] + gamma + t)
            for t_ in teams:
                dfn[t_] = -math.log((num[t_] + s) / (den[t_] + s))
            m_ = sum(dfn.values()) / len(dfn)
            for t_ in teams:
                dfn[t_] -= m_
                att[t_] -= m_
            n_h = sum(wi * mm[3] for wi, mm in zip(w, ms))
            d_h = sum(wi * math.exp(att[mm[1]] - dfn[mm[2]] + t) for wi, mm, t in zip(w, ms, tx))
            gamma = math.log(n_h / d_h)
            if self.n_ctx:  # un pas de Newton sur theta (ridge), les autres paramètres fixés
                k = self.n_ctx
                g = [-self.ridge * theta[i] for i in range(k)]
                H = [[self.ridge if i == j else 0.0 for j in range(k)] for i in range(k)]
                for wi, (_, h, a, hg, ag, x) in zip(w, ms):
                    t = sum(th * v for th, v in zip(theta, x))
                    lam = math.exp(att[h] - dfn[a] + gamma + t)
                    mu = math.exp(att[a] - dfn[h] - t)
                    for i in range(k):
                        g[i] += wi * x[i] * ((hg - lam) - (ag - mu))
                        for j in range(k):
                            H[i][j] += wi * x[i] * x[j] * (lam + mu)
                step = solve(H, g)
                theta = [theta[i] + step[i] for i in range(k)]
        self.att, self.dfn, self.gamma, self.theta = att, dfn, gamma, theta
        self.mean_att = sum(att.values()) / len(att)
        self.rho = self._fit_rho(ms, w)
        return self

    def _fit_rho(self, ms, w):
        low = [(wi, m) for wi, m in zip(w, ms) if m[3] <= 1 and m[4] <= 1]
        best, best_ll = 0.0, -1e18
        for k in range(-30, 11):
            rho = k / 100.0
            ll = 0.0
            for wi, (_, h, a, hg, ag, x) in low:
                lam, mu = self.rates(h, a, x)
                t = tau(hg, ag, lam, mu, rho)
                if t <= 0:
                    ll = -1e18
                    break
                ll += wi * math.log(t)
            if ll > best_ll:
                best, best_ll = rho, ll
        return best

    def rates(self, home, away, x=None):
        ah = self.att.get(home, self.mean_att)
        aa = self.att.get(away, self.mean_att)
        dh, da = self.dfn.get(home, 0.0), self.dfn.get(away, 0.0)
        t = self._tx(x) if (x and self.n_ctx) else 0.0
        return math.exp(ah - da + self.gamma + t), math.exp(aa - dh - t)

    def matrix(self, home, away, maxg=10, x=None):
        lam, mu = self.rates(home, away, x)
        return score_matrix(lam, mu, self.rho, maxg)

    def predict(self, home, away, x=None):
        return outcome_probs(self.matrix(home, away, x=x))
