"""AI layer: a 3-sentence slate brief and a one-line "why" for the top plays, written by Claude.
Runs only when ANTHROPIC_API_KEY is set; otherwise it exits quietly and the pages render without it.
Cost: one request per run, a few cents. Output: docs/ai.json  {brief: str, why: {play_id: str}}
"""
import glob
import json
import os
import sys

import pandas as pd
import requests

import config as C

KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MODEL = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
TOP_N = 25


def play_id(r):
    return f"{r.player}|{r.market}|{r.side}|{float(r.line)}"


def main():
    if not KEY:
        print("brief: no ANTHROPIC_API_KEY, skipping (pages render without the AI layer)")
        return
    files = glob.glob("output/props_wk*.csv")
    if not files:
        return
    df = pd.read_csv(max(files, key=os.path.getmtime))
    gfiles = glob.glob("output/games_wk*.csv")
    if gfiles:
        df = pd.concat([df, pd.read_csv(max(gfiles, key=os.path.getmtime))], ignore_index=True)
    df["flags"] = df["flags"].fillna("")
    good = df[(df.ev >= C.MIN_EV) & (df.raw_edge.abs() <= C.MAX_RAW_EDGE) & ~df.flags.str.contains("no-recent-game|odd-line|OUT")]
    good = good.sort_values("ev", ascending=False).drop_duplicates(["player", "market", "side"]).head(TOP_N)
    rows = []
    for r in good.itertuples():
        recent = json.loads(r.recent) if isinstance(r.recent, str) else []
        rows.append(dict(id=play_id(r), player=r.player, pos=r.position, team=r.team, opp=r.opp,
                         pick=f"{r.side} {r.line:g} {r.market.replace('player_', '').replace('game_', '').replace('_', ' ')}",
                         odds=round(float(r.price), 2), book=r.book, projection=round(float(r.mean), 1),
                         model_pct=round(100 * r.p_model), market_pct=round(100 * r.p_market), edge_pct=round(100 * r.ev, 1),
                         recent=[(g["w"], g["opp"], g["v"]) for g in recent][-6:], flags=r.flags.strip()))
    by_market = good.market.value_counts().to_dict()
    prompt = (
        "You write the betting notes for a personal NFL prop board. Be concrete and brief. Use only the numbers given; "
        "do not invent injuries, news or stats. If the data for a play is thin, say so.\n\n"
        f"Week {int(df.week.iloc[0]) if 'week' in df else ''} plays with an edge, best first (projection = our model, "
        f"recent = last games as (week, opponent, stat)):\n{json.dumps(rows)}\n\nCounts by market: {json.dumps(by_market)}\n\n"
        "Return ONLY JSON of the form {\"brief\": str, \"why\": {id: str}}. "
        "brief: 2 to 3 sentences on where the value sits this week and the single strongest play, plain language, no hype. "
        "why: for each play id, one sentence (max 25 words) on what drives the edge and the main risk, e.g. "
        "'Targets up to 7 a game since Week 3; risk is a blowout cutting snaps.'"
    )
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json=dict(model=MODEL, max_tokens=3000, messages=[dict(role="user", content=prompt)]), timeout=120)
    if r.status_code != 200:
        print(f"brief: API error {r.status_code}: {r.text[:200]}")
        return
    text = "".join(b.get("text", "") for b in r.json().get("content", []))
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        out = json.loads(text)
    except json.JSONDecodeError:
        print("brief: could not parse the reply; skipping")
        return
    out = dict(brief=str(out.get("brief", ""))[:600], why={k: str(v)[:220] for k, v in (out.get("why") or {}).items()})
    os.makedirs("docs", exist_ok=True)
    json.dump(out, open("docs/ai.json", "w"))
    print(f"brief: wrote docs/ai.json with {len(out['why'])} explanations")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # never break the run over the AI layer
        print(f"brief: skipped ({e})")
        sys.exit(0)
