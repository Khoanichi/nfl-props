"""Grade every logged play against real box scores. This is the only honest test of the model.

Usage:  python grade.py
Watch three numbers over 100+ bets: ROI, hit rate vs. predicted, and whether results hold across markets.
Under ~200 graded bets, luck dominates. Don't scale stakes up on a hot week.
"""
import pandas as pd
import nflreadpy as nfl

import config as C
from model import add_derived

log = pd.read_csv(C.BET_LOG)
stats = nfl.load_player_stats(sorted(log.season.unique().tolist())).to_pandas()
stats = add_derived(stats)

rows = []
for r in log.itertuples():
    stat = C.MARKETS[r.market]["stat"]
    g = stats[(stats.player_id == r.player_id) & (stats.season == r.season) & (stats.week == r.week)]
    if g.empty:
        continue  # not played yet, or inactive (book usually voids)
    x = float(g[stat].fillna(0).iloc[0])
    if x == r.line:
        result, units = "P", 0.0
    else:
        win = (x > r.line) if r.side == "Over" else (x < r.line)
        result, units = ("W", r.price - 1) if win else ("L", -1.0)
    rows.append(dict(week=r.week, player=r.player, market=r.market, side=r.side, line=r.line,
                     actual=x, result=result, units=units, p=r.p_blend, ev=r.ev))

g = pd.DataFrame(rows)
if g.empty:
    raise SystemExit("Nothing to grade yet.")
dec = g[g.result != "P"]
print(f"Graded {len(g)} plays ({(g.result == 'P').sum()} pushes)")
print(f"Record: {(dec.result == 'W').sum()}-{(dec.result == 'L').sum()}   "
      f"Hit rate {100 * (dec.result == 'W').mean():.1f}% vs model's {100 * dec.p.mean():.1f}%")
print(f"Profit at 1 unit flat: {g.units.sum():+.2f}u   ROI {100 * g.units.sum() / len(g):+.1f}%   "
      f"(expected ROI {100 * g.ev.mean():+.1f}%)")
print("\nBy market:")
print(g.groupby("market").agg(n=("units", "size"), units=("units", "sum"),
                              hit=("result", lambda s: (s == "W").mean())).round(2).to_string())
g.to_csv("graded.csv", index=False)
print("\nDetail: graded.csv")
