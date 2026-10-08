"""Game markets: spreads, totals and moneylines, scored the same way as the props.

Model: a margin-of-victory Elo built from nflverse results (last season carried in at 2/3 weight),
home field worth about 2 points. Spread and moneyline get a model probability from it; totals have
no model here, so they are judged on price alone (best book vs. no-vig consensus).
Odds: The Odds API featured markets (h2h, spreads, totals): 3 credits per pull, cached like props.

Usage:  python game_lines.py            (writes output/games_wk{N}.csv and output/lines_history.csv)
"""
import glob
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

import config as C
from odds import BASE, to_american

HIST = "output/lines_history.csv"
MARGIN_SD = 13.5          # NFL margin of victory spread around the point spread
ELO_PER_POINT = 25        # 25 Elo points = 1 point of spread
HFA = 48                  # home-field advantage in Elo points (about 2 points)
K = 20


# ----------------------------------------------------------------------------- Elo
def elo_ratings(sched, season):
    games = sched[sched.result.notna() & (sched.season >= season - 1)].sort_values(["season", "week"])
    elo = {}
    last_season = None
    for g in games.itertuples():
        if g.season != last_season and last_season is not None:   # new season: regress a third to 1500
            elo = {t: 1500 + (r - 1500) * 2 / 3 for t, r in elo.items()}
        last_season = g.season
        h, a = elo.get(g.home_team, 1500), elo.get(g.away_team, 1500)
        exp_home = 1 / (1 + 10 ** ((a - (h + HFA)) / 400))
        margin = g.home_score - g.away_score
        actual = 1 if margin > 0 else 0 if margin < 0 else 0.5
        diff = (h + HFA - a) if margin > 0 else (a - h - HFA)
        mult = np.log(abs(margin) + 1) * 2.2 / (diff * 0.001 + 2.2)
        shift = K * mult * (actual - exp_home)
        elo[g.home_team], elo[g.away_team] = h + shift, a - shift
    return elo


def model_spread(elo, home, away):
    """Expected home margin (positive = home wins by that much)."""
    return (elo.get(home, 1500) + HFA - elo.get(away, 1500)) / ELO_PER_POINT


# ----------------------------------------------------------------------------- odds
def fetch_game_odds(fresh=False):
    """Featured odds for every upcoming game; reuses a pull newer than CACHE_MAX_AGE_HOURS unless fresh."""
    files = glob.glob(f"{C.CACHE_DIR}/games_*.json")
    stamp = lambda p: datetime.strptime(os.path.basename(p)[6:19], "%Y%m%d_%H%M")
    recent = [p for p in files if (datetime.now() - stamp(p)).total_seconds() < C.CACHE_MAX_AGE_HOURS * 3600]
    if recent and not fresh:
        path = max(recent, key=stamp)
        print(f"Reusing game odds from {path}")
        data = json.load(open(path))
        if not os.path.exists(HIST):
            _append_history(data)
        return data
    if not C.ODDS_API_KEY:
        raise SystemExit("Set ODDS_API_KEY first.")
    q = dict(apiKey=C.ODDS_API_KEY.strip(), markets="h2h,spreads,totals", oddsFormat="decimal")
    q.update({"bookmakers": C.BOOKMAKERS} if C.BOOKMAKERS else {"regions": C.REGIONS})
    r = requests.get(f"{BASE}/odds", params=q, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"Odds API rejected the request ({r.status_code}): {r.text[:200]}")
    data = r.json()
    print(f"Pulled game odds for {len(data)} games. API credits remaining: {r.headers.get('x-requests-remaining')}")
    os.makedirs(C.CACHE_DIR, exist_ok=True)
    path = os.path.join(C.CACHE_DIR, f"games_{datetime.now():%Y%m%d_%H%M}.json")
    json.dump(data, open(path, "w"))
    _append_history(data)
    return data


