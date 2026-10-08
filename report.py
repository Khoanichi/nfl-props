"""Turn the latest output CSV into a phone-friendly page at docs/index.html.

Usage:  python report.py            # uses the newest file in output/
        python report.py output/props_wk5_20261008_0900.csv
Open docs/index.html on your phone (GitHub Pages publishes it automatically if you use the workflow).
"""
import glob
import json
import os
import sys
from datetime import datetime

import pandas as pd

import config as C
from odds import to_american

MARKET_LABEL = {
    "player_pass_yds": "Pass yds", "player_pass_attempts": "Pass att", "player_pass_completions": "Completions",
    "player_pass_tds": "Pass TD", "player_rush_yds": "Rush yds", "player_rush_attempts": "Carries",
    "player_reception_yds": "Rec yds", "player_receptions": "Receptions", "player_anytime_td": "Anytime TD",
    "player_pass_interceptions": "Interceptions", "player_rush_reception_yds": "Rush+Rec yds",
    "game_spread": "Spread", "game_total": "Total", "game_moneyline": "Moneyline",
}


def latest(pattern):
    files = glob.glob(pattern)
    return max(files, key=os.path.getmtime) if files else None


def load_latest(path=None):
    path = path or latest("output/props_wk*.csv")
    if not path:
        raise SystemExit("No output yet. Run find_value.py first.")
    df = pd.read_csv(path)
    week = int(os.path.basename(path).split("_wk")[1].split("_")[0])
    gpath = latest("output/games_wk*.csv")
    if gpath:
        g = pd.read_csv(gpath)
        g["kind"] = "game"
        df["kind"] = "player"
        df = pd.concat([df, g], ignore_index=True)
    else:
        df["kind"] = "player"
    return df, week, datetime.fromtimestamp(os.path.getmtime(path))


def plays_json(df, all_lines=False):
    """Every priced bet (one row per subject, market and side) so the page can filter it any way.
    Big model-vs-market gaps are kept but marked, since they usually mean the market knows something.
    all_lines=True keeps alternate lines too (the parlay page wants the easy -300 ladders)."""
    show = df[~df.report_status.fillna("").isin(["Out", "Doubtful"])]
    keys = ["player", "market", "side"] + (["line"] if all_lines else [])
    show = show.sort_values("ev", ascending=False).drop_duplicates(keys).copy()
    show["flags"] = show["flags"].fillna("").str.strip()
    show["injury"] = show.injury.fillna("")
    rows = []
    for r in show.itertuples():
        game = r.kind == "game"
        if game:
            pick = r.pick
            proj = (f"{'by ' + str(abs(r.model_spread)) if r.model_spread else 'pick'}" if r.market != "game_total" else "")
        else:
            line = "" if r.market == "player_anytime_td" else f"{r.line:g} "
            side = "" if r.market == "player_anytime_td" else r.side
            pick = f"{side} {line}{MARKET_LABEL.get(r.market, r.market)}".strip()
            proj = round(float(r.mean), 1)
        rows.append(dict(
            kind=r.kind, player=r.player, team=r.team, opp=r.opp, pos=r.position, pick=pick,
            market=MARKET_LABEL.get(r.market, r.market), mkey=r.market, side=r.side,
            odds=to_american(r.price), book=str(r.book).replace("_", " "),
            proj=proj, model=round(100 * r.p_model), market_p=round(100 * r.p_market),
            ev=round(100 * r.ev, 1), stake=round(100 * r.stake_pct, 2), flags=r.flags, injury=r.injury,
            kick=str(r.commence), gap=bool(abs(r.raw_edge) > C.MAX_RAW_EDGE or ("no-recent-game" in r.flags) or ("odd-line" in r.flags)), line_num=float(r.line),
            recent=json.loads(r.recent) if isinstance(r.recent, str) else [],
            streak=json.loads(r.streak) if isinstance(getattr(r, "streak", None), str) else [],
            model_spread=(float(r.model_spread) if game and pd.notna(r.model_spread) else None),
        ))
    return rows


def ai_json():
    if not os.path.exists("docs/ai.json"):
        return None
    return json.load(open("docs/ai.json"))


def checks_json():
    if not os.path.exists("docs/checks.json"):
        return None
    return json.load(open("docs/checks.json"))


