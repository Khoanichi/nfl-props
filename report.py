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
}


def load_latest(path=None):
    files = glob.glob("output/props_wk*.csv")
    if not path and not files:
        raise SystemExit("No output yet. Run find_value.py first.")
    path = path or max(files, key=os.path.getmtime)
    df = pd.read_csv(path)
    week = int(os.path.basename(path).split("_wk")[1].split("_")[0])
    return df, week, datetime.fromtimestamp(os.path.getmtime(path))


def plays_json(df):
    """Every priced prop (one row per player, market and side), so the page can filter it any way.
    Big model-vs-market gaps are kept but marked, since they usually mean the market knows something."""
    show = df[~df.report_status.isin(["Out", "Doubtful"])]
    show = show.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side"]).copy()
    show["flags"] = show["flags"].fillna("").str.strip()
    show["injury"] = show.injury.fillna("")
    rows = []
    for r in show.itertuples():
        line = "" if r.market == "player_anytime_td" else f"{r.line:g} "
        side = "" if r.market == "player_anytime_td" else r.side
        rows.append(dict(
            player=r.player, team=r.team, opp=r.opp, pos=r.position,
            pick=f"{side} {line}{MARKET_LABEL.get(r.market, r.market)}".strip(),
            market=MARKET_LABEL.get(r.market, r.market), odds=to_american(r.price), book=r.book.replace("_", " "),
            proj=round(float(r.mean), 1), model=round(100 * r.p_model), market_p=round(100 * r.p_market),
            ev=round(100 * r.ev, 1), stake=round(100 * r.stake_pct, 2), flags=r.flags, injury=r.injury,
            kick=str(r.commence), gap=bool(abs(r.raw_edge) > C.MAX_RAW_EDGE),
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
<title>Props Week __WEEK__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Oswald:wght@500;600&family=Source+Sans+3:wght@400;600&display=swap" rel="stylesheet">
<style>
:root{
  --felt:#1b3f32; --paper:#f6f1e4; --paper-edge:#e7dfc9; --ink:#1c1b17; --ink-soft:#6e6a5e;
  --chip:#c8372d; --gold:#b9922f; --ok:#2e7d4f;
  --display:"Oswald","Arial Narrow",Impact,sans-serif; --body:"Source Sans 3","Segoe UI",system-ui,sans-serif;
  box-sizing:border-box; padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
}
*,*::before,*::after{box-sizing:inherit}
html{scroll-padding-top:env(safe-area-inset-top,0px)}
body{margin:0;background:var(--felt);color:var(--ink);font-family:var(--body);font-size:17px;line-height:1.35}
header{color:var(--paper);padding:20px 16px 8px;max-width:640px;margin:0 auto}
header h1{font-family:var(--display);font-weight:600;font-size:34px;margin:0;letter-spacing:.3px;line-height:1}
header p{margin:6px 0 0;color:#c9d6cd;font-size:15px}
.chips{display:flex;gap:8px;overflow-x:auto;padding:10px 16px 14px;max-width:640px;margin:0 auto;scrollbar-width:none}
.chips::-webkit-scrollbar{display:none}
.chip{flex:0 0 auto;border:1.5px solid #8fb0a0;color:var(--paper);background:transparent;border-radius:999px;padding:8px 14px;font:600 15px var(--body);min-height:40px}
.chip[aria-pressed=true]{background:var(--paper);color:var(--ink);border-color:var(--paper)}
.chip:focus-visible,.card:focus-visible{outline:3px solid var(--gold);outline-offset:2px}
.controls{max-width:640px;margin:0 auto 14px;padding:0 16px;display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px 12px;color:var(--paper)}
.controls input[type=search]{grid-column:1 / -1;border:1.5px solid #8fb0a0;background:transparent;color:var(--paper);border-radius:8px;padding:10px 12px;font:16px var(--body);min-height:44px}
.controls input[type=search]::placeholder{color:#9db7aa}
.controls label{display:flex;flex-direction:column;gap:4px;font-size:13px;color:#c9d6cd;min-width:0}
.controls select{border:1.5px solid #8fb0a0;background:#16342a;color:var(--paper);border-radius:8px;padding:9px 8px;font:600 16px var(--body);min-height:44px;width:100%}
.controls .check{grid-column:1 / -1;flex-direction:row;align-items:center;gap:10px;font-size:15px;color:var(--paper)}
.controls .check input{width:22px;height:22px;accent-color:var(--gold)}
main{max-width:640px;margin:0 auto;padding:0 12px 40px}
.card{background:var(--paper);border-radius:6px;margin:0 0 14px;position:relative;box-shadow:0 2px 0 var(--paper-edge)}
.top{padding:14px 16px 12px;display:flex;justify-content:space-between;align-items:flex-start;gap:12px}
.who{min-width:0}
.name{font-family:var(--display);font-weight:600;font-size:22px;line-height:1.1;margin:0}
.meta{color:var(--ink-soft);font-size:14px;margin-top:3px}
.pick{font-family:var(--display);font-weight:500;font-size:20px;margin-top:8px}
.odds{font-family:var(--display);font-weight:600;font-size:30px;color:var(--chip);line-height:1;text-align:right;white-space:nowrap}
.odds small{display:block;font:600 13px var(--body);color:var(--ink-soft);margin-top:4px}
/* perforation between the pick and the numbers: the one decorative idea on the page */
.tear{height:0;border-top:2px dashed #cfc6ad;margin:0 10px;position:relative}
.tear::before,.tear::after{content:"";position:absolute;top:-9px;width:18px;height:18px;border-radius:50%;background:var(--felt)}
.tear::before{left:-19px}.tear::after{right:-19px}
.nums{display:grid;grid-template-columns:repeat(4,1fr);padding:12px 16px 12px;gap:6px}
.nums div{font-size:13px;color:var(--ink-soft)}
.nums b{display:block;font:600 19px var(--display);color:var(--ink)}
.nums b.ev{color:var(--ok)}
.flag{margin:0 16px 12px;font-size:14px;color:var(--chip);font-weight:600}
.flag.soft{color:var(--ink-soft);font-weight:400}
.empty{background:var(--paper);border-radius:6px;padding:22px 18px;font-size:17px}
.empty b{display:block;font:600 24px var(--display);margin-bottom:6px}
.results{background:var(--paper);border-radius:6px;padding:14px 16px;margin-bottom:16px;display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap}
.results div{font-size:13px;color:var(--ink-soft)}
.results b{display:block;font:600 22px var(--display);color:var(--ink)}
footer{color:#a7bbb0;font-size:14px;text-align:center;padding:0 20px 30px;max-width:640px;margin:0 auto}
details{margin-top:4px}
@media (prefers-reduced-motion:no-preference){.card{transition:transform .12s}.card:active{transform:scale(.995)}}
</style>
</head>
<body>
<header>
  <h1>Week __WEEK__ props</h1>
  <p id="count">Updated __UPDATED__.</p>
</header>
<div class="chips" id="chips" role="group" aria-label="Filter by market"></div>
<div class="controls">
  <input id="q" type="search" placeholder="Player or team" aria-label="Search player or team" autocomplete="off">
  <label>Model win %<select id="minModel"><option value="0" selected>Any</option><option value="55">55%+</option><option value="60">60%+</option><option value="65">65%+</option><option value="70">70%+</option></select></label>
  <label>Edge<select id="minEv"><option value="-100">Any</option><option value="0">0%+</option><option value="3" selected>3%+</option><option value="5">5%+</option><option value="8">8%+</option></select></label>
  <label>Sort<select id="sort"><option value="ev">Edge</option><option value="model">Model %</option><option value="kick">Kickoff</option></select></label>
  <label class="check"><input id="showGap" type="checkbox">Include "check news" plays</label>
</div>
<main>
  <div id="results"></div>
  <div id="list"></div>
</main>
<footer>Win % shown as model / market. Stake is a share of your bankroll (quarter Kelly, 2% max). Red flags mean check the news before you bet.</footer>
<script>
const PLAYS = __PLAYS__;
const RESULTS = __RESULTS__;
let filter = "All";
const $ = id => document.getElementById(id);
const when = s => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}); };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function chips(){
  const mk = ["All", ...new Set(PLAYS.map(p => p.market))];
  const box = $("chips");
  box.innerHTML = mk.map(m => `<button class="chip" data-m="${esc(m)}" aria-pressed="${m===filter}">${esc(m)}</button>`).join("");
  box.querySelectorAll(".chip").forEach(b => b.onclick = () => { filter = b.dataset.m; chips(); render(); });
}
function render(){
  const q = $("q").value.trim().toLowerCase(), minM = +$("minModel").value, minE = +$("minEv").value,
        sort = $("sort").value, gap = $("showGap").checked;
  let rows = PLAYS.filter(p => (filter==="All" || p.market===filter) && p.model >= minM && p.ev >= minE
    && (gap || !p.gap) && (!q || (p.player + " " + p.team + " " + p.opp).toLowerCase().includes(q)));
  rows.sort((a, b) => sort==="model" ? b.model - a.model : sort==="kick" ? new Date(a.kick) - new Date(b.kick) : b.ev - a.ev);
  $("count").textContent = `${rows.length} of ${PLAYS.length} priced props match. Updated __UPDATED__.`;
  const list = $("list");
  if (!rows.length){
    list.innerHTML = `<div class="empty"><b>Nothing matches.</b>Lower the model % or edge filter, or clear the search.</div>`;
    return;
  }
  list.innerHTML = rows.slice(0, 150).map(p => `
  <article class="card" tabindex="0">
    <div class="top">
      <div class="who">
        <h2 class="name">${esc(p.player)}</h2>
        <div class="meta">${esc(p.pos)} ${esc(p.team)} vs ${esc(p.opp)} &nbsp;${when(p.kick)}${p.injury ? " &nbsp;" + esc(p.injury) : ""}</div>
        <div class="pick">${esc(p.pick)}</div>
      </div>
      <div class="odds">${esc(p.odds)}<small>${esc(p.book)}</small></div>
    </div>
    <div class="tear"></div>
    <div class="nums">
      <div>Projection<b>${p.proj}</b></div>
      <div>Model win %<b>${p.model}</b></div>
      <div>Market win %<b>${p.market_p}</b></div>
      <div>Edge<b class="ev">${p.ev > 0 ? "+" : ""}${p.ev}%</b></div>
    </div>
    ${p.flags ? `<div class="flag ${/BIG-GAP|Q-tag/.test(p.flags) ? "" : "soft"}">${esc(p.flags.replace("BIG-GAP:check-news","Model and market disagree: check news").replace("Q-tag","Questionable").replace("small-sample","Few games of data").replace("one-sided-mkt","Only one side priced"))} &nbsp; Stake ${p.stake}%</div>`
             : `<div class="flag soft">Stake ${p.stake}% of bankroll</div>`}
  </article>`).join("") + (rows.length > 150 ? `<div class="empty">Showing the top 150. Tighten the filters to see the rest.</div>` : "");
}
["q", "minModel", "minEv", "sort", "showGap"].forEach(id => $(id).addEventListener("input", render));
if (RESULTS){
  document.getElementById("results").innerHTML = `<section class="results" aria-label="Season results">
    <div>Record<b>${RESULTS.wins}-${RESULTS.losses}</b></div>
    <div>Units<b>${RESULTS.units>0?"+":""}${RESULTS.units}</b></div>
    <div>ROI<b>${RESULTS.roi}%</b></div>
    <div>Hit vs predicted<b>${RESULTS.hit}% / ${RESULTS.predicted}%</b></div>
  </section>`;
}
chips(); render();
</script>
</body>
</html>
"""


def main():
    df, week, updated = load_latest(sys.argv[1] if len(sys.argv) > 1 else None)
    plays = plays_json(df)
    html = (HTML.replace("__WEEK__", str(week)).replace("__COUNT__", str(len(plays)))
            .replace("__UPDATED__", updated.strftime("%a %b %d, %I:%M %p"))
            .replace("__PLAYS__", json.dumps(plays)).replace("__RESULTS__", json.dumps(results_json())))
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote docs/index.html with {len(plays)} priced props")


if __name__ == "__main__":
    main()