def _append_history(data):
    rows = []
    for ev in data:
        sp = [o["point"] for bk in ev["bookmakers"] for mk in bk["markets"] if mk["key"] == "spreads"
              for o in mk["outcomes"] if o["name"] == ev["home_team"] and o.get("point") is not None]
        tot = [o["point"] for bk in ev["bookmakers"] for mk in bk["markets"] if mk["key"] == "totals"
               for o in mk["outcomes"] if o["name"] == "Over" and o.get("point") is not None]
        if sp and tot:
            rows.append(dict(ts=datetime.now(timezone.utc).isoformat(timespec="minutes"), event_id=ev["id"],
                             away=ev["away_team"], home=ev["home_team"], commence=ev["commence_time"],
                             spread_home=float(np.median(sp)), total=float(np.median(tot)), books=len(sp)))
    if rows:
        os.makedirs("output", exist_ok=True)
        pd.DataFrame(rows).to_csv(HIST, mode="a", header=not os.path.exists(HIST), index=False)


def flatten_game_odds(data, this_week_only=True):
    rows = []
    for ev in data:
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk.get("outcomes", []):
                    rows.append(dict(event_id=ev["id"], home=ev["home_team"], away=ev["away_team"],
                                     commence=ev["commence_time"], book=bk["key"], market=mk["key"],
                                     name=o["name"], line=o.get("point", np.nan), price=float(o["price"])))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    if this_week_only:
        first = pd.to_datetime(df.commence).min()
        df = df[pd.to_datetime(df.commence) <= first + pd.Timedelta(days=6)]
    return df


def consensus_rows(df):
    """One row per (game, market, side, line): no-vig consensus prob and best price."""
    out = []
    for (eid, market, line), g in df.groupby(["event_id", "market", "line"], dropna=False):
        sides = sorted(g.name.unique())
        if len(sides) != 2:
            continue
        fair = {s: [] for s in sides}
        for book, gb in g.groupby("book"):
            p = {s: 1 / gb[gb.name == s].price.max() for s in sides if (gb.name == s).any()}
            if len(p) == 2:
                tot = sum(p.values())
                for s in sides:
                    fair[s].append(p[s] / tot)
        if not fair[sides[0]]:
            continue
        for s in sides:
            best = g[g.name == s].sort_values("price", ascending=False).iloc[0]
            out.append(dict(event_id=eid, home=best.home, away=best.away, commence=best.commence,
                            market=market, side=s, line=line, p_market=float(np.median(fair[s])),
                            price=float(best.price), book=best.book, n_books=len(fair[s])))
    return pd.DataFrame(out)


# ----------------------------------------------------------------------------- scoring
def score(cons, elo, abbr, sched, season):
    rows = []
    for r in cons.itertuples():
        h, a = abbr.get(r.home, r.home), abbr.get(r.away, r.away)
        mu = model_spread(elo, h, a)
        team = abbr.get(r.side, r.side)
        if r.market == "spreads":
            # P(team covers): team margin > -line
            m = mu if team == h else -mu
            p_model = 1 - norm.cdf(-r.line, loc=m, scale=MARGIN_SD)
            pick = f"{team} {r.line:+g}"
            kind_side = team
        elif r.market == "h2h":
            m = mu if team == h else -mu
            p_model = 1 - norm.cdf(0, loc=m, scale=MARGIN_SD)
            pick = f"{team} moneyline"
            kind_side = team
        else:  # totals: no model, lean on the market
            p_model = r.p_market
            pick = f"{r.side} {r.line:g}"
            kind_side = r.side
        logit = lambda p: np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4)))
        w = C.MODEL_WEIGHT if r.market != "totals" else 0.0
        p_blend = 1 / (1 + np.exp(-(w * logit(p_model) + (1 - w) * logit(r.p_market))))
        ev = p_blend * (r.price - 1) - (1 - p_blend)
        kelly = max(0.0, ev / (r.price - 1)) * C.KELLY_FRACTION
        if r.price > C.MAX_PRICE_DEC:
            continue
        rows.append(dict(player=f"{a} @ {h}", position="GAME", team=team if r.market != "totals" else h, opp=a if team == h else h,
                         market={"spreads": "game_spread", "totals": "game_total", "h2h": "game_moneyline"}[r.market],
                         side=kind_side, line=r.line if pd.notna(r.line) else 0,
                         mean=round(mu, 1) if r.market != "totals" else r.line, games=6, injury="", report_status="",
                         n_books=r.n_books, two_sided=True, player_id="", commence=r.commence,
                         recent=json.dumps(recent_log(sched, season, team if r.market != "totals" else h, r.market, a if team == h else h)),
                         p_model=p_model, p_market=r.p_market, p_blend=p_blend, price=r.price, book=r.book,
                         ev=ev, stake_pct=min(kelly, C.MAX_STAKE_PCT), raw_edge=p_model - r.p_market,
                         pick=pick, model_spread=round(mu, 1)))
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["flags"] = ""
    df.loc[df.raw_edge.abs() > C.MAX_RAW_EDGE, "flags"] += "BIG-GAP:check-news "
    return df.sort_values("ev", ascending=False)


