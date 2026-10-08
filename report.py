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
    show = df[(df.ev >= C.MIN_EV) & ~df.report_status.isin(["Out", "Doubtful"])
              & (df.raw_edge.abs() <= C.MAX_RAW_EDGE)]
    show = show.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side"]).copy()
    show["flags"] = show["flags"].fillna("").str.strip()
    show["injury"] = show.injury.fillna("")
    rows = []
    for r in show.sort_values("ev", ascending=False).itertuples():
        line = "" if r.market == "player_anytime_td" else f"{r.line:g} "
        side = "" if r.market == "player_anytime_td" else r.side
        rows.append(dict(
            player=r.player, team=r.team, opp=r.opp, pos=r.position,
            pick=f"{side} {line}{MARKET_LABEL.get(r.market, r.market)}".strip(),
            market=MARKET_LABEL.get(r.market, r.market), odds=to_american(r.price), book=r.book.replace("_", " "),
            proj=round(float(r.mean), 1), model=round(100 * r.p_model), market_p=round(100 * r.p_market),
            ev=round(100 * r.ev, 1), stake=round(100 * r.stake_pct, 2), flags=r.flags, injury=r.injury,
            kick=str(r.commence),
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
  <p>__COUNT__ plays at +__MINEV__% or better. Updated __UPDATED__.</p>
</header>
<div class="chips" id="chips" role="group" aria-label="Filter by market"></div>
<main>
  <div id="results"></div>
  <div id="list"></div>
</main>
<footer>Win % shown as model / market. Stake is a share of your bankroll (quarter Kelly, 2% max). Red flags mean check the news before you bet.</footer>
<script>
const PLAYS = __PLAYS__;
const RESULTS = __RESULTS__;
let filter = "All", cleanOnly = false;
const when = s => { const d = new Date(s); return isNaN(d) ? "" : d.toLocaleString([], {weekday:"short", hour:"numeric", minute:"2-digit"}); };
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function chips(){
  const mk = ["All", ...new Set(PLAYS.map(p => p.market))];
  const box = document.getElementById("chips");
  box.innerHTML = mk.map(m => `<button class="chip" data-m="${esc(m)}" aria-pressed="${m===filter}">${esc(m)}</button>`).join("")
    + `<button class="chip" data-clean="1" aria-pressed="${cleanOnly}">No flags</button>`;
  box.querySelectorAll(".chip").forEach(b => b.onclick = () => {
    if (b.dataset.clean) cleanOnly = !cleanOnly; else filter = b.dataset.m;
    chips(); render();
  });
}
function render(){
  const rows = PLAYS.filter(p => (filter==="All" || p.market===filter) && (!cleanOnly || !p.flags));
  const list = document.getElementById("list");
  if (!rows.length){
    list.innerHTML = `<div class="empty"><b>Nothing to bet here.</b>No edge means no bet. Check back after more props post, or loosen the filter.</div>`;
    return;
  }
  list.innerHTML = rows.map(p => `
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
      <div>Edge<b class="ev">+${p.ev}%</b></div>
    </div>
    ${p.flags ? `<div class="flag ${/BIG-GAP|Q-tag/.test(p.flags) ? "" : "soft"}">${esc(p.flags.replace("BIG-GAP:check-news","Model and market disagree: check news").replace("Q-tag","Questionable").replace("small-sample","Few games of data").replace("one-sided-mkt","Only one side priced"))} &nbsp; Stake ${p.stake}%</div>`
             : `<div class="flag soft">Stake ${p.stake}% of bankroll</div>`}
  </article>`).join("");
}
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
            .replace("__MINEV__", f"{100 * C.MIN_EV:g}").replace("__UPDATED__", updated.strftime("%a %b %d, %I:%M %p"))
            .replace("__PLAYS__", json.dumps(plays)).replace("__RESULTS__", json.dumps(results_json())))
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote docs/index.html with {len(plays)} plays")


if __name__ == "__main__":
    main()