def results_json():
    if not os.path.exists("graded.csv"):
        return None
    g = pd.read_csv("graded.csv")
    dec = g[g.result != "P"]
    return dict(n=int(len(g)), wins=int((dec.result == "W").sum()), losses=int((dec.result == "L").sum()),
                units=round(float(g.units.sum()), 2), roi=round(100 * g.units.sum() / max(len(g), 1), 1),
                hit=round(100 * (dec.result == "W").mean(), 1) if len(dec) else 0,
                predicted=round(100 * dec.p.mean(), 1) if len(dec) else 0)


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Week __WEEK__ board</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{
  --felt:#101823; --felt-2:#182230; --paper:#FFFFFF; --paper-edge:#E3E9F0; --ink:#0B1420; --ink-soft:#5B6B7E;
  --chip:#E5533D; --gold:#3DDC97; --ok:#17B37A; --mint:#2A3647; --panel:#F3F6F9; --violet:#6B5CE7;
  --display:"Sora","Segoe UI",system-ui,sans-serif; --body:"Manrope","Segoe UI",system-ui,sans-serif;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
*,*::before,*::after{box-sizing:inherit}
html{scroll-padding-top:calc(env(safe-area-inset-top,0px) + 120px)}
body{margin:0;background:var(--felt);color:var(--ink);font-family:var(--body);font-size:17px;line-height:1.35}
header{color:#F2F5F8;padding:18px 16px 6px;max-width:640px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
header h1{font-family:var(--display);font-weight:600;font-size:32px;margin:0;line-height:1}
header p{margin:4px 0 0;color:#93A1B3;font-size:14px}
.checks{font-size:12.5px}.checks b{color:var(--gold)}.checks b.bad{color:#f3a08f}.checks details{display:inline}.checks summary{display:inline;cursor:pointer;text-decoration:underline dotted}.checks ul{margin:4px 0 0;padding-left:16px;color:#93A1B3}
.pages{display:flex;gap:6px}
.pages a{color:#F2F5F8;text-decoration:none;border:1px solid var(--mint);background:var(--felt-2);border-radius:10px;padding:8px 12px;font-weight:700;font-size:13px;white-space:nowrap}
.pages a.on{background:#F2F5F8;color:var(--ink);border-color:#F2F5F8}
.pages a.refresh{font-size:18px;line-height:1;padding:6px 11px;border-color:var(--gold);color:var(--gold)}
/* layout: wider, grid, compact */
header,.bar-in,.active,main{max-width:1180px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;align-items:start}
.cat{display:flex;align-items:baseline;justify-content:space-between;color:#F2F5F8;margin:18px 2px 10px;font:600 20px var(--display)}
.cat:first-child{margin-top:4px}
.cat small{font:600 13px var(--body);color:#93A1B3}
.cat .more{border:1px solid var(--mint);background:var(--felt-2);color:#F2F5F8;border-radius:999px;padding:4px 10px;font:700 12px var(--body)}
.card .name{font-size:19px}.card .pick{font-size:17px;margin-top:5px}.card .meta{font-size:13px}
.card .odds{font-size:22px}.card .odds small{font-size:12px}
.card .nums{padding:8px 12px 6px;gap:5px}.card .nums div{padding:6px 8px;font-size:11.5px}.card .nums b{font-size:16px}
.card .top{padding:12px 12px 8px}.card .tear{margin:0 12px}
.card .log2{padding:2px 12px 8px;gap:8px}.card .log2 svg{height:44px}.card .log2 .lbl{width:52px;font-size:11px}
.card .flag{margin:0 12px 10px;font-size:13px}.card .why{margin:0 12px 8px}
/* toolbar */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--felt);padding:10px 16px 8px;box-shadow:0 8px 14px -10px rgba(0,0,0,.5)}
.bar-in{max-width:640px;margin:0 auto;display:grid;grid-template-columns:1fr auto;gap:8px}
.search{display:flex;align-items:center;gap:8px;border:1px solid var(--mint);background:var(--felt-2);border-radius:12px;padding:0 12px;min-height:46px;color:#F2F5F8}
.search svg{flex:0 0 auto;opacity:.8}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--paper);font:16px var(--body);outline:none}
.search input::placeholder{color:#7F8EA3}
.search button{display:none;border:0;background:transparent;color:var(--paper);font-size:22px;line-height:1;padding:0 2px}
.search.has button{display:block}
.fbtn{border:1px solid var(--mint);background:var(--felt-2);color:#F2F5F8;border-radius:12px;min-height:46px;padding:0 14px;font:600 15px var(--body);display:flex;align-items:center;gap:8px}
.fbtn .n{background:var(--gold);color:#0B1420;border-radius:999px;min-width:22px;height:22px;display:none;align-items:center;justify-content:center;font-size:13px}
.fbtn.has .n{display:flex}
.sortrow{grid-column:1 / -1;display:flex;gap:8px}
.seg{flex:1;display:flex;border:1px solid var(--mint);background:var(--felt-2);border-radius:12px;padding:3px;gap:2px}
.dir{border:1px solid var(--mint);background:var(--felt-2);color:#F2F5F8;border-radius:12px;padding:0 12px;font:600 13px var(--body);min-height:38px;white-space:nowrap}
.seg button{flex:1;border:0;background:transparent;color:#93A1B3;min-height:34px;border-radius:9px;font:700 13px var(--body)}
.seg button[aria-pressed=true]{background:#F2F5F8;color:var(--ink)}
.active{max-width:640px;margin:0 auto;padding:8px 16px 0;display:flex;gap:6px;flex-wrap:wrap}
.active span{background:var(--felt-2);color:#C9D3DF;border:1px solid var(--mint);border-radius:999px;padding:4px 10px;font-size:13px;display:flex;gap:6px;align-items:center}
.active span b{font-weight:600;cursor:pointer;opacity:.8}
main{max-width:640px;margin:0 auto;padding:12px 12px 110px}
/* cards */
.card{background:var(--paper);border-radius:14px;margin:0 0 12px;position:relative;box-shadow:0 1px 0 rgba(0,0,0,.25)}
.top{padding:14px 16px 12px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.who{min-width:0}
.name{font-family:var(--display);font-weight:600;font-size:22px;line-height:1.1;margin:0}
.meta{color:var(--ink-soft);font-size:14px;margin-top:3px}
.tag{display:inline-block;font:600 11px var(--body);letter-spacing:.2px;color:var(--paper);background:#5B7FD6;border-radius:3px;padding:2px 6px;margin-right:6px;vertical-align:1px}
.pick{font-family:var(--display);font-weight:500;font-size:20px;margin-top:8px}
.odds{font-family:var(--display);font-weight:700;font-size:26px;color:var(--ink);line-height:1;text-align:right;white-space:nowrap}
.odds small{display:block;font:600 13px var(--body);color:var(--ink-soft);margin-top:4px}
.tear{height:0;border-top:1px solid var(--paper-edge);margin:0 16px;position:relative}
.tear::before,.tear::after{display:none}
.tear::before{left:-19px}.tear::after{right:-19px}
.nums{display:grid;grid-template-columns:repeat(4,1fr);padding:10px 16px 8px;gap:6px}
.nums div{font-size:13px;color:var(--ink-soft)}
.nums b{display:block;font:600 19px var(--display);color:var(--ink)}
.nums b.ev{color:#0E6B45}
.nums div{background:var(--panel);border-radius:8px;padding:8px 10px}
.log2{display:flex;gap:10px;padding:2px 16px 12px;align-items:stretch}
.log2 .lbl{flex:0 0 auto;align-self:center;font-size:12px;color:var(--ink-soft);width:58px;line-height:1.2}
.log2 .chart{flex:1;min-width:0;display:flex;flex-direction:column;gap:3px}
.log2 svg{display:block;width:100%;height:56px;background:#F3F6F9;border-radius:5px}
.nums2{display:flex}
.nums2 .n{flex:1;text-align:center;line-height:1.1}
.nums2 .n b{display:block;font:600 13px var(--display);color:var(--ink)}
.nums2 .n small{display:block;font-size:9.5px;color:var(--ink-soft);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nums2 .n.old{opacity:.5}
.log2 .cap{font-size:10.5px;color:var(--ink-soft)}
.flag{margin:0 16px 12px;font-size:14px;color:var(--chip);font-weight:600}
.flag.soft{color:var(--ink-soft);font-weight:400}
.empty{background:var(--paper);border-radius:6px;padding:22px 18px;font-size:17px}
.empty b{display:block;font:600 24px var(--display);margin-bottom:6px}
.results{background:var(--paper);border-radius:6px;padding:14px 16px;margin-bottom:16px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.results div{font-size:13px;color:var(--ink-soft)}
.results b{display:block;font:600 22px var(--display);color:var(--ink)}
footer{color:#93A1B3;font-size:13px;text-align:center;padding:0 20px 110px;max-width:640px;margin:0 auto}
/* parlay tray */
.tray{position:fixed;left:12px;right:12px;bottom:calc(env(safe-area-inset-bottom,0px) + 12px);z-index:15;display:flex;gap:8px}
.tray[hidden]{display:none}
.tray-main{flex:1;display:flex;justify-content:space-between;align-items:center;border:1px solid var(--mint);background:#0B1420;color:#F2F5F8;border-radius:12px;min-height:52px;padding:0 16px;font:600 15px var(--body);box-shadow:0 8px 24px rgba(0,0,0,.35)}
.tray-main b{font:600 17px var(--display)}
.trayev{color:#7fe0a9}
.tray-x{border:1px solid var(--mint);background:#0B1420;color:#F2F5F8;border-radius:12px;width:52px;font-size:24px}
.addp{border:1.5px solid #D5DDE6;background:transparent;color:var(--ink);border-radius:8px;padding:6px 10px;font:600 13px var(--body);min-height:34px}
.addp[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:#fff}
.note{font-size:13px;color:var(--ink-soft);margin:6px 0 10px}
.autob{width:100%;min-height:46px;border:0;border-radius:12px;background:var(--ink);color:#F2F5F8;font:600 16px var(--body)}
.leg{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px dashed #E3E9F0}
.leg .t{min-width:0}
.leg .t b{display:block;font:600 16px var(--display)}
.leg .t small{font-size:12.5px;color:var(--ink-soft)}
.leg .o{font:600 17px var(--display);white-space:nowrap}
.leg .rm{border:0;background:transparent;font-size:22px;color:var(--ink-soft);padding:0 4px}
.ps{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}
.ps div{background:#F3F6F9;border-radius:8px;padding:10px 12px;font-size:12px;color:var(--ink-soft)}
.ps b{display:block;font:600 22px var(--display);color:var(--ink)}
.warn{margin-top:10px;padding:8px 10px;border-radius:6px;background:#FCE6E1;color:#9E2F1F;font-size:13px}
.good{margin-top:10px;padding:8px 10px;border-radius:6px;background:#DDF6EA;color:#0E6B45;font-size:13px}
.tabs{position:fixed;left:0;right:0;bottom:0;z-index:12;background:#0B1420;border-top:1px solid var(--mint);display:grid;grid-template-columns:repeat(3,1fr);padding:8px 8px calc(env(safe-area-inset-bottom,0px) + 10px)}
.tabs a{display:flex;flex-direction:column;align-items:center;gap:3px;color:#93A1B3;text-decoration:none;font:700 11px var(--body)}
.tabs a.on{color:var(--gold)}
.tray{bottom:calc(env(safe-area-inset-bottom,0px) + 78px)}
.brief{background:linear-gradient(135deg,#1A2A3A,#182230);border:1px solid #2E4056;border-radius:14px;padding:12px 14px;color:#DCE3EB;margin-bottom:12px}
.brief h3{display:flex;align-items:center;gap:8px;margin:0 0 6px;font:600 14px var(--display);color:#F2F5F8}
.brief p{margin:0;font-size:13.5px;line-height:1.45}
.why{margin:0 16px 10px;padding:8px 10px;background:var(--panel);border-radius:8px;display:flex;gap:8px;align-items:flex-start;font-size:12.5px;line-height:1.35;color:#2B3A4D}
.why svg{flex:0 0 auto;margin-top:2px}
.name{cursor:pointer}
.pbar{height:10px;border-radius:5px;background:#E3E9F0;position:relative;margin:6px 0 2px}
.pbar i{position:absolute;left:0;top:0;bottom:0;border-radius:5px;background:var(--ok)}
.pbar b{position:absolute;top:-3px;width:2px;height:16px;background:var(--ink)}
.dbig{font:700 22px var(--display);margin:4px 0 8px}
.drow{display:flex;gap:8px;margin-top:12px}
.drow button{flex:1;min-height:46px;border-radius:12px;font:700 15px var(--body);border:1px solid #D5DDE6;background:transparent;color:var(--ink)}
.drow button.pri{background:var(--ink);color:#F2F5F8;border-color:var(--ink)}
/* filter sheet */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}
.sheet{position:fixed;left:0;right:0;bottom:0;max-height:88vh;background:var(--paper);color:var(--ink);border-radius:16px 16px 0 0;transform:translateY(102%);transition:transform .25s;z-index:21;display:flex;flex-direction:column;padding-bottom:env(safe-area-inset-bottom,0px)}
body.open #scrim,body.popen #scrim2,body.dopen #scrim3{opacity:1;pointer-events:auto}
body.open #sheet,body.popen #psheet,body.dopen #dsheet{transform:none}
@media (min-width:700px){.sheet{left:50%;right:auto;width:560px;transform:translate(-50%,102%)}body.open #sheet,body.popen #psheet,body.dopen #dsheet{transform:translate(-50%,0)}}
.sh{display:flex;justify-content:space-between;align-items:center;padding:14px 18px 8px}
.sh h2{font:600 24px var(--display);margin:0}
.sh button{border:0;background:transparent;font:600 15px var(--body);color:var(--chip);padding:6px}
.grab{width:40px;height:4px;border-radius:2px;background:#D5DDE6;margin:8px auto 0}
.sb{overflow:auto;padding:0 18px 10px;flex:1}
.sec{padding:12px 0;border-top:1px solid #E3E9F0}
.sec h3{font:600 15px var(--body);margin:0 0 8px;color:var(--ink-soft)}
.sec h3 span{float:right;font-family:var(--display);font-size:17px;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1.5px solid #D5DDE6;background:transparent;border-radius:999px;padding:7px 12px;font:600 14px var(--body);color:var(--ink);min-height:36px}
.chip[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.seg2{display:flex;border:1.5px solid #D5DDE6;border-radius:10px;overflow:hidden}
.seg2 button{flex:1;border:0;background:transparent;color:var(--ink);min-height:40px;font:600 14px var(--body)}
.seg2 button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
input[type=range]{width:100%;accent-color:var(--ok);height:34px}
.ticks{display:flex;justify-content:space-between;font-size:12px;color:var(--ink-soft);margin-top:-6px}
.sw{display:flex;justify-content:space-between;align-items:center}
.sw label{font-size:15px}
.sw input{width:44px;height:26px;appearance:none;background:#D5DDE6;border-radius:13px;position:relative;outline:none}
.sw input::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:left .15s}
.sw input:checked{background:var(--ok)}.sw input:checked::after{left:21px}
.sf{display:flex;gap:10px;padding:10px 18px 14px;border-top:1px solid #E3E9F0;background:var(--paper)}
.sf button{flex:1;min-height:46px;border-radius:10px;font:600 16px var(--body)}
.sf .reset{border:1.5px solid #D5DDE6;background:transparent;color:var(--ink)}
.sf .apply{border:0;background:var(--ok);color:#06281A}
:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
</style>
</head>
<body>
<header>
  <div><h1>Week __WEEK__ board</h1><p id="count">Updated __UPDATED__.</p><p id="checks" class="checks"></p></div>
  <nav class="pages"><a class="on" href="index.html">Board</a><a href="parlay.html">Parlay</a><a href="games.html">Games</a><a class="refresh" id="refresh" href="https://github.com/Khoanichi/nfl-props/actions/workflows/props.yml" target="_blank" rel="noopener" title="Re-run the model">&#8635;</a></nav>
</header>
<div class="bar"><div class="bar-in">
  <label class="search" id="searchwrap">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/></svg>
    <input id="q" type="search" placeholder="Player, team or game" aria-label="Search" autocomplete="off">
    <button id="clearq" aria-label="Clear search">&times;</button>
  </label>
  <button class="fbtn" id="openf" aria-haspopup="dialog">Filters <span class="n" id="fcount">0</span></button>
  <div class="sortrow">
    <div class="seg" id="sort" role="group" aria-label="Sort by">
      <button data-s="ev" aria-pressed="true">Edge</button><button data-s="model">Model %</button><button data-s="odds">Odds</button><button data-s="kick">Kickoff</button>
    </div>
    <button class="dir" id="dir" aria-label="Sort direction">High to low</button>
    <div class="seg" id="group" role="group" aria-label="Layout" style="flex:0 0 auto"><button data-s="cat" aria-pressed="true">By category</button><button data-s="flat">Flat</button></div>
  </div>
</div></div>
<div class="active" id="active"></div>
<main>
  <div id="results"></div>
  <div id="list"></div>
</main>
<footer>Win % shown as model / market. Stake is a share of your bankroll (quarter Kelly, 2% max). Game lines use a results-based power rating; totals are judged on price only.</footer>

<div class="tray" id="tray" hidden>
  <button class="tray-main" id="opentray"><span><b id="trayN">0 legs</b> <span id="trayOdds"></span></span><span id="trayEv" class="trayev"></span></button>
  <button class="tray-x" id="cleartray" aria-label="Clear parlay">&times;</button>
</div>
<div class="scrim" id="scrim2"></div>
<section class="sheet" id="psheet" role="dialog" aria-modal="true" aria-label="Parlay builder">
  <div class="grab"></div>
  <div class="sh"><h2>Parlay builder</h2><button id="closep">Done</button></div>
  <div class="sb">
    <div class="sec" style="border-top:0">
      <h3>Auto-build to a target</h3>
      <div class="seg2" id="ptarget"><button data-v="2">+100</button><button data-v="3" aria-pressed="true">+200</button><button data-v="4">+300</button><button data-v="6">+500</button></div>
      <p class="note">Picks the highest-probability legs with a positive edge, one per game, one per player, until the payout reaches the target. Legs that hit 5+ of their last 6 come first.</p>
      <button class="autob" id="autobuild">Auto-build parlay</button>
    </div>
    <div class="sec"><h3>Legs</h3><div id="legs"></div></div>
    <div class="sec" id="psummary"></div>
  </div>
  <div class="sf"><button class="reset" id="clearp">Clear</button><button class="apply" id="copyp">Copy slip</button></div>
</section>
<nav class="tabs" aria-label="Sections">
  <a href="index.html" class="on"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V9M10 19V5M16 19v-8M22 19H2"/></svg>Board</a>
  <a href="parlay.html" class=""><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h10"/></svg>Parlay</a>
  <a href="games.html" class=""><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="12" rx="9" ry="6"/><path d="M6 12h12M12 6v12"/></svg>Games</a>
</nav>
<div class="scrim" id="scrim3"></div>
<section class="sheet" id="dsheet" role="dialog" aria-modal="true" aria-label="Play detail">
  <div class="grab"></div>
  <div class="sh"><h2 id="dtitle">Play</h2><button id="closed">Done</button></div>
  <div class="sb" id="dbody"></div>
</section>
<div class="scrim" id="scrim"></div>
<section class="sheet" id="sheet" role="dialog" aria-modal="true" aria-label="Filters">
  <div class="grab"></div>
  <div class="sh"><h2>Filters</h2><button id="closef">Done</button></div>
  <div class="sb">
    <div class="sec" style="border-top:0"><h3>Type</h3><div class="seg2" id="ftype"><button data-v="all" aria-pressed="true">Everything</button><button data-v="player">Player props</button><button data-v="game">Game lines</button></div></div>
    <div class="sec"><h3>Market</h3><div class="chips" id="fmkt"></div></div>
    <div class="sec"><h3>Side (pick one or both)</h3><div class="chips" id="fside"></div></div>
    <div class="sec"><h3>Model win % at least <span id="vmodel">any</span></h3><input type="range" id="fmodel" min="0" max="80" step="5" value="0"><div class="ticks"><span>any</span><span>40</span><span>60</span><span>80%</span></div></div>
    <div class="sec"><h3>Edge at least <span id="vev">+3%</span></h3><input type="range" id="fev" min="-10" max="15" step="1" value="3"><div class="ticks"><span>-10%</span><span>0</span><span>+5</span><span>+15%</span></div></div>
    <div class="sec"><h3>Odds no longer than <span id="vprice">+300</span></h3><input type="range" id="fprice" min="-300" max="300" step="25" value="300"><div class="ticks"><span>-300</span><span>-100</span><span>+100</span><span>+300</span></div></div>
    <div class="sec"><h3>Sportsbook</h3><div class="chips" id="fbook"></div></div>
    <div class="sec"><h3>Game</h3><div class="chips" id="fgame"></div></div>
    <div class="sec"><div class="sw"><label for="fgap">Show "check news" plays (model and market far apart)</label><input type="checkbox" id="fgap"></div></div>
    <div class="sec"><div class="sw"><label for="fhit">Only plays that hit in 4+ of the last 6</label><input type="checkbox" id="fhit"></div></div>
  </div>
  <div class="sf"><button class="reset" id="resetf">Reset</button><button class="apply" id="applyf">Show plays</button></div>
</section>

<script>
const PLAYS = __PLAYS__;
const RESULTS = __RESULTS__;
const CHECKS = __CHECKS__;
const AI = __AI__ || {brief: "", why: {}};
if (CHECKS){ const n = CHECKS.checks.filter(c => c.ok).length, all = CHECKS.checks.length; const E = s => String(s).replace(/[&<>"]/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[ch]));
  document.getElementById("checks").innerHTML = `Data checks: <b class="${n === all ? "" : "bad"}">${n} of ${all} passed</b> <details><summary>details</summary><ul>${CHECKS.checks.map(c => `<li>${c.ok ? "OK" : "Check"}: ${E(c.name)}${c.detail ? " (" + E(c.detail) + ")" : ""}</li>`).join("")}</ul></details>`; }
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when = s => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}); };
const amer = o => { const n = parseInt(o, 10); return isNaN(n) ? 0 : n; };
const DEF = {q:"", type:"all", mkts:[], sides:[], model:0, ev:3, price:300, books:[], games:[], gap:false, hit:false, sort:"ev", dir:"desc", group:"cat"};
const CATS = [["Passing", /^player_pass/], ["Rushing", /^player_rush_(yds|attempts)$/], ["Receiving", /^player_(reception|receptions|rush_reception)/], ["Touchdowns", /anytime_td/], ["Game lines", /^game_/]];
const catOf = p => (CATS.find(([, re]) => re.test(p.mkey)) || ["Other"])[0];
let F = Object.assign({}, DEF);
try { Object.assign(F, JSON.parse(localStorage.getItem("boardFilters") || "{}")); } catch(e) {}
const save = () => { try { localStorage.setItem("boardFilters", JSON.stringify(F)); } catch(e) {} };

const uniq = k => [...new Set(PLAYS.map(p => p[k]))];
const MARKETS = uniq("market"), BOOKS = uniq("book").sort(), GAMES = [...new Set(PLAYS.map(gameOf))].sort();
function gameOf(p){ return p.kind === "game" ? p.player : (p.team < p.opp ? p.team + " / " + p.opp : p.opp + " / " + p.team); }

function hits(p){
  if (!p.recent || !p.recent.length) return null;
  const hit = g => p.mkey === "game_spread" ? (g.line == null ? null : g.v + g.line > 0)
              : p.mkey === "game_moneyline" ? g.v > 0
              : p.mkey === "game_total" ? (g.line == null ? null : (p.side === "Over" ? g.v > g.line : g.v < g.line))
              : (p.side === "Over" ? g.v > p.line_num : g.v < p.line_num);
  const hs = p.recent.map(hit).filter(x => x !== null);
  return {n: hs.filter(Boolean).length, of: hs.length, each: p.recent.map(hit)};
}
function matches(p){
  const q = F.q.trim().toLowerCase();
  const h = hits(p);
  return (F.type === "all" || p.kind === F.type)
    && (!F.mkts.length || F.mkts.includes(p.market))
    && (!F.sides.length || F.sides.includes(p.side))
    && p.model >= F.model && p.ev >= F.ev && amer(p.odds) <= F.price
    && (!F.books.length || F.books.includes(p.book))
    && (!F.games.length || F.games.includes(gameOf(p)))
    && (F.gap || !p.gap)
    && (!F.hit || (h && h.of >= 4 && h.n >= 4))
    && (!q || (p.player + " " + p.team + " " + p.opp + " " + p.pick + " " + p.market).toLowerCase().includes(q));
}
function activeCount(){
  return (F.type !== "all") + (F.mkts.length > 0) + (F.sides.length > 0) + (F.model > 0) + (F.ev !== 3) + (F.price !== 300)
       + (F.books.length > 0) + (F.games.length > 0) + F.gap + F.hit;
}
function chipRow(el, items, sel, onToggle){
  el.innerHTML = items.map(m => `<button class="chip" aria-pressed="${sel.includes(m)}">${esc(m)}</button>`).join("");
  [...el.children].forEach((b, i) => b.onclick = () => { onToggle(items[i]); syncSheet(); render(); });
}
function toggle(arr, v){ const i = arr.indexOf(v); i < 0 ? arr.push(v) : arr.splice(i, 1); }
function seg(el, val, onPick){
  [...el.children].forEach(b => { b.setAttribute("aria-pressed", b.dataset.v === val || b.dataset.s === val); b.onclick = () => { onPick(b.dataset.v || b.dataset.s); syncSheet(); render(); }; });
}
function syncSheet(){
  seg($("ftype"), F.type, v => F.type = v);
  chipRow($("fside"), ["Over", "Under"], F.sides, v => toggle(F.sides, v));
  $("dir").textContent = F.dir === "desc" ? "High to low" : "Low to high";
  seg($("sort"), F.sort, v => F.sort = v);
  seg($("group"), F.group, v => F.group = v);
  chipRow($("fmkt"), MARKETS, F.mkts, v => toggle(F.mkts, v));
  chipRow($("fbook"), BOOKS, F.books, v => toggle(F.books, v));
  chipRow($("fgame"), GAMES, F.games, v => toggle(F.games, v));
  $("fmodel").value = F.model; $("vmodel").textContent = F.model ? F.model + "%" : "any";
  $("fev").value = F.ev; $("vev").textContent = (F.ev > 0 ? "+" : "") + F.ev + "%";
  $("fprice").value = F.price; $("vprice").textContent = (F.price > 0 ? "+" : "") + F.price;
  $("fgap").checked = F.gap; $("fhit").checked = F.hit; $("q").value = F.q;
  $("searchwrap").classList.toggle("has", !!F.q);
  const n = activeCount(); $("fcount").textContent = n; $("openf").classList.toggle("has", n > 0);
  const chips = [];
  if (F.type !== "all") chips.push(["type", F.type === "player" ? "Player props" : "Game lines"]);
  F.mkts.forEach(m => chips.push(["mkt:" + m, m]));
  F.sides.forEach(s => chips.push(["side:" + s, s + " only"]));
  if (F.model) chips.push(["model", "Model " + F.model + "%+"]);
  if (F.ev !== 3) chips.push(["ev", "Edge " + (F.ev > 0 ? "+" : "") + F.ev + "%+"]);
  if (F.price !== 300) chips.push(["price", "Odds to " + (F.price > 0 ? "+" : "") + F.price]);
  F.books.forEach(b => chips.push(["book:" + b, b]));
  F.games.forEach(g => chips.push(["game:" + g, g]));
  if (F.gap) chips.push(["gap", "Incl. check-news"]);
  if (F.hit) chips.push(["hit", "4+ of last 6"]);
  $("active").innerHTML = chips.map(([k, l]) => `<span>${esc(l)}<b data-k="${esc(k)}" aria-label="Remove">&times;</b></span>`).join("");
  [...$("active").querySelectorAll("b")].forEach(b => b.onclick = () => { clearOne(b.dataset.k); syncSheet(); render(); });
}
function clearOne(k){
  if (k === "type") F.type = "all"; else if (k.startsWith("side:")) toggle(F.sides, k.slice(5)); else if (k === "model") F.model = 0;
  else if (k === "ev") F.ev = 3; else if (k === "price") F.price = 300; else if (k === "gap") F.gap = false; else if (k === "hit") F.hit = false;
  else if (k.startsWith("mkt:")) toggle(F.mkts, k.slice(4)); else if (k.startsWith("book:")) toggle(F.books, k.slice(5)); else if (k.startsWith("game:")) toggle(F.games, k.slice(5));
}
function gamelog(p){
  const h = hits(p); if (!h) return "";
  const cur = p.recent.map((g, i) => [g, h.each[i]]).filter(([g]) => g.cur !== false);
  const curN = cur.filter(([, ok]) => ok).length, curOf = cur.filter(([, ok]) => ok !== null).length;
  const what = p.mkey === "game_spread" ? "ATS" : p.mkey === "game_moneyline" ? "wins" : "hit";
  const label = curOf ? `This season<br>${curN} of ${curOf} ${what}` : `Last season<br>${h.n} of ${h.of} ${what}`;
  // value per game and the number it is measured against
  const spread = p.mkey === "game_spread", ml = p.mkey === "game_moneyline", tot = p.mkey === "game_total";
  const val = g => spread ? g.v + (g.line ?? 0) : g.v;            // spread: cover margin
  const ref = g => spread || ml ? 0 : tot ? (g.line ?? p.line_num) : p.line_num;
  const vals = p.recent.map(val), refs = p.recent.map(ref);
  const signed = spread || ml;
  const top = Math.max(1, ...vals.map(Math.abs), ...refs.map(Math.abs)) * 1.15;
  const H = 56, W = 100 / p.recent.length;
  const y = v => signed ? H / 2 - (v / top) * (H / 2) : H - (v / top) * H;
  const refLine = signed ? `<line x1="0" x2="100" y1="${H / 2}" y2="${H / 2}" stroke="#5B6B7E" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>`
    : `<line x1="0" x2="100" y1="${y(p.line_num).toFixed(1)}" y2="${y(p.line_num).toFixed(1)}" stroke="#5B6B7E" stroke-width="1" stroke-dasharray="2 2" vector-effect="non-scaling-stroke"/>`;
  const bars = p.recent.map((g, i) => {
    const v = vals[i], ok = h.each[i], old = g.cur === false;
    const fill = ok === null ? "#D5DDE6" : ok ? "#17B37A" : "#E5533D";
    const x = i * W + W * 0.18, bw = W * 0.64;
    const y0 = signed ? H / 2 : H, y1 = y(v);
    const by = Math.min(y0, y1), bh = Math.max(1, Math.abs(y0 - y1));
    return `<rect x="${x.toFixed(1)}" y="${by.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="1" fill="${fill}" opacity="${old ? .45 : .9}"/>`;
  }).join("");
  const nums = p.recent.map((g, i) => `<div class="n ${g.cur === false ? "old" : ""}"><b>${spread || ml ? (g.v > 0 ? "+" : "") + g.v : (g.v % 1 ? g.v.toFixed(1) : g.v)}</b><small>${esc(g.w)} ${esc(g.opp)}</small></div>`).join("");
  const lineTxt = tot ? "dashed line = that game's total" : spread ? "bars = margin vs the spread" : ml ? "bars = margin of victory" : `dashed line = ${p.line_num}`;
  return `<div class="log2"><div class="lbl">${label}</div><div class="chart"><svg viewBox="0 0 100 ${H}" preserveAspectRatio="none" aria-label="Last games vs the line">${refLine}${bars}</svg><div class="nums2">${nums}</div><div class="cap">${lineTxt}</div></div></div>`;
}
function card(p){
  const game = p.kind === "game";
  const meta = game ? `<span class="tag">${esc(p.market)}</span>${when(p.kick)}`
                    : `${esc(p.pos)} ${esc(p.team)} vs ${esc(p.opp)} &nbsp;${when(p.kick)}${p.injury ? " &nbsp;" + esc(p.injury) : ""}`;
  const projLabel = game ? (p.mkey === "game_total" ? "Model" : "Model line") : "Projection";
  const projVal = game ? (p.mkey === "game_total" ? "price only" : (p.model_spread === null ? "" : fmtSpread(p))) : p.proj;
  return `
  <article class="card" data-id="${esc(idOf(p))}">
    <div class="top">
      <div class="who">
        <h2 class="name" title="Open details">${esc(p.player)}</h2>
        <div class="meta">${meta}</div>
        <div class="pick">${esc(p.pick)}</div>
      </div>
      <div class="odds">${esc(p.odds)}<small>${esc(p.book)}</small></div>
    </div>
    <div class="tear"></div>
    <div class="nums">
      <div>${projLabel}<b>${projVal}</b></div>
      <div>Model win %<b>${p.model}</b></div>
      <div>Market win %<b>${p.market_p}</b></div>
      <div>Edge<b class="ev">${p.ev > 0 ? "+" : ""}${p.ev}%</b></div>
    </div>
    ${gamelog(p)}
    ${AI.why[idOf(p)] ? `<div class="why"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6B5CE7" stroke-width="2.2"><path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z"/></svg><div><b>Why:</b> ${esc(AI.why[idOf(p)])}</div></div>` : ""}
    <div class="flag ${/BIG-GAP|Q-tag/.test(p.flags) ? "" : "soft"}" style="display:flex;justify-content:space-between;align-items:center;gap:8px"><span>${p.flags ? esc(p.flags.replace("BIG-GAP:check-news","Model and market disagree: check news").replace("Q-tag","Questionable").replace("small-sample","Few games of data").replace("one-sided-mkt","Only one side priced").replace("no-recent-game","No game in 3+ weeks: traded or hurt?").replace("odd-line","Line far from projection: alt line or bad match")) + " &nbsp;" : ""}Stake ${p.stake}%</span><button class="addp" data-id="${esc(idOf(p))}" aria-pressed="${PARLAY.has(idOf(p))}">${PARLAY.has(idOf(p)) ? "In parlay" : "+ Parlay"}</button></div>
  </article>`;
}
function fmtSpread(p){
  // model_spread is the expected HOME margin; show it as "<team> -x" for the home side
  const home = p.player.split(" @ ")[1];
  const m = p.model_spread;
  return m >= 0 ? `${home} -${Math.abs(m)}` : `${p.player.split(" @ ")[0]} -${Math.abs(m)}`;
}
function render(){
  save();
  let rows = PLAYS.filter(matches);
  const key = p => F.sort === "model" ? p.model : F.sort === "kick" ? -new Date(p.kick) : F.sort === "odds" ? amer(p.odds) : p.ev;
  rows.sort((a, b) => F.dir === "desc" ? key(b) - key(a) : key(a) - key(b));
  $("count").textContent = `${rows.length} of ${PLAYS.length} priced bets. Updated __UPDATED__.`;
  $("applyf").textContent = `Show ${rows.length} plays`;
  const brief = AI.brief ? `<section class="brief"><h3><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#3DDC97" stroke-width="2"><path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z"/></svg>Slate brief</h3><p>${esc(AI.brief)}</p></section>` : "";
  if (!rows.length){ $("list").innerHTML = brief + `<div class="empty"><b>Nothing matches.</b>Loosen a filter or clear the search.</div>`; return; }
  if (F.group === "flat"){
    $("list").innerHTML = brief + `<div class="grid">${rows.slice(0, 200).map(card).join("")}</div>` + (rows.length > 200 ? `<div class="empty">Showing the top 200. Tighten the filters to see the rest.</div>` : "");
    return;
  }
  const groups = new Map(); rows.forEach(p => { const c = catOf(p); if (!groups.has(c)) groups.set(c, []); groups.get(c).push(p); });
  const order = CATS.map(c => c[0]).concat(["Other"]).filter(c => groups.has(c));
  $("list").innerHTML = brief + order.map(c => { const g = groups.get(c), lim = EXPANDED.has(c) ? g.length : 8;
    return `<h2 class="cat">${c}<span><small>${g.length} play${g.length === 1 ? "" : "s"}</small>${g.length > 8 ? ` <button class="more" data-cat="${esc(c)}">${EXPANDED.has(c) ? "Show fewer" : "Show all " + g.length}</button>` : ""}</span></h2><div class="grid">${g.slice(0, lim).map(card).join("")}</div>`; }).join("");
  [...$("list").querySelectorAll(".more")].forEach(b => b.onclick = () => { EXPANDED.has(b.dataset.cat) ? EXPANDED.delete(b.dataset.cat) : EXPANDED.add(b.dataset.cat); render(); });
}
const EXPANDED = new Set();
$("q").addEventListener("input", e => { F.q = e.target.value; syncSheet(); render(); });
$("clearq").onclick = () => { F.q = ""; syncSheet(); render(); };
$("fmodel").oninput = e => { F.model = +e.target.value; syncSheet(); render(); };
$("fev").oninput = e => { F.ev = +e.target.value; syncSheet(); render(); };
$("fprice").oninput = e => { F.price = +e.target.value; syncSheet(); render(); };
$("fgap").onchange = e => { F.gap = e.target.checked; syncSheet(); render(); };
$("fhit").onchange = e => { F.hit = e.target.checked; syncSheet(); render(); };
const open = v => document.body.classList.toggle("open", v);
$("openf").onclick = () => open(true); $("closef").onclick = $("applyf").onclick = $("scrim").onclick = () => open(false);
$("resetf").onclick = () => { F = Object.assign({}, DEF, {q: F.q, sort: F.sort, dir: F.dir}); syncSheet(); render(); };
$("dir").onclick = () => { F.dir = F.dir === "desc" ? "asc" : "desc"; syncSheet(); render(); };
document.addEventListener("keydown", e => { if (e.key === "Escape") { open(false); openP(false); openD(false); } });
// ---- parlay builder ----
const idOf = p => p.player + "|" + p.mkey + "|" + p.side + "|" + p.line_num;
let PARLAY = new Set(); try { PARLAY = new Set(JSON.parse(localStorage.getItem("parlayLegs") || "[]")); } catch(e) {}
let PTARGET = 3;
const dec = o => { const n = amer(o); return n >= 100 ? 1 + n / 100 : n <= -100 ? 1 + 100 / -n : 1; };
const toAmer = d => d >= 2 ? "+" + Math.round((d - 1) * 100) : String(Math.round(-100 / (d - 1)));
const blend = p => { const m = p.model / 100, k = p.market_p / 100, w = p.kind === "game" && p.mkey === "game_total" ? 0 : 0.35;
  const L = x => Math.log(Math.min(Math.max(x, 1e-4), 1 - 1e-4) / (1 - Math.min(Math.max(x, 1e-4), 1 - 1e-4))); return 1 / (1 + Math.exp(-(w * L(m) + (1 - w) * L(k)))); };
const legsOf = () => PLAYS.filter(p => PARLAY.has(idOf(p)));
function parlayStats(legs){
  const d = legs.reduce((a, p) => a * dec(p.odds), 1), pb = legs.reduce((a, p) => a * blend(p), 1), pm = legs.reduce((a, p) => a * p.market_p / 100, 1);
  return {d, pb, pm, ev: pb * d - 1, games: new Set(legs.map(gameOf)).size};
}
function savePar(){ try { localStorage.setItem("parlayLegs", JSON.stringify([...PARLAY])); } catch(e) {} }
function renderTray(){
  const legs = legsOf(); const t = $("tray"); t.hidden = legs.length === 0;
  if (legs.length){ const s = parlayStats(legs); $("trayN").textContent = legs.length + (legs.length === 1 ? " leg" : " legs"); $("trayOdds").textContent = toAmer(s.d); $("trayEv").textContent = (s.ev >= 0 ? "+" : "") + (100 * s.ev).toFixed(1) + "% EV"; $("trayEv").style.color = s.ev >= 0 ? "#7fe0a9" : "#f3a08f"; }
  const legsEl = $("legs");
  legsEl.innerHTML = legs.length ? legs.map(p => `<div class="leg"><div class="t"><b>${esc(p.player)}</b><small>${esc(p.pick)} · ${esc(p.book)} · model ${p.model}%</small></div><span class="o">${esc(p.odds)}</span><button class="rm" data-id="${esc(idOf(p))}" aria-label="Remove leg">&times;</button></div>`).join("")
    : `<p class="note">No legs yet. Tap "+ Parlay" on any card, or auto-build below.</p>`;
  [...legsEl.querySelectorAll(".rm")].forEach(b => b.onclick = () => { PARLAY.delete(b.dataset.id); savePar(); renderTray(); render(); });
  const sum = $("psummary");
  if (!legs.length){ sum.innerHTML = ""; return; }
  const s = parlayStats(legs); const same = s.games < legs.length;
  sum.innerHTML = `<h3>If the book pays the legs multiplied</h3><div class="ps">
    <div>Combined odds<b>${toAmer(s.d)}</b></div><div>Payout on $10<b>$${(10 * s.d).toFixed(0)}</b></div>
    <div>Our win chance<b>${(100 * s.pb).toFixed(0)}%</b></div><div>Market's win chance<b>${(100 * s.pm).toFixed(0)}%</b></div></div>
    <div class="${s.ev >= 0 ? "good" : "warn"}">Expected value ${s.ev >= 0 ? "+" : ""}${(100 * s.ev).toFixed(1)}%. ${s.ev >= 0 ? "Every leg carries its own small edge, and they multiply." : "The legs' prices eat the edge once multiplied. Swap a leg for one with a better price."}</div>
    ${same ? `<div class="warn">Two legs are from the same game. Their results move together, so the real win chance is not a simple multiply, and many books reprice same-game parlays. Treat the numbers above as optimistic.</div>` : ""}
    <p class="note">Books often pay a bit less than the straight multiply on parlays. Check the slip's payout against the number above before you confirm.</p>`;
}
function autoBuild(){
  const hitRate = p => { const h = hits(p); return h && h.of >= 4 ? h.n / h.of : 0; };
  const pool = PLAYS.filter(p => !p.gap && p.ev >= 0 && dec(p.odds) < 2 && blend(p) >= 0.6)
    .sort((a, b) => (hitRate(b) >= 5/6) - (hitRate(a) >= 5/6) || blend(b) - blend(a));
  PARLAY = new Set(); const games = new Set(), players = new Set(); let d = 1;
  for (const p of pool){ const g = gameOf(p); if (games.has(g) || players.has(p.player)) continue; PARLAY.add(idOf(p)); games.add(g); players.add(p.player); d *= dec(p.odds); if (d >= PTARGET || PARLAY.size >= 8) break; }
  savePar(); renderTray(); render();
}
$("list").addEventListener("click", e => { const nm = e.target.closest(".name"); if (nm){ openDetail(nm.closest(".card").dataset.id); return; } const b = e.target.closest(".addp"); if (!b) return; const id = b.dataset.id; PARLAY.has(id) ? PARLAY.delete(id) : PARLAY.add(id); savePar(); renderTray(); render(); });
const openP = v => document.body.classList.toggle("popen", v);
const openD = v => document.body.classList.toggle("dopen", v);
function openDetail(id){
  const p = PLAYS.find(x => idOf(x) === id); if (!p) return;
  const pb = blend(p), be = 1 / dec(p.odds);
  $("dtitle").textContent = p.player;
  $("dbody").innerHTML = `
    <div class="sec" style="border-top:0"><div class="meta">${p.kind === "game" ? esc(p.market) : esc(p.pos) + " " + esc(p.team) + " vs " + esc(p.opp)} · ${when(p.kick)}${p.injury ? " · " + esc(p.injury) : ""}</div>
      <div class="dbig">${esc(p.pick)} <span style="float:right">${esc(p.odds)} <small style="font:600 12px var(--body);color:var(--ink-soft)">${esc(p.book)}</small></span></div>
      <div class="nums" style="padding:0;gap:6px"><div>Projection<b>${p.kind === "game" ? (p.mkey === "game_total" ? "price only" : fmtSpread(p)) : p.proj}</b></div><div>Model<b>${p.model}%</b></div><div>Market<b>${p.market_p}%</b></div><div>Edge<b class="ev">${p.ev > 0 ? "+" : ""}${p.ev}%</b></div></div>
      <div class="note" style="margin:10px 0 0">Blended win chance ${(100 * pb).toFixed(0)}% against a breakeven of ${(100 * be).toFixed(0)}% at ${esc(p.odds)}</div>
      <div class="pbar"><i style="width:${(100 * pb).toFixed(0)}%"></i><b style="left:${(100 * be).toFixed(0)}%"></b></div></div>
    <div class="sec">${gamelog(p).replace('class="log2"', 'class="log2" style="padding:0"')}</div>
    ${AI.why[id] ? `<div class="sec"><div class="why" style="margin:0"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6B5CE7" stroke-width="2.2"><path d="M12 3l1.8 4.6L18 9.4l-4.2 1.8L12 16l-1.8-4.8L6 9.4l4.2-1.8z"/></svg><div><b>Why:</b> ${esc(AI.why[id])}</div></div></div>` : ""}
    <div class="sec"><div class="note">${p.flags ? esc(p.flags) : "No flags."} Stake ${p.stake}% of bankroll at quarter Kelly.</div>
      <div class="drow"><button id="dadd">${PARLAY.has(id) ? "Remove from parlay" : "Add to parlay"}</button><button class="pri" id="dcopy">Copy pick</button></div></div>`;
  $("dadd").onclick = () => { PARLAY.has(id) ? PARLAY.delete(id) : PARLAY.add(id); savePar(); renderTray(); render(); $("dadd").textContent = PARLAY.has(id) ? "Remove from parlay" : "Add to parlay"; };
  $("dcopy").onclick = () => { try { navigator.clipboard.writeText(`${p.player} ${p.pick} (${p.odds}, ${p.book})`); $("dcopy").textContent = "Copied"; } catch(e) {} };
  openD(true);
}
$("closed").onclick = $("scrim3").onclick = () => openD(false);
$("opentray").onclick = () => openP(true); $("closep").onclick = $("scrim2").onclick = () => openP(false);
$("cleartray").onclick = $("clearp").onclick = () => { PARLAY = new Set(); savePar(); renderTray(); render(); };
$("autobuild").onclick = autoBuild;
seg($("ptarget"), String(PTARGET), v => { PTARGET = +v; }); [...$("ptarget").children].forEach(b => b.onclick = () => { PTARGET = +b.dataset.v; seg($("ptarget"), String(PTARGET), v => { PTARGET = +v; }); });
$("copyp").onclick = () => { const legs = legsOf(); const s = parlayStats(legs); const txt = legs.map(p => `${p.player} ${p.pick} (${p.odds}, ${p.book})`).join("\n") + `\nCombined ${toAmer(s.d)}`; try { navigator.clipboard.writeText(txt); $("copyp").textContent = "Copied"; setTimeout(() => $("copyp").textContent = "Copy slip", 1200); } catch(e) {} };
renderTray();
if (RESULTS){
  $("results").innerHTML = `<section class="results" aria-label="Season results">
    <div>Record<b>${RESULTS.wins}-${RESULTS.losses}</b></div>
    <div>Units<b>${RESULTS.units>0?"+":""}${RESULTS.units}</b></div>
    <div>ROI<b>${RESULTS.roi}%</b></div>
    <div>Hit vs predicted<b>${RESULTS.hit}% / ${RESULTS.predicted}%</b></div>
  </section>`;
}
syncSheet(); render();
$("refresh").onclick = e => {
  const ageH = Math.round((Date.now() - new Date(document.lastModified)) / 36e5);
  const msg = `Refresh re-runs the model on GitHub (tap the green "Run workflow" button on the page that opens; the board updates 2 to 3 minutes later).\n\nCredits: a run only pulls new odds if the last pull is more than 12 hours old. A fresh pull costs about 95 of your 500 monthly credits, so do this once a day at most. Runs inside the 12-hour window reuse the saved odds and cost nothing.\n\nThis board was built ${ageH} hours ago. Continue?`;
  if (!confirm(msg)) e.preventDefault();
};
</script>
</body>
</html>
"""


PARLAY_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Week __WEEK__ parlay builder</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Manrope:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--felt:#101823;--felt-2:#182230;--paper:#FFFFFF;--paper-edge:#E3E9F0;--ink:#0B1420;--ink-soft:#5B6B7E;--chip:#E5533D;--gold:#3DDC97;--ok:#17B37A;--mint:#2A3647;--panel:#F3F6F9;--violet:#6B5CE7;
--display:"Sora","Segoe UI",system-ui,sans-serif;--body:"Manrope","Segoe UI",system-ui,sans-serif;box-sizing:border-box;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
*,*::before,*::after{box-sizing:inherit}
body{margin:0;background:var(--felt);color:var(--ink);font-family:var(--body);font-size:17px;line-height:1.35}
header{color:#F2F5F8;padding:18px 16px 6px;max-width:640px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
header h1{font:600 32px var(--display);margin:0;line-height:1}
header p{margin:4px 0 0;color:#93A1B3;font-size:14px}
.pages{display:flex;gap:6px}
.pages a{color:#F2F5F8;text-decoration:none;border:1px solid var(--mint);background:var(--felt-2);border-radius:10px;padding:8px 12px;font-weight:700;font-size:13px;white-space:nowrap}
.pages a.on{background:#F2F5F8;color:var(--ink);border-color:#F2F5F8}
.pages a.refresh{font-size:18px;line-height:1;padding:6px 11px;border-color:var(--gold);color:var(--gold)}
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--felt);padding:10px 16px 10px;box-shadow:0 8px 14px -10px rgba(0,0,0,.5)}
.bar-in{max-width:640px;margin:0 auto;display:flex;flex-direction:column;gap:8px}
.row{display:flex;gap:8px;align-items:center}
.row label{flex:1;display:flex;flex-direction:column;gap:3px;font-size:12px;color:#93A1B3}
select{border:1px solid var(--mint);background:var(--felt-2);color:#F2F5F8;border-radius:12px;padding:9px 8px;font:600 15px var(--body);min-height:44px;width:100%}
.seg{display:flex;border:1px solid var(--mint);background:var(--felt-2);border-radius:12px;padding:3px;gap:2px;flex:1}
.seg button{flex:1;border:0;background:transparent;color:#93A1B3;min-height:34px;border-radius:9px;font:700 13px var(--body)}
.seg button[aria-pressed=true]{background:#F2F5F8;color:var(--ink)}
main{max-width:1180px;margin:0 auto;padding:12px 12px 120px}
header,.bar-in{max-width:1180px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:12px;align-items:start}
.intro{background:var(--felt-2);border:1px solid #2E4056;color:#DCE3EB;border-radius:10px;padding:12px 14px;font-size:14px;line-height:1.4;margin-bottom:12px}
.card{background:var(--paper);border-radius:14px;margin:0 0 12px;box-shadow:0 1px 0 rgba(0,0,0,.25);padding:12px 14px;display:flex;flex-direction:column;gap:8px}
.top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.name{font:600 20px var(--display);line-height:1.1}
.meta{color:var(--ink-soft);font-size:13px}
.pick{font:500 17px var(--display);margin-top:2px}
.odds{font:700 24px var(--display);color:var(--ink);line-height:1;text-align:right;white-space:nowrap}
.odds small{display:block;font:600 12px var(--body);color:var(--ink-soft);margin-top:3px}
.dots{display:flex;gap:4px;align-items:center;flex-wrap:wrap}
.dots i{width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font:600 10px var(--body);color:#fff;background:#D5DDE6}
.dots i.h{background:var(--ok)}.dots i.m{background:var(--chip)}.dots i.old{opacity:.55}
.dots span{font-size:13px;color:var(--ink-soft);margin-left:4px}
.stats{display:flex;gap:14px;font-size:13px;color:var(--ink-soft)}
.stats b{font:600 16px var(--display);color:var(--ink);margin-left:4px}
.foot{display:flex;justify-content:space-between;align-items:center}
.addp{border:1.5px solid #D5DDE6;background:transparent;color:var(--ink);border-radius:8px;padding:7px 12px;font:600 14px var(--body);min-height:36px}
.addp[aria-pressed=true]{background:var(--ink);border-color:var(--ink);color:#fff}
.empty{background:var(--paper);border-radius:6px;padding:22px 18px}
.tray{position:fixed;left:12px;right:12px;bottom:calc(env(safe-area-inset-bottom,0px) + 12px);z-index:15;display:flex;gap:8px}
.tray[hidden]{display:none}
.tray-main{flex:1;display:flex;justify-content:space-between;align-items:center;border:1px solid var(--mint);background:#0B1420;color:#F2F5F8;border-radius:12px;min-height:52px;padding:0 16px;font:600 15px var(--body);box-shadow:0 8px 24px rgba(0,0,0,.35)}
.tray-main b{font:600 17px var(--display)}
.tray-x{border:1px solid var(--mint);background:#0B1420;color:#F2F5F8;border-radius:12px;width:52px;font-size:24px}
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}
.sheet{position:fixed;left:0;right:0;bottom:0;max-height:88vh;background:var(--paper);color:var(--ink);border-radius:16px 16px 0 0;transform:translateY(102%);transition:transform .25s;z-index:21;display:flex;flex-direction:column;padding-bottom:env(safe-area-inset-bottom,0px)}
body.popen .scrim{opacity:1;pointer-events:auto}body.popen .sheet{transform:none}
@media (min-width:700px){.sheet{left:50%;right:auto;width:560px;transform:translate(-50%,102%)}body.popen .sheet{transform:translate(-50%,0)}}
.sh{display:flex;justify-content:space-between;align-items:center;padding:14px 18px 8px}.sh h2{font:600 24px var(--display);margin:0}.sh button{border:0;background:transparent;font:600 15px var(--body);color:var(--chip);padding:6px}
.grab{width:40px;height:4px;border-radius:2px;background:#D5DDE6;margin:8px auto 0}
.sb{overflow:auto;padding:0 18px 10px;flex:1}
.sec{padding:12px 0;border-top:1px solid #E3E9F0}.sec h3{font:600 15px var(--body);margin:0 0 8px;color:var(--ink-soft)}
.seg2{display:flex;border:1.5px solid #D5DDE6;border-radius:10px;overflow:hidden}.seg2 button{flex:1;border:0;background:transparent;color:var(--ink);min-height:40px;font:600 14px var(--body)}.seg2 button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
.note{font-size:13px;color:var(--ink-soft);margin:6px 0 10px}
.autob{width:100%;min-height:46px;border:0;border-radius:12px;background:var(--ink);color:#F2F5F8;font:600 16px var(--body)}
.leg{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:10px 0;border-bottom:1px dashed #E3E9F0}.leg .t{min-width:0}.leg .t b{display:block;font:600 16px var(--display)}.leg .t small{font-size:12.5px;color:var(--ink-soft)}.leg .o{font:600 17px var(--display);white-space:nowrap}.leg .rm{border:0;background:transparent;font-size:22px;color:var(--ink-soft);padding:0 4px}
.ps{display:grid;grid-template-columns:repeat(2,1fr);gap:8px}.ps div{background:#F3F6F9;border-radius:8px;padding:10px 12px;font-size:12px;color:var(--ink-soft)}.ps b{display:block;font:600 22px var(--display);color:var(--ink)}
.warn{margin-top:10px;padding:8px 10px;border-radius:6px;background:#FCE6E1;color:#9E2F1F;font-size:13px}.good{margin-top:10px;padding:8px 10px;border-radius:6px;background:#DDF6EA;color:#0E6B45;font-size:13px}
.sf{display:flex;gap:10px;padding:10px 18px 14px;border-top:1px solid #E3E9F0;background:var(--paper)}.sf button{flex:1;min-height:46px;border-radius:10px;font:600 16px var(--body)}.sf .reset{border:1.5px solid #D5DDE6;background:transparent;color:var(--ink)}.sf .apply{border:0;background:var(--ok);color:#06281A}
.tabs{position:fixed;left:0;right:0;bottom:0;z-index:12;background:#0B1420;border-top:1px solid var(--mint);display:grid;grid-template-columns:repeat(3,1fr);padding:8px 8px calc(env(safe-area-inset-bottom,0px) + 10px)}
.tabs a{display:flex;flex-direction:column;align-items:center;gap:3px;color:#93A1B3;text-decoration:none;font:700 11px var(--body)}
.tabs a.on{color:var(--gold)}
.tray{bottom:calc(env(safe-area-inset-bottom,0px) + 78px)}
:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
</style>
</head>
<body>
<header>
  <div><h1>Parlay builder</h1><p id="count">Week __WEEK__ · heavy favorites on a streak</p></div>
  <nav class="pages"><a href="index.html">Board</a><a class="on" href="parlay.html">Parlay</a><a href="games.html">Games</a><a class="refresh" id="refresh" href="https://github.com/Khoanichi/nfl-props/actions/workflows/props.yml" target="_blank" rel="noopener" title="Re-run the model">&#8635;</a></nav>
</header>
<div class="bar"><div class="bar-in">
  <div class="row">
    <label>Hit at least<select id="fmin"><option value="1">every game (100%)</option><option value="0.9">90% of games</option><option value="0.8" selected>80% of games</option><option value="0.7">70% of games</option></select></label>
    <label>Over at least<select id="fn"><option value="4">4 games</option><option value="6" selected>6 games</option><option value="8">8 games</option><option value="10">10 games</option></select></label>
    <label>Favored by at least<select id="fodds"><option value="-101" selected>any favorite</option><option value="-130">-130</option><option value="-150">-150</option><option value="-200">-200</option><option value="-300">-300</option></select></label>
  </div>
  <div class="row">
    <div class="seg" id="fside"><button data-v="all" aria-pressed="true">Any side</button><button data-v="Over">Over</button><button data-v="Under">Under</button></div>
    <div class="seg" id="fseason"><button data-v="all" aria-pressed="true">Incl. last season</button><button data-v="cur">This season only</button></div>
  </div>
  <div class="row"><div class="seg" id="fgap"><button data-v="hide" aria-pressed="true">Hide role-change legs</button><button data-v="show">Show all</button></div></div>
</div></div>
<main>
  <div class="intro">This page ranks legs by how often they've cleared today's line, not by value. Heavy favorites that keep hitting are the raw material; the slip at the bottom shows what they're really worth once multiplied. A 90% leg five times over is a 59% parlay. Legs where the market and model disagree sharply are hidden by default: a backup who was under 35 yards ten times straight stops being a lock the week he becomes the starter.</div>
  <div id="list"></div>
</main>
<div class="tray" id="tray" hidden><button class="tray-main" id="opentray"><span><b id="trayN">0 legs</b> <span id="trayOdds"></span></span><span id="trayP"></span></button><button class="tray-x" id="cleartray" aria-label="Clear parlay">&times;</button></div>
<nav class="tabs" aria-label="Sections">
  <a href="index.html" class=""><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 19V9M10 19V5M16 19v-8M22 19H2"/></svg>Board</a>
  <a href="parlay.html" class="on"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 7h16M4 12h16M4 17h10"/></svg>Parlay</a>
  <a href="games.html" class=""><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="12" rx="9" ry="6"/><path d="M6 12h12M12 6v12"/></svg>Games</a>
</nav>
<div class="scrim" id="scrim"></div>
<section class="sheet" id="psheet" role="dialog" aria-modal="true" aria-label="Parlay slip">
  <div class="grab"></div>
  <div class="sh"><h2>Your slip</h2><button id="closep">Done</button></div>
  <div class="sb">
    <div class="sec" style="border-top:0"><h3>Auto-build to a target</h3>
      <div class="seg2" id="ptarget"><button data-v="2">+100</button><button data-v="3" aria-pressed="true">+200</button><button data-v="4">+300</button><button data-v="6">+500</button></div>
      <p class="note">Fills the slip with the legs that match your filters above, best streak first, one per game, until the payout reaches the target.</p>
      <button class="autob" id="autobuild">Auto-build</button></div>
    <div class="sec"><h3>Legs</h3><div id="legs"></div></div>
    <div class="sec" id="psummary"></div>
  </div>
  <div class="sf"><button class="reset" id="clearp">Clear</button><button class="apply" id="copyp">Copy slip</button></div>
</section>
<script>
const PLAYS = __PLAYS__;
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when = s => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}); };
const amer = o => parseInt(o, 10) || 0, dec = o => { const n = amer(o); return n >= 100 ? 1 + n / 100 : n <= -100 ? 1 + 100 / -n : 1; };
const toAmer = d => d >= 2 ? "+" + Math.round((d - 1) * 100) : String(Math.round(-100 / (d - 1)));
const idOf = p => p.player + "|" + p.mkey + "|" + p.side + "|" + p.line_num;
const gameOf = p => p.kind === "game" ? p.player : (p.team < p.opp ? p.team + " / " + p.opp : p.opp + " / " + p.team);
let S = {min: 0.8, n: 6, odds: -101, side: "all", season: "all", target: 3, gap: "hide"};
try { Object.assign(S, JSON.parse(localStorage.getItem("parlayPage") || "{}")); } catch(e) {}
let PARLAY = new Set(); try { PARLAY = new Set(JSON.parse(localStorage.getItem("parlayLegs") || "[]")); } catch(e) {}
const saveAll = () => { try { localStorage.setItem("parlayPage", JSON.stringify(S)); localStorage.setItem("parlayLegs", JSON.stringify([...PARLAY])); } catch(e) {} };
function log(p){ let g = p.kind === "game" ? p.recent : (p.streak && p.streak.length ? p.streak : p.recent); if (S.season === "cur") g = g.filter(x => x.cur !== false); return g; }
function hitOf(p, g){ return p.mkey === "game_spread" ? (g.line == null ? null : g.v + g.line > 0) : p.mkey === "game_moneyline" ? g.v > 0 : p.mkey === "game_total" ? (g.line == null ? null : (p.side === "Over" ? g.v > g.line : g.v < g.line)) : (p.side === "Over" ? g.v > p.line_num : g.v < p.line_num); }
function streak(p){ const g = log(p); const hs = g.map(x => hitOf(p, x)); const of = hs.filter(x => x !== null).length, n = hs.filter(Boolean).length; return {n, of, rate: of ? n / of : 0, each: hs, g}; }
function pool(){
  return PLAYS.filter(p => !/no-recent-game|odd-line|OUT/.test(p.flags) && (S.gap === "show" || !p.gap) && amer(p.odds) <= S.odds && amer(p.odds) < 0 && (S.side === "all" || p.side === S.side))
    .map(p => ({p, s: streak(p)})).filter(x => x.s.of >= S.n && x.s.rate >= S.min)
    .sort((a, b) => b.s.rate - a.s.rate || b.s.of - a.s.of || b.p.market_p - a.p.market_p);
}
function card(x){ const p = x.p, s = x.s;
  const dots = s.g.map((g, i) => `<i class="${s.each[i] === null ? "" : s.each[i] ? "h" : "m"}${g.cur === false ? " old" : ""}" title="${esc(g.w)} ${esc(g.opp)}: ${g.v}">${g.v % 1 ? g.v.toFixed(1) : g.v}</i>`).join("");
  return `<article class="card"><div class="top"><div><div class="name">${esc(p.player)}</div><div class="meta">${p.kind === "game" ? esc(p.market) : esc(p.pos) + " " + esc(p.team) + " vs " + esc(p.opp)} · ${when(p.kick)}</div><div class="pick">${esc(p.pick)}</div></div><div class="odds">${esc(p.odds)}<small>${esc(p.book)}</small></div></div>
  <div class="dots">${dots}<span>${s.n} of ${s.of}</span></div>
  <div class="stats"><span>Market win %<b>${p.market_p}</b></span><span>Model<b>${p.model}</b></span><span>Streak<b>${Math.round(100 * s.rate)}%</b></span></div>
  <div class="foot"><span class="meta">${p.gap ? "Role changed? Streak is from a different job. Market says " + p.market_p + "%." : ""}</span><button class="addp" data-id="${esc(idOf(p))}" aria-pressed="${PARLAY.has(idOf(p))}">${PARLAY.has(idOf(p)) ? "In slip" : "+ Add"}</button></div></article>`;
}
function render(){ saveAll(); const rows = pool(); $("count").textContent = `Week __WEEK__ · ${rows.length} legs match`; $("list").innerHTML = rows.length ? `<div class="grid">${rows.slice(0, 160).map(card).join("")}</div>` : `<div class="empty"><b>No legs match.</b> Lower the hit rate, the game count, or the favorite threshold.</div>`; renderTray(); }
function stats(legs){ const d = legs.reduce((a, p) => a * dec(p.odds), 1), pm = legs.reduce((a, p) => a * p.market_p / 100, 1); return {d, pm, games: new Set(legs.map(gameOf)).size}; }
function renderTray(){ const legs = PLAYS.filter(p => PARLAY.has(idOf(p))); $("tray").hidden = !legs.length; if (!legs.length){ $("legs").innerHTML = `<p class="note">Empty. Add legs above or auto-build.</p>`; $("psummary").innerHTML = ""; return; }
  const s = stats(legs); $("trayN").textContent = legs.length + (legs.length === 1 ? " leg" : " legs"); $("trayOdds").textContent = toAmer(s.d); $("trayP").textContent = Math.round(100 * s.pm) + "% to hit";
  $("legs").innerHTML = legs.map(p => `<div class="leg"><div class="t"><b>${esc(p.player)}</b><small>${esc(p.pick)} · ${esc(p.book)} · market ${p.market_p}%</small></div><span class="o">${esc(p.odds)}</span><button class="rm" data-id="${esc(idOf(p))}" aria-label="Remove">&times;</button></div>`).join("");
  [...$("legs").querySelectorAll(".rm")].forEach(b => b.onclick = () => { PARLAY.delete(b.dataset.id); render(); });
  const same = s.games < legs.length;
  $("psummary").innerHTML = `<h3>If the book pays the legs multiplied</h3><div class="ps"><div>Combined odds<b>${toAmer(s.d)}</b></div><div>Payout on $10<b>$${(10 * s.d).toFixed(0)}</b></div><div>Chance it all hits<b>${Math.round(100 * s.pm)}%</b></div><div>Legs<b>${legs.length}</b></div></div>
   <div class="warn">That ${Math.round(100 * s.pm)}% uses the market's own numbers for each leg, which is the fairest guess for favorites. Streaks don't raise it: a 6-for-6 run at -200 is still about a 67% leg.</div>
   ${same ? `<div class="warn">Two legs share a game, so the true odds are not a clean multiply and books reprice same-game slips.</div>` : ""}`;
}
function autoBuild(){ PARLAY = new Set(); const games = new Set(), players = new Set(); let d = 1; for (const x of pool()){ const p = x.p, g = gameOf(p); if (games.has(g) || players.has(p.player)) continue; PARLAY.add(idOf(p)); games.add(g); players.add(p.player); d *= dec(p.odds); if (d >= S.target || PARLAY.size >= 10) break; } render(); openP(true); }
const openP = v => document.body.classList.toggle("popen", v);
function seg(el, val, fn){ [...el.children].forEach(b => { b.setAttribute("aria-pressed", b.dataset.v === val); b.onclick = () => { fn(b.dataset.v); seg(el, b.dataset.v, fn); render(); }; }); }
$("fmin").value = S.min; $("fn").value = S.n; $("fodds").value = S.odds;
$("fmin").onchange = e => { S.min = +e.target.value; render(); }; $("fn").onchange = e => { S.n = +e.target.value; render(); }; $("fodds").onchange = e => { S.odds = +e.target.value; render(); };
seg($("fside"), S.side, v => S.side = v); seg($("fseason"), S.season, v => S.season = v); seg($("fgap"), S.gap, v => S.gap = v); seg($("ptarget"), String(S.target), v => S.target = +v);
$("list").addEventListener("click", e => { const b = e.target.closest(".addp"); if (!b) return; PARLAY.has(b.dataset.id) ? PARLAY.delete(b.dataset.id) : PARLAY.add(b.dataset.id); render(); });
$("opentray").onclick = () => openP(true); $("closep").onclick = $("scrim").onclick = () => openP(false);
$("cleartray").onclick = $("clearp").onclick = () => { PARLAY = new Set(); render(); };
$("autobuild").onclick = autoBuild;
$("copyp").onclick = () => { const legs = PLAYS.filter(p => PARLAY.has(idOf(p))); const s = stats(legs); const txt = legs.map(p => `${p.player} ${p.pick} (${p.odds}, ${p.book})`).join("\n") + `\nCombined ${toAmer(s.d)}`; try { navigator.clipboard.writeText(txt); $("copyp").textContent = "Copied"; setTimeout(() => $("copyp").textContent = "Copy slip", 1200); } catch(e) {} };
document.addEventListener("keydown", e => { if (e.key === "Escape") openP(false); });
$("refresh").onclick = e => { if (!confirm("Refresh re-runs the model on GitHub (tap the green Run workflow button on the next page). New odds are only pulled if the last pull is over 12 hours old; a fresh pull costs about 95 of 500 monthly credits, so once a day at most. Continue?")) e.preventDefault(); };
render();
</script>
</body>
</html>
"""


def main():
    df, week, updated = load_latest(sys.argv[1] if len(sys.argv) > 1 else None)
    plays = plays_json(df)
    os.makedirs("docs", exist_ok=True)
    with open("docs/parlay.html", "w", encoding="utf-8") as f:
        f.write(PARLAY_HTML.replace("__WEEK__", str(week)).replace("__PLAYS__", json.dumps(plays_json(df, all_lines=True))))
    html = (HTML.replace("__WEEK__", str(week))
            .replace("__UPDATED__", updated.strftime("%a %b %d, %I:%M %p"))
            .replace("__PLAYS__", json.dumps(plays)).replace("__RESULTS__", json.dumps(results_json()))
            .replace("__CHECKS__", json.dumps(checks_json())).replace("__AI__", json.dumps(ai_json())))
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote docs/index.html with {len(plays)} priced bets")


if __name__ == "__main__":
    main()
