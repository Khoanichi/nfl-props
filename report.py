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


def plays_json(df):
    """Every priced bet (one row per subject, market and side) so the page can filter it any way.
    Big model-vs-market gaps are kept but marked, since they usually mean the market knows something."""
    show = df[~df.report_status.fillna("").isin(["Out", "Doubtful"])]
    show = show.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side"]).copy()
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
            kick=str(r.commence), gap=bool(abs(r.raw_edge) > C.MAX_RAW_EDGE), line_num=float(r.line),
            recent=json.loads(r.recent) if isinstance(r.recent, str) else [],
            model_spread=(float(r.model_spread) if game and pd.notna(r.model_spread) else None),
        ))
    return rows


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
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{
  --felt:#1b3f32; --felt-2:#16342a; --paper:#f6f1e4; --paper-edge:#e7dfc9; --ink:#1c1b17; --ink-soft:#6e6a5e;
  --chip:#c8372d; --gold:#b9922f; --ok:#2e7d4f; --mint:#8fb0a0;
  --display:"Oswald","Arial Narrow",Impact,sans-serif; --body:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
*,*::before,*::after{box-sizing:inherit}
html{scroll-padding-top:calc(env(safe-area-inset-top,0px) + 120px)}
body{margin:0;background:var(--felt);color:var(--ink);font-family:var(--body);font-size:17px;line-height:1.35}
header{color:var(--paper);padding:18px 16px 6px;max-width:640px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-end;gap:12px}
header h1{font-family:var(--display);font-weight:600;font-size:32px;margin:0;line-height:1}
header p{margin:4px 0 0;color:#c9d6cd;font-size:14px}
.pages{display:flex;gap:6px}
.pages a{color:var(--paper);text-decoration:none;border:1.5px solid var(--mint);border-radius:999px;padding:7px 12px;font-weight:600;font-size:14px;white-space:nowrap}
.pages a.on{background:var(--paper);color:var(--ink);border-color:var(--paper)}
/* toolbar */
.bar{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;background:var(--felt);padding:10px 16px 8px;box-shadow:0 8px 14px -10px rgba(0,0,0,.5)}
.bar-in{max-width:640px;margin:0 auto;display:grid;grid-template-columns:1fr auto;gap:8px}
.search{display:flex;align-items:center;gap:8px;border:1.5px solid var(--mint);border-radius:10px;padding:0 10px;min-height:44px;color:var(--paper)}
.search svg{flex:0 0 auto;opacity:.8}
.search input{flex:1;min-width:0;border:0;background:transparent;color:var(--paper);font:16px var(--body);outline:none}
.search input::placeholder{color:#9db7aa}
.search button{display:none;border:0;background:transparent;color:var(--paper);font-size:22px;line-height:1;padding:0 2px}
.search.has button{display:block}
.fbtn{border:1.5px solid var(--mint);background:transparent;color:var(--paper);border-radius:10px;min-height:44px;padding:0 14px;font:600 15px var(--body);display:flex;align-items:center;gap:8px}
.fbtn .n{background:var(--gold);color:var(--ink);border-radius:999px;min-width:22px;height:22px;display:none;align-items:center;justify-content:center;font-size:13px}
.fbtn.has .n{display:flex}
.sortrow{grid-column:1 / -1;display:flex;gap:8px}
.seg{flex:1;display:flex;border:1.5px solid var(--mint);border-radius:10px;overflow:hidden}
.dir{border:1.5px solid var(--mint);background:transparent;color:var(--paper);border-radius:10px;padding:0 12px;font:600 13px var(--body);min-height:38px;white-space:nowrap}
.seg button{flex:1;border:0;background:transparent;color:var(--paper);min-height:38px;font:600 14px var(--body)}
.seg button[aria-pressed=true]{background:var(--paper);color:var(--ink)}
.active{max-width:640px;margin:0 auto;padding:8px 16px 0;display:flex;gap:6px;flex-wrap:wrap}
.active span{background:var(--felt-2);color:var(--paper);border:1px solid var(--mint);border-radius:999px;padding:4px 10px;font-size:13px;display:flex;gap:6px;align-items:center}
.active span b{font-weight:600;cursor:pointer;opacity:.8}
main{max-width:640px;margin:0 auto;padding:12px 12px 60px}
/* cards */
.card{background:var(--paper);border-radius:6px;margin:0 0 14px;position:relative;box-shadow:0 2px 0 var(--paper-edge)}
.top{padding:14px 16px 12px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.who{min-width:0}
.name{font-family:var(--display);font-weight:600;font-size:22px;line-height:1.1;margin:0}
.meta{color:var(--ink-soft);font-size:14px;margin-top:3px}
.tag{display:inline-block;font:600 11px var(--body);letter-spacing:.2px;color:var(--paper);background:#5b7f9b;border-radius:3px;padding:2px 6px;margin-right:6px;vertical-align:1px}
.pick{font-family:var(--display);font-weight:500;font-size:20px;margin-top:8px}
.odds{font-family:var(--display);font-weight:600;font-size:30px;color:var(--chip);line-height:1;text-align:right;white-space:nowrap}
.odds small{display:block;font:600 13px var(--body);color:var(--ink-soft);margin-top:4px}
.tear{height:0;border-top:2px dashed #cfc6ad;margin:0 10px;position:relative}
.tear::before,.tear::after{content:"";position:absolute;top:-9px;width:18px;height:18px;border-radius:50%;background:var(--felt)}
.tear::before{left:-19px}.tear::after{right:-19px}
.nums{display:grid;grid-template-columns:repeat(4,1fr);padding:12px 16px 12px;gap:6px}
.nums div{font-size:13px;color:var(--ink-soft)}
.nums b{display:block;font:600 19px var(--display);color:var(--ink)}
.nums b.ev{color:var(--ok)}
.log{display:flex;gap:6px;padding:0 16px 12px;overflow-x:auto;scrollbar-width:none;align-items:stretch}
.log::-webkit-scrollbar{display:none}
.log .lbl{flex:0 0 auto;align-self:center;font-size:12px;color:var(--ink-soft);width:52px;line-height:1.2}
.log .g{flex:0 0 auto;min-width:54px;border-radius:5px;padding:5px 6px 4px;text-align:center;background:#ebe4d2;border:1px solid #ddd3bb}
.log .g small{display:block;font-size:10.5px;color:var(--ink-soft);white-space:nowrap}
.log .g b{font:600 17px var(--display);color:var(--ink)}
.log .g i{display:block;font-style:normal;font-size:10px;color:var(--ink-soft)}
.log .g.hit{background:#dcebdd;border-color:#b9d4bc}
.log .g.miss{background:#f1dcd8;border-color:#e3bdb6}
.log .g.old{opacity:.5;border-style:dashed}
.flag{margin:0 16px 12px;font-size:14px;color:var(--chip);font-weight:600}
.flag.soft{color:var(--ink-soft);font-weight:400}
.empty{background:var(--paper);border-radius:6px;padding:22px 18px;font-size:17px}
.empty b{display:block;font:600 24px var(--display);margin-bottom:6px}
.results{background:var(--paper);border-radius:6px;padding:14px 16px;margin-bottom:16px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.results div{font-size:13px;color:var(--ink-soft)}
.results b{display:block;font:600 22px var(--display);color:var(--ink)}
footer{color:#a7bbb0;font-size:14px;text-align:center;padding:0 20px 30px;max-width:640px;margin:0 auto}
/* filter sheet */
.scrim{position:fixed;inset:0;background:rgba(0,0,0,.45);opacity:0;pointer-events:none;transition:opacity .2s;z-index:20}
.sheet{position:fixed;left:0;right:0;bottom:0;max-height:88vh;background:var(--paper);color:var(--ink);border-radius:16px 16px 0 0;transform:translateY(102%);transition:transform .25s;z-index:21;display:flex;flex-direction:column;padding-bottom:env(safe-area-inset-bottom,0px)}
body.open .scrim{opacity:1;pointer-events:auto}
body.open .sheet{transform:none}
@media (min-width:700px){.sheet{left:50%;right:auto;width:560px;transform:translate(-50%,102%)}body.open .sheet{transform:translate(-50%,0)}}
.sh{display:flex;justify-content:space-between;align-items:center;padding:14px 18px 8px}
.sh h2{font:600 24px var(--display);margin:0}
.sh button{border:0;background:transparent;font:600 15px var(--body);color:var(--chip);padding:6px}
.grab{width:40px;height:4px;border-radius:2px;background:#cfc6ad;margin:8px auto 0}
.sb{overflow:auto;padding:0 18px 10px;flex:1}
.sec{padding:12px 0;border-top:1px solid #e7dfc9}
.sec h3{font:600 15px var(--body);margin:0 0 8px;color:var(--ink-soft)}
.sec h3 span{float:right;font-family:var(--display);font-size:17px;color:var(--ink)}
.chips{display:flex;flex-wrap:wrap;gap:8px}
.chip{border:1.5px solid #cfc6ad;background:transparent;border-radius:999px;padding:7px 12px;font:600 14px var(--body);color:var(--ink);min-height:36px}
.chip[aria-pressed=true]{background:var(--ink);color:var(--paper);border-color:var(--ink)}
.seg2{display:flex;border:1.5px solid #cfc6ad;border-radius:10px;overflow:hidden}
.seg2 button{flex:1;border:0;background:transparent;color:var(--ink);min-height:40px;font:600 14px var(--body)}
.seg2 button[aria-pressed=true]{background:var(--ink);color:var(--paper)}
input[type=range]{width:100%;accent-color:var(--ok);height:34px}
.ticks{display:flex;justify-content:space-between;font-size:12px;color:var(--ink-soft);margin-top:-6px}
.sw{display:flex;justify-content:space-between;align-items:center}
.sw label{font-size:15px}
.sw input{width:44px;height:26px;appearance:none;background:#cfc6ad;border-radius:13px;position:relative;outline:none}
.sw input::after{content:"";position:absolute;top:3px;left:3px;width:20px;height:20px;border-radius:50%;background:#fff;transition:left .15s}
.sw input:checked{background:var(--ok)}.sw input:checked::after{left:21px}
.sf{display:flex;gap:10px;padding:10px 18px 14px;border-top:1px solid #e7dfc9;background:var(--paper)}
.sf button{flex:1;min-height:46px;border-radius:10px;font:600 16px var(--body)}
.sf .reset{border:1.5px solid #cfc6ad;background:transparent;color:var(--ink)}
.sf .apply{border:0;background:var(--ok);color:#fff}
:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
</style>
</head>
<body>
<header>
  <div><h1>Week __WEEK__ board</h1><p id="count">Updated __UPDATED__.</p></div>
  <nav class="pages"><a class="on" href="index.html">Board</a><a href="games.html">Games</a></nav>
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
  </div>
</div></div>
<div class="active" id="active"></div>
<main>
  <div id="results"></div>
  <div id="list"></div>
</main>
<footer>Win % shown as model / market. Stake is a share of your bankroll (quarter Kelly, 2% max). Game lines use a results-based power rating; totals are judged on price only.</footer>

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
const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const when = s => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}); };
const amer = o => { const n = parseInt(o, 10); return isNaN(n) ? 0 : n; };
const DEF = {q:"", type:"all", mkts:[], sides:[], model:0, ev:3, price:300, books:[], games:[], gap:false, hit:false, sort:"ev", dir:"desc"};
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
  const box = (g, ok) => {
    let v = p.kind === "game" && p.mkey !== "game_total" ? (g.v > 0 ? "+" : "") + g.v : (g.v % 1 ? g.v.toFixed(1) : g.v);
    let sub = p.mkey === "game_spread" && g.line != null ? `<i>line ${g.line > 0 ? "+" : ""}${g.line}</i>` : p.mkey === "game_total" && g.line != null ? `<i>o/u ${g.line}</i>` : "";
    const old = g.cur === false ? " old" : "";
    return `<div class="g ${ok === null ? "" : ok ? "hit" : "miss"}${old}"><small>${esc(g.w)} ${esc(g.opp)}</small><b>${v}</b>${sub}</div>`;
  };
  const what = p.mkey === "game_spread" ? "ATS" : p.mkey === "game_moneyline" ? "wins" : "hit";
  const label = curOf ? `This season<br>${curN} of ${curOf} ${what}` : `Last season<br>${h.n} of ${h.of} ${what}`;
  return `<div class="log"><div class="lbl">${label}</div>${p.recent.map((g, i) => box(g, h.each[i])).join("")}</div>`;
}
function card(p){
  const game = p.kind === "game";
  const meta = game ? `<span class="tag">${esc(p.market)}</span>${when(p.kick)}`
                    : `${esc(p.pos)} ${esc(p.team)} vs ${esc(p.opp)} &nbsp;${when(p.kick)}${p.injury ? " &nbsp;" + esc(p.injury) : ""}`;
  const projLabel = game ? (p.mkey === "game_total" ? "Model" : "Model line") : "Projection";
  const projVal = game ? (p.mkey === "game_total" ? "price only" : (p.model_spread === null ? "" : fmtSpread(p))) : p.proj;
  return `
  <article class="card">
    <div class="top">
      <div class="who">
        <h2 class="name">${esc(p.player)}</h2>
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
    ${p.flags ? `<div class="flag ${/BIG-GAP|Q-tag/.test(p.flags) ? "" : "soft"}">${esc(p.flags.replace("BIG-GAP:check-news","Model and market disagree: check news").replace("Q-tag","Questionable").replace("small-sample","Few games of data").replace("one-sided-mkt","Only one side priced"))} &nbsp; Stake ${p.stake}%</div>`
             : `<div class="flag soft">Stake ${p.stake}% of bankroll</div>`}
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
  $("list").innerHTML = rows.length
    ? rows.slice(0, 150).map(card).join("") + (rows.length > 150 ? `<div class="empty">Showing the top 150. Tighten the filters to see the rest.</div>` : "")
    : `<div class="empty"><b>Nothing matches.</b>Loosen a filter or clear the search.</div>`;
}
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
document.addEventListener("keydown", e => { if (e.key === "Escape") open(false); });
if (RESULTS){
  $("results").innerHTML = `<section class="results" aria-label="Season results">
    <div>Record<b>${RESULTS.wins}-${RESULTS.losses}</b></div>
    <div>Units<b>${RESULTS.units>0?"+":""}${RESULTS.units}</b></div>
    <div>ROI<b>${RESULTS.roi}%</b></div>
    <div>Hit vs predicted<b>${RESULTS.hit}% / ${RESULTS.predicted}%</b></div>
  </section>`;
}
syncSheet(); render();
</script>
</body>
</html>
"""


def main():
    df, week, updated = load_latest(sys.argv[1] if len(sys.argv) > 1 else None)
    plays = plays_json(df)
    html = (HTML.replace("__WEEK__", str(week))
            .replace("__UPDATED__", updated.strftime("%a %b %d, %I:%M %p"))
            .replace("__PLAYS__", json.dumps(plays)).replace("__RESULTS__", json.dumps(results_json())))
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote docs/index.html with {len(plays)} priced bets")


if __name__ == "__main__":
    main()
