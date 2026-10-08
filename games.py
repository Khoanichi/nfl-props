"""Game dashboard: spreads and totals, how they have moved since we first saw them, where the public's
tickets and money are, and a "trap?" flag when those disagree. Writes docs/games.html.

Data sources:
  - Lines: The Odds API featured markets (spreads, totals), 2 credits per run. Each run is saved to
    output/lines_history.csv so the dashboard can show the opener vs. now.
  - Public splits: Action Network's public scoreboard feed (ticket % and money %). This is an
    unofficial feed and can change or disappear; if it does, the page still renders without splits.
    You can also drop a splits.csv in the folder (columns: away,home,market,side,tickets,money).

Usage:  python games.py
"""
import json
import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

import config as C
from odds import BASE

HIST = "output/lines_history.csv"
AN_URL = "https://api.actionnetwork.com/web/v2/scoreboard/nfl"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) prop_model/1.0"}


# ----------------------------------------------------------------------------- lines
def fetch_lines():
    """Consensus spread (home) and total per upcoming game. Returns a DataFrame; empty on failure."""
    if not C.ODDS_API_KEY:
        return pd.DataFrame()
    r = requests.get(f"{BASE}/odds", params=dict(apiKey=C.ODDS_API_KEY.strip(), regions=C.REGIONS,
                                                 markets="spreads,totals", oddsFormat="american"), timeout=30)
    if r.status_code != 200:
        print(f"  lines: Odds API {r.status_code} {r.text[:120]}")
        return pd.DataFrame()
    rows = []
    for ev in r.json():
        sp, tot = [], []
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk.get("outcomes", []):
                    if mk["key"] == "spreads" and o["name"] == ev["home_team"] and o.get("point") is not None:
                        sp.append(o["point"])
                    if mk["key"] == "totals" and o["name"] == "Over" and o.get("point") is not None:
                        tot.append(o["point"])
        if sp and tot:
            rows.append(dict(ts=datetime.now(timezone.utc).isoformat(timespec="minutes"), event_id=ev["id"],
                             away=ev["away_team"], home=ev["home_team"], commence=ev["commence_time"],
                             spread_home=float(np.median(sp)), total=float(np.median(tot)), books=len(sp)))
    df = pd.DataFrame(rows)
    if len(df):
        os.makedirs("output", exist_ok=True)
        df.to_csv(HIST, mode="a", header=not os.path.exists(HIST), index=False)
    return df


def lines_with_openers():
    if not os.path.exists(HIST):
        return pd.DataFrame()
    h = pd.read_csv(HIST).sort_values("ts")
    first = h.groupby("event_id").first()[["spread_home", "total", "ts"]].rename(
        columns={"spread_home": "open_spread", "total": "open_total", "ts": "open_ts"})
    now = h.groupby("event_id").last()
    cur = now.join(first).reset_index()
    cur = cur[pd.to_datetime(cur.commence) > datetime.now(timezone.utc) - pd.Timedelta(hours=4)]
    if len(cur):  # only this week's slate, not next week's early lines
        cur = cur[pd.to_datetime(cur.commence) <= pd.to_datetime(cur.commence).min() + pd.Timedelta(days=6)]
    return cur


# ----------------------------------------------------------------------------- public splits
def _pct(d, *path):
    for k in path:
        d = d.get(k, {}) if isinstance(d, dict) else {}
    return d if isinstance(d, (int, float)) else None


def fetch_splits():
    """{(away_name, home_name): {spread_home_tickets, spread_home_money, over_tickets, over_money}}"""
    out = {}
    if os.path.exists("splits.csv"):
        s = pd.read_csv("splits.csv")
        for r in s.itertuples():
            key = (r.away, r.home)
            d = out.setdefault(key, {})
            side = "spread_home" if (r.market == "spread" and r.side == "home") else \
                   "spread_away" if r.market == "spread" else "over" if r.side == "over" else "under"
            d[f"{side}_tickets"], d[f"{side}_money"] = r.tickets, r.money
        return _normalize(out)
    try:
        r = requests.get(AN_URL, params=dict(bookIds=15, periods="event"), headers=HEADERS, timeout=30)
        games = r.json().get("games", [])
    except Exception as e:
        print(f"  splits: unavailable ({e})")
        return {}
    for g in games:
        teams = {t["id"]: t.get("full_name") for t in g.get("teams", [])}
        away, home = teams.get(g.get("away_team_id")), teams.get(g.get("home_team_id"))
        books = g.get("markets") or {}
        ev = (books.get("15") or next(iter(books.values()), {}) or {}).get("event") or {}
        if not (away and home and ev):
            continue
        d = {}
        for o in ev.get("spread", []):
            side = "spread_home" if o.get("side") == "home" else "spread_away"
            d[f"{side}_tickets"], d[f"{side}_money"] = _pct(o, "bet_info", "tickets", "percent"), _pct(o, "bet_info", "money", "percent")
        for o in ev.get("total", []):
            side = "over" if o.get("side") == "over" else "under"
            d[f"{side}_tickets"], d[f"{side}_money"] = _pct(o, "bet_info", "tickets", "percent"), _pct(o, "bet_info", "money", "percent")
        if any(v for v in d.values()):
            out[(away, home)] = d
    return _normalize(out)


