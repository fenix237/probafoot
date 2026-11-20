"""Modèle 1 : Elo avec avantage domicile et modèle de nul."""
import math


class Elo:
    def __init__(self, k=20.0, hfa=65.0, base=1500.0, season_carry=0.75):
        self.k, self.hfa, self.base, self.carry = k, hfa, base, season_carry
        self.r = {}

    def rating(self, team):
        return self.r.get(team, self.base)

    def new_season(self):
        for t in self.r:
            self.r[t] = self.base + self.carry * (self.r[t] - self.base)

    def predict(self, home, away):
        d = self.rating(home) + self.hfa - self.rating(away)
        e = 1.0 / (1.0 + 10 ** (-d / 400.0))
        pd = 0.27 * math.exp(-((d / 475.0) ** 2))
        ph = max(e - pd / 2, 0.01)
        pa = max(1.0 - e - pd / 2, 0.01)
        s = ph + pd + pa
        return [ph / s, pd / s, pa / s]

    def update(self, home, away, hg, ag):
        d = self.rating(home) + self.hfa - self.rating(away)
        e = 1.0 / (1.0 + 10 ** (-d / 400.0))
        s = 1.0 if hg > ag else 0.5 if hg == ag else 0.0
        gd = abs(hg - ag)
        g = 1.0 if gd <= 1 else 1.5 if gd == 2 else (11 + gd) / 8.0
        delta = self.k * g * (s - e)
        self.r[home] = self.rating(home) + delta
        self.r[away] = self.rating(away) - delta
