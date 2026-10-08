"""Find +EV player props for an NFL week.

Usage:
  python find_value.py --week 5                 # pulls live odds (uses API credits)
  python find_value.py --week 5 --cache cache/odds_20261008_0900.json   # re-run on saved odds, free
  python find_value.py --week 5 --log           # also append the plays to bet_log.csv for grading later
"""
import argparse
import glob
import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import nflreadpy as nfl

import config as C
from model import load_data, build_projections, prob_over_under, norm_name
from odds import fetch_props, market_table, to_american

BAD_STATUS = {"Out", "Doubtful"}


def team_lookup(sched_teams):
    t = nfl.load_teams().to_pandas()
    t = t[t.team_abbr.isin(sched_teams)]
    return dict(zip(t.team_name, t.team_abbr))


def injury_table(inj, week):
    i = inj[inj.week == week].copy()
    if i.empty:
        return pd.DataFrame(columns=["player_id", "injury"])
    i["injury"] = (i.report_status.fillna("") + " " +
                   i.practice_status.fillna("").str.replace(" in Practice", "").str.replace("Participation", "")).str.strip()
    return i.rename(columns={"gsis_id": "player_id"})[["player_id", "injury", "report_status"]].drop_duplicates("player_id", keep="last")


def evaluate(row):
    po, pu, push = prob_over_under(row["mean"], row["var"], row["kind"], row["line"])
    fair_over = row["fair_over"]
    res = []
    for side, p_model, p_mkt, price, book in [
        ("Over", po, fair_over, row["best_over"], row["book_over"]),
        ("Under", pu, 1 - fair_over, row["best_under"], row["book_under"]),
    ]:
        if pd.isna(price) or price > C.MAX_PRICE_DEC:
            continue
        w = C.MODEL_WEIGHT if row["two_sided"] else C.ONE_SIDED_MODEL_WEIGHT
        logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
        p_blend = 1 / (1 + np.exp(-(w * logit(p_model) + (1 - w) * logit(p_mkt))))
        p_loss = max(0.0, 1 - p_blend - push)
        ev = p_blend * (price - 1) - p_loss
        kelly = max(0.0, ev / (price - 1)) * C.KELLY_FRACTION
        res.append(dict(side=side, p_model=p_model, p_market=p_mkt, p_blend=p_blend, price=price,
                        book=book, ev=ev, stake_pct=min(kelly, C.MAX_STAKE_PCT),
                        raw_edge=p_model - p_mkt))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", default="auto", help="week number, or auto = next week with games")
    ap.add_argument("--season", type=int, default=C.SEASON)
    ap.add_argument("--cache", help="saved odds JSON to reuse (default: newest cache file if recent enough)")
    ap.add_argument("--fresh", action="store_true", help="always pull new odds")
    ap.add_argument("--log", action="store_true", help="append plays to the bet log")
    ap.add_argument("--all", action="store_true", help="show every priced prop, not just +EV")
    a = ap.parse_args()

    print("Loading nflverse data...")
    ps, sched, inj = load_data(a.season)
    if a.week == "auto":
        today = pd.Timestamp.today().normalize()
        upcoming = sched[(sched.season == a.season) & (pd.to_datetime(sched.gameday) >= today)]
        a.week = int(upcoming.week.min()) if len(upcoming) else int(sched[sched.season == a.season].week.max())
        print(f"Auto-selected week {a.week}")
    a.week = int(a.week)
    proj = build_projections(ps, sched, a.season, a.week)
    proj = proj.merge(injury_table(inj, a.week), on="player_id", how="left")

    if not a.cache and not a.fresh:
        def stamp(p):  # time is in the file name, since git checkout resets modification times
            return datetime.strptime(os.path.basename(p)[5:18], "%Y%m%d_%H%M")
        recent = [p for p in glob.glob(f"{C.CACHE_DIR}/odds_*.json")
                  if (datetime.now() - stamp(p)).total_seconds() < C.CACHE_MAX_AGE_HOURS * 3600]
        if recent:
            a.cache = max(recent, key=stamp)
            print(f"Reusing odds from {a.cache} (use --fresh to pull new lines)")
    print("Loading odds...")
    mt = market_table(fetch_props(use_cache=a.cache))
    if mt.empty:
        raise SystemExit("No props returned. Books usually post most props by Thursday.")
    names = team_lookup(set(sched.home_team) | set(sched.away_team))
    mt["home_abbr"], mt["away_abbr"] = mt.home.map(names), mt.away.map(names)
    mt["name_key"] = mt.player.map(norm_name)

    # match each prop to a projection: same normalized name, same market, team in that game
    m = mt.merge(proj, on=["name_key", "market"], how="left")
    m = m[(m.team == m.home_abbr) | (m.team == m.away_abbr)]
    unmatched = set(mt.player) - set(m.player)
    if unmatched:
        print(f"{len(unmatched)} props had no projection (rookies/new roles/name mismatch), e.g.: "
              + ", ".join(sorted(unmatched)[:6]))

    # last games for each matched player, so the page can show the recent box scores next to the line
    hist = ps[ps.player_id.isin(m.player_id.dropna())].sort_values("t", ascending=False)
    hist = hist.groupby("player_id").head(C.RECENT_GAMES)
    recent = {}
    for pid, g in hist.groupby("player_id"):
        for market, spec in C.MARKETS.items():
            recent[(pid, market)] = json.dumps([
                dict(w=f"{'W' if s == a.season else str(s)[2:] + 'W'}{int(w)}", opp=o, v=float(v), cur=bool(s == a.season))
                for s, w, o, v in zip(g.season, g.week, g.opponent_team, g[spec["stat"]].fillna(0))][::-1])  # oldest to newest

    plays = []
    for _, r in m.iterrows():
        for res in evaluate(r):
            plays.append({**{k: r[k] for k in ["player", "position", "team", "opp", "market", "line",
                                                "mean", "games", "injury", "report_status", "n_books",
                                                "two_sided", "player_id", "commence"]},
                          "recent": recent.get((r.player_id, r.market), "[]"), **res})
    df = pd.DataFrame(plays)
    df["flags"] = ""
    df.loc[df.report_status.isin(BAD_STATUS), "flags"] += "OUT/DOUBTFUL "
    df.loc[df.report_status.eq("Questionable"), "flags"] += "Q-tag "
    df.loc[df.raw_edge.abs() > C.MAX_RAW_EDGE, "flags"] += "BIG-GAP:check-news "
    df.loc[df.games < 4, "flags"] += "small-sample "
    df.loc[~df.two_sided, "flags"] += "one-sided-mkt "

    df = df.sort_values("ev", ascending=False)
    os.makedirs("output", exist_ok=True)
    out_path = f"output/props_wk{a.week}_{datetime.now():%Y%m%d_%H%M}.csv"
    df.to_csv(out_path, index=False)

    # the shown list drops BIG-GAP rows: when the model and market disagree that much, the market
    # almost always knows something (new starter, injury), and keeps one line per player and side
    show = df if a.all else df[(df.ev >= C.MIN_EV) & ~df.report_status.isin(BAD_STATUS)
                               & (df.raw_edge.abs() <= C.MAX_RAW_EDGE)]
    show = show.drop_duplicates(["player", "market", "side"])
    view = show.assign(
        pick=show.player + " " + show.side + " " + show.line.astype(str) + " " + show.market.str.replace("player_", ""),
        odds=show.price.map(to_american),
        proj=show["mean"].round(1),
        model=(100 * show.p_model).round(1), market_=(100 * show.p_market).round(1),
        ev_pct=(100 * show.ev).round(1), stake=(100 * show.stake_pct).round(2),
    )[["pick", "odds", "book", "proj", "model", "market_", "ev_pct", "stake", "flags"]]
    print(f"\n{len(show)} plays at +{C.MIN_EV:.0%} EV or better (model/market = win %, stake = % of bankroll):\n")
    print(view.head(40).to_string(index=False) if len(view) else "None this run. That's normal: no edge means no bet.")
    print(f"\nFull sheet: {out_path}")

    if a.log and len(show):
        log = show.assign(season=a.season, week=a.week, logged_at=datetime.now().isoformat(timespec="minutes"))
        cols = ["logged_at", "season", "week", "player_id", "player", "market", "side", "line", "price",
                "book", "p_blend", "ev", "stake_pct"]
        log[cols].to_csv(C.BET_LOG, mode="a", header=not os.path.exists(C.BET_LOG), index=False)
        print(f"Logged {len(show)} plays to {C.BET_LOG}. After the games: python grade.py")


if __name__ == "__main__":
    main()