def _normalize(out):
    for d in out.values():
        for a, b in [("spread_home", "spread_away"), ("over", "under")]:
            for k in ("tickets", "money"):
                if d.get(f"{a}_{k}") is None and d.get(f"{b}_{k}") is not None:
                    d[f"{a}_{k}"] = 100 - d[f"{b}_{k}"]
    return out


def trap_flags(row, s, a="away", h="home"):
    """Plain-language reasons this game smells like a trap. Empty list = nothing unusual."""
    flags = []
    if not s or s.get("spread_home_tickets") is None:
        return flags
    th, mh = s["spread_home_tickets"], s.get("spread_home_money")
    pub_side = h if th >= 50 else a
    pub_pct = max(th, 100 - th)
    move = row.spread_home - row.open_spread if pd.notna(row.open_spread) else 0  # negative = home more favored
    moved_toward_home = move < -0.4
    moved_toward_away = move > 0.4
    if pub_pct >= 70:
        flags.append(f"{pub_pct:.0f}% of tickets on {pub_side}")
    if (pub_side == h and moved_toward_away) or (pub_side == a and moved_toward_home):
        flags.append("line moved against the public side (reverse line movement)")
    if mh is not None and abs(mh - th) >= 15:
        big = h if mh > th else a
        flags.append(f"money leans {big} much harder than tickets (bigger bets on {big})")
    return flags


# ----------------------------------------------------------------------------- props per game
def props_by_game():
    import glob
    files = glob.glob("output/props_wk*.csv")
    if not files:
        return {}
    df = pd.read_csv(max(files, key=os.path.getmtime))
    df = df[(df.ev >= C.MIN_EV) & (df.raw_edge.abs() <= C.MAX_RAW_EDGE)
            & ~df.report_status.isin(["Out", "Doubtful"])]
    df = df.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side"])
    out = {}
    for r in df.itertuples():
        key = frozenset([r.team, r.opp])
        out.setdefault(key, [])
        if len(out[key]) < 4:
            out[key].append(f"{r.player} {r.side} {r.line:g} {r.market.replace('player_', '').replace('_', ' ')} "
                            f"({'+' if r.price >= 2 else ''}{round((r.price - 1) * 100) if r.price >= 2 else round(-100 / (r.price - 1))}, +{100 * r.ev:.0f}%)")
    return out


# ----------------------------------------------------------------------------- charts
def bar_svg(labels, values, color="#2e7d4f", width=560, fmt="{:.0f}"):
    if not labels:
        return ""
    h, pad, bw = 22, 4, 300
    vmax = max(abs(v) for v in values) or 1
    rows = []
    for i, (l, v) in enumerate(zip(labels, values)):
        y = i * (h + pad)
        w = bw * abs(v) / vmax
        x = 180 if v >= 0 else 180 - w
        rows.append(f'<text x="172" y="{y + 15}" text-anchor="end" font-size="12" fill="#6e6a5e">{l}</text>'
                    f'<rect x="{x}" y="{y}" width="{w:.1f}" height="{h}" rx="3" fill="{color if v >= 0 else "#c8372d"}"/>'
                    f'<text x="{180 + bw + 6}" y="{y + 15}" font-size="12" fill="#1c1b17">{fmt.format(v)}</text>')
    H = len(labels) * (h + pad)
    return f'<svg viewBox="0 0 {width} {H}" width="100%" role="img">{"".join(rows)}</svg>'