def recent_log(sched, season, team, market, opp_for_total=None):
    """Last 6 results for a team: margin vs closing spread (ATS) or game total vs closing total."""
    g = sched[sched.result.notna() & ((sched.home_team == team) | (sched.away_team == team))]
    g = g[g.season >= season - 1].sort_values(["season", "week"]).tail(C.RECENT_GAMES)
    out = []
    for r in g.itertuples():
        is_home = r.home_team == team
        opp = r.away_team if is_home else r.home_team
        w = f"{'W' if r.season == season else str(r.season)[2:] + 'W'}{int(r.week)}"
        if market == "totals":
            out.append(dict(w=w, opp=opp, v=float(r.home_score + r.away_score), line=float(r.total_line) if pd.notna(r.total_line) else None))
        else:
            margin = (r.home_score - r.away_score) if is_home else (r.away_score - r.home_score)
            spread = (-r.spread_line) if is_home else r.spread_line   # team's own spread, negative = favored
            out.append(dict(w=w, opp=opp, v=float(margin), line=float(spread) if pd.notna(spread) else None))
    return out  # oldest to newest


def main(fresh=False, log=False):
    import nflreadpy as nfl
    from model import load_data
    _, sched, _ = load_data(C.SEASON)
    t = nfl.load_teams().to_pandas()
    abbr = dict(zip(t.team_name, t.team_abbr))
    abbr["Los Angeles Rams"] = "LA"
    data = fetch_game_odds(fresh)
    df = flatten_game_odds(data)
    if df.empty:
        raise SystemExit("No game odds returned.")
    cons = consensus_rows(df)
    elo = elo_ratings(sched, C.SEASON)
    scored = score(cons, elo, abbr, sched, C.SEASON)
    week = int(sched[(sched.season == C.SEASON) & (pd.to_datetime(sched.gameday) >= pd.Timestamp.today().normalize())].week.min())
    os.makedirs("output", exist_ok=True)
    path = f"output/games_wk{week}_{datetime.now():%Y%m%d_%H%M}.csv"
    scored.to_csv(path, index=False)
    good = scored[(scored.ev >= C.MIN_EV) & (scored.raw_edge.abs() <= C.MAX_RAW_EDGE)]
    print(f"{len(scored)} game-line prices scored, {len(good)} at +{C.MIN_EV:.0%} EV or better:")
    print(good.head(15)[["pick", "price", "book", "p_model", "p_market", "ev"]].round(3).to_string(index=False))
    print(f"Saved {path}")
    if log and len(good):
        good = good.drop_duplicates(["player", "market", "side"])
        out = good.assign(season=C.SEASON, week=week, logged_at=datetime.now().isoformat(timespec="minutes"),
                          player_id="")
        cols = ["logged_at", "season", "week", "player_id", "player", "market", "side", "line", "price",
                "book", "p_blend", "ev", "stake_pct"]
        out[cols].to_csv(C.BET_LOG, mode="a", header=not os.path.exists(C.BET_LOG), index=False)
        print(f"Logged {len(good)} game plays to {C.BET_LOG}")


if __name__ == "__main__":
    import sys
    main(fresh="--fresh" in sys.argv, log="--log" in sys.argv)
