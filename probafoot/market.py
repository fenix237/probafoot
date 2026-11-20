"""Cotes : retrait de marge, valeur espérée, Kelly fractionné, CLV."""


def implied(odds):
    return [1.0 / o for o in odds]


def overround(odds):
    return sum(implied(odds))


def devig_proportional(odds):
    q = implied(odds)
    s = sum(q)
    return [x / s for x in q]


def devig_power(odds, tol=1e-12):
    """Trouve k tel que sum((1/o)^k) = 1 (corrige le biais favoris / outsiders)."""
    q = implied(odds)
    if abs(sum(q) - 1.0) < tol:
        return q
    lo, hi = 0.5, 5.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if sum(x ** mid for x in q) > 1.0:
            lo = mid
        else:
            hi = mid
    k = (lo + hi) / 2
    p = [x ** k for x in q]
    s = sum(p)
    return [x / s for x in p]


def ev(p, odds):
    """Valeur espérée pour une mise unitaire."""
    return p * odds - 1.0


def kelly_fraction(p, odds, fraction=0.25, cap=0.02):
    """Kelly fractionné et plafonné. 0 si l'EV n'est pas positive."""
    if odds <= 1.0:
        return 0.0
    full = (p * odds - 1.0) / (odds - 1.0)
    if full <= 0:
        return 0.0
    return min(fraction * full, cap)


def clv(odds_taken, p_close_fair):
    """> 0 : la cote obtenue était meilleure que le prix juste de clôture."""
    return odds_taken * p_close_fair - 1.0