def charts_html():
    import glob
    blocks = []
    files = glob.glob("output/props_wk*.csv")
    if files:
        df = pd.read_csv(max(files, key=os.path.getmtime))
        good = df[(df.ev >= C.MIN_EV) & (df.raw_edge.abs() <= C.MAX_RAW_EDGE)].drop_duplicates(["player", "market", "side"])
        by_mkt = good.groupby("market").size().sort_values(ascending=False)
        blocks.append("<h3>Plays with an edge, by market</h3>" +
                      bar_svg([m.replace("player_", "").replace("_", " ") for m in by_mkt.index], by_mkt.values.tolist()))
        sides = good.groupby("side").size()
        blocks.append("<h3>Overs vs unders among the plays</h3>" + bar_svg(sides.index.tolist(), sides.values.tolist(), "#b9922f"))
    if os.path.exists("graded.csv"):
        g = pd.read_csv("graded.csv")
        wk = g.groupby("week").units.sum().cumsum()
        blocks.append("<h3>Running profit by week (units, flat 1u bets)</h3>" +
                      bar_svg([f"Week {w}" for w in wk.index], wk.values.tolist(), fmt="{:+.1f}"))
    return "".join(f'<section class="chart">{b}</section>' for b in blocks)


# ----------------------------------------------------------------------------- page
CSS = """
:root{--felt:#1b3f32;--paper:#f6f1e4;--paper-edge:#e7dfc9;--ink:#1c1b17;--ink-soft:#6e6a5e;--chip:#c8372d;--gold:#b9922f;--ok:#2e7d4f;
--display:"Oswald","Arial Narrow",Impact,sans-serif;--body:"Source Sans 3","Segoe UI",system-ui,sans-serif;
box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*,*::before,*::after{box-sizing:inherit}
body{margin:0;background:var(--felt);color:var(--ink);font-family:var(--body);font-size:17px;line-height:1.35}
header,main,nav{max-width:640px;margin:0 auto}
header{color:var(--paper);padding:20px 16px 6px}
header h1{font:600 34px var(--display);margin:0;line-height:1}
header p{margin:6px 0 0;color:#c9d6cd;font-size:15px}
nav{padding:8px 16px 14px;display:flex;gap:8px}
nav a{color:var(--paper);text-decoration:none;border:1.5px solid #8fb0a0;border-radius:999px;padding:8px 14px;font-weight:600;font-size:15px}
nav a.on{background:var(--paper);color:var(--ink);border-color:var(--paper)}
main{padding:0 12px 40px}
.card{background:var(--paper);border-radius:6px;margin:0 0 14px;padding:14px 16px;box-shadow:0 2px 0 var(--paper-edge)}
.gh{display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.gh h2{font:600 22px var(--display);margin:0}
.gh small{color:var(--ink-soft);font-size:14px;white-space:nowrap}
.lines{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0 6px;font-size:14px;color:var(--ink-soft)}
.lines b{display:block;font:600 20px var(--display);color:var(--ink)}
.lines .mv{font-size:13px}
.up{color:var(--ok)}.dn{color:var(--chip)}
.split{margin-top:10px}
.split .t{display:flex;justify-content:space-between;font-size:13px;color:var(--ink-soft);margin-bottom:3px}
.bar{display:flex;height:18px;border-radius:4px;overflow:hidden;background:#ebe4d2;margin-bottom:4px}
.bar span{display:flex;align-items:center;justify-content:center;font:600 12px var(--body);color:#fff;min-width:0;overflow:hidden}
.bar .a{background:#5b7f9b}.bar .h{background:#8c6a3f}
.bar.money .a{background:#3f6584}.bar.money .h{background:#6f4f2a}
.trap{margin-top:10px;padding:8px 10px;border-radius:5px;background:#f1dcd8;color:#8a2a22;font-size:14px}
.trap b{font-family:var(--display);font-size:16px;margin-right:6px}
.calm{margin-top:10px;font-size:13px;color:var(--ink-soft)}
.props{margin-top:10px;font-size:14px;color:var(--ink);border-top:1px dashed #cfc6ad;padding-top:8px}
.props div{padding:2px 0}
.chart{background:var(--paper);border-radius:6px;padding:12px 16px 6px;margin-bottom:14px}
.chart h3{font:600 17px var(--display);margin:0 0 8px}
.empty{background:var(--paper);border-radius:6px;padding:20px 18px}
footer{color:#a7bbb0;font-size:13px;text-align:center;padding:0 20px 30px;max-width:640px;margin:0 auto}
"""


