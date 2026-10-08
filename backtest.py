"""Walk-forward backtest: for each past week, project using ONLY earlier data, then compare to what happened.

What it tells you:
  1. Accuracy: does the adjusted projection beat a plain recent average? (MAE, lower is better)
  2. Calibration: when the model says 60%, does it hit about 60%?
Free data has no historical prop lines, so the "line" here is the player's plain recent average
rounded to x.5, which is roughly where books open. It tests the model, not real-world ROI.
Real ROI comes from grade.py once you have logged picks.

Usage:  python backtest.py --season 2025 --start 4 --end 18
"""
import argparse
import numpy as np
import pandas as pd

import config as C
from model import load_data, build_projections, prob_over_under


def run(season, start, end):
    ps, sched, _ = load_data(season)
    rows = []
    for wk in range(start, end + 1):
        actual = ps[(ps.season == season) & (ps.week == wk)]
        if actual.empty:
            continue
        proj = build_projections(ps, sched, season, wk, team_of=actual.set_index("player_id").team)
        for market, m in C.MARKETS.items():
            p = proj[proj.market == market].merge(
                actual[["player_id", m["stat"]]].rename(columns={m["stat"]: "actual"}), on="player_id")
            p = p[p.base_mean >= {"yards": 15, "count": 2, "td": 0.15}[m["kind"]]]
            for r in p.itertuples():
                line = np.floor(r.base_mean) + 0.5
                po, pu, _ = prob_over_under(r.mean, r.var, r.kind, line)
                rows.append((wk, market, r.mean, r.base_mean, r.actual, po, int(r.actual > line)))
        print(f"week {wk}: {len(rows)} projections so far", end="\r")
    df = pd.DataFrame(rows, columns=["week", "market", "model", "naive", "actual", "p_over", "hit_over"])
    print()
    return df


def report(df):
    print("\n=== Accuracy (MAE, lower is better) ===")
    acc = df.groupby("market").apply(lambda d: pd.Series({
        "n": len(d),
        "model_MAE": (d.model - d.actual).abs().mean(),
        "naive_MAE": (d.naive - d.actual).abs().mean(),
    }), include_groups=False)
    acc["improvement_%"] = 100 * (1 - acc.model_MAE / acc.naive_MAE)
    print(acc.round(2).to_string())

    print("\n=== Calibration (predicted P(over) vs how often it actually went over) ===")
    df["bucket"] = pd.cut(df.p_over, [0, .3, .4, .45, .5, .55, .6, .7, 1])
    cal = df.groupby("bucket", observed=True).agg(n=("hit_over", "size"),
                                                   predicted=("p_over", "mean"),
                                                   actual=("hit_over", "mean"))
    print(cal.round(3).to_string())
    brier = ((df.p_over - df.hit_over) ** 2).mean()
    base = ((df.hit_over.mean() - df.hit_over) ** 2).mean()
    print(f"\nBrier score: {brier:.4f}  (coin-flip baseline {base:.4f}; lower is better)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=C.SEASON - 1)
    ap.add_argument("--start", type=int, default=4)
    ap.add_argument("--end", type=int, default=18)
    a = ap.parse_args()
    d = run(a.season, a.start, a.end)
    report(d)
    d.to_csv(f"backtest_{a.season}.csv", index=False)