def split_block(label, left, right, lt, lm, rt, rm):
    def bar(cls, lv, rv):
        if lv is None or rv is None:
            return ""
        return (f'<div class="bar {cls}"><span class="a" style="width:{lv}%">{lv:.0f}%</span>'
                f'<span class="h" style="width:{rv}%">{rv:.0f}%</span></div>')
    if lt is None:
        return ""
    return (f'<div class="split"><div class="t"><span>{left}</span><span>{label}</span><span>{right}</span></div>'
            f'{bar("", lt, rt)}{bar("money", lm, rm)}'
            f'<div class="t"><span>top bar = share of tickets, bottom = share of money</span></div></div>')


def build():
    cur = lines_with_openers()
    splits = fetch_splits()
    props = props_by_game()
    import nflreadpy as nfl
    t = nfl.load_teams().to_pandas()
    abbr = dict(zip(t.team_name, t.team_abbr))
    abbr["Los Angeles Rams"] = "LA"
    cards = []
    for r in cur.sort_values("commence").itertuples():
        s = splits.get((r.away, r.home), {})
        a, h = abbr.get(r.away, r.away), abbr.get(r.home, r.home)
        fav = h if r.spread_home < 0 else a
        sp_txt = f"{fav} {-abs(r.spread_home):g}"
        mv_sp = r.spread_home - r.open_spread if pd.notna(r.open_spread) else 0
        mv_tot = r.total - r.open_total if pd.notna(r.open_total) else 0
        def mv(x, kind):
            if abs(x) < 0.25:
                return '<span class="mv">no move since opener</span>'
            if kind == "sp":
                who = h if x < 0 else a
                return f'<span class="mv {"dn" if x < 0 else "up"}">moved {abs(x):g} toward {who}</span>'
            return f'<span class="mv {"up" if x > 0 else "dn"}">{"up" if x > 0 else "down"} {abs(x):g} since opener</span>'
        flags = trap_flags(r, s, a, h)
        kick = pd.to_datetime(r.commence).tz_convert("America/Los_Angeles").strftime("%a %I:%M %p")
        plist = props.get(frozenset([a, h]), [])
        cards.append(f"""
<article class="card">
  <div class="gh"><h2>{a} @ {h}</h2><small>{kick} PT</small></div>
  <div class="lines">
    <div>Spread<b>{sp_txt}</b>{mv(mv_sp, "sp")}</div>
    <div>Total<b>{r.total:g}</b>{mv(mv_tot, "tot")}</div>
  </div>
  {split_block("Spread", a, h, s.get("spread_away_tickets"), s.get("spread_away_money"), s.get("spread_home_tickets"), s.get("spread_home_money"))}
  {split_block("Total", "Over", "Under", s.get("over_tickets"), s.get("over_money"), s.get("under_tickets"), s.get("under_money"))}
  {('<div class="trap"><b>Trap?</b>' + "; ".join(flags) + '</div>') if len(flags) >= 2 else
   ('<div class="calm">' + "; ".join(flags) + '</div>') if flags else
   ('<div class="calm">Public and line agree. Nothing unusual.</div>' if s else '<div class="calm">No public split data for this game.</div>')}
  {('<div class="props">' + "".join(f"<div>{p}</div>" for p in plist) + '</div>') if plist else ''}
</article>""")
    note = ("" if splits else "<div class='empty'>Public betting splits were not available this run, so the cards show "
            "lines and movement only. The feed is unofficial and sometimes down; try again later or drop a splits.csv in the repo.</div>")
    html = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover"><title>Games</title>
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<header><h1>Games this week</h1><p>Lines, how they moved, and where the public's money is. Updated {datetime.now():%a %b %d, %I:%M %p} UTC.</p></header>
<nav><a href="index.html">Board</a><a href="parlay.html">Parlay</a><a class="on" href="games.html">Games</a></nav>
<main>{note}{"".join(cards) if cards else '<div class="empty">No games loaded yet. The Saturday run fills this in.</div>'}
<h2 style="color:var(--paper);font:600 24px var(--display);margin:18px 0 10px">Charts</h2>{charts_html()}</main>
<footer>How to read a trap: when 70%+ of tickets are on one side but the line moves the other way, or the money share is much bigger than the ticket share, the sportsbook is happy to take the public's side. That is a reason to pause, not an automatic fade.</footer>
</body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open("docs/games.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote docs/games.html with {len(cards)} games, splits for {len(splits)}")


if __name__ == "__main__":
    build()
