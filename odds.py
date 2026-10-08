"""Pull player prop odds from The Odds API, remove the vig, and find the best price per side."""
import json
import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

import config as C

BASE = "https://api.the-odds-api.com/v4/sports/americanfootball_nfl"
OVER_NAMES, UNDER_NAMES = {"over", "yes"}, {"under", "no"}


def fetch_props(markets=None, days_ahead=7, use_cache=None):
    """Returns the raw event-odds JSON list. use_cache: path to a saved JSON (no API credits used)."""
    if use_cache:
        with open(use_cache) as f:
            return json.load(f)
    if not C.ODDS_API_KEY:
        raise SystemExit("Set ODDS_API_KEY first (see README).")
    markets = markets or list(C.MARKETS)
    params = {"apiKey": C.ODDS_API_KEY.strip()}
    r = requests.get(f"{BASE}/events", params=params, timeout=30)
    if r.status_code != 200 or not isinstance(r.json(), list):
        raise SystemExit(f"Odds API rejected the request ({r.status_code}): {r.text[:300]}")
    events = r.json()
    cutoff = datetime.now(timezone.utc) + timedelta(days=days_ahead)
    events = [e for e in events
              if datetime.fromisoformat(e["commence_time"].replace("Z", "+00:00")) <= cutoff]

    q = dict(params, oddsFormat="decimal")
    q.update({"bookmakers": C.BOOKMAKERS} if C.BOOKMAKERS else {"regions": C.REGIONS})
    markets = available_markets(events, q, markets)
    q["markets"] = ",".join(markets)
    data = []
    for e in events:
        r = requests.get(f"{BASE}/events/{e['id']}/odds", params=q, timeout=30)
        if r.status_code != 200:
            print(f"  skip {e['away_team']} @ {e['home_team']}: {r.status_code} {r.text[:120]}")
            continue
        data.append(r.json())
        left = r.headers.get("x-requests-remaining")
    print(f"Pulled {len(data)} games. API credits remaining: {left if data else 'n/a'}")

    os.makedirs(C.CACHE_DIR, exist_ok=True)
    path = os.path.join(C.CACHE_DIR, f"odds_{datetime.now():%Y%m%d_%H%M}.json")
    with open(path, "w") as f:
        json.dump(data, f)
    print(f"Saved to {path} (re-run free with --cache {path})")
    return data


def available_markets(events, q, wanted):
    """Ask the API which prop markets exist for one game; drop any we asked for that it doesn't know.
    One unknown market key would otherwise make every request fail."""
    if not events:
        return wanted
    try:
        r = requests.get(f"{BASE}/events/{events[0]['id']}/markets", params=q, timeout=30)
        offered = {m["key"] for bk in r.json().get("bookmakers", []) for m in bk.get("markets", [])}
    except Exception:
        return wanted
    if not offered:
        return wanted
    missing = [m for m in wanted if m not in offered]
    if missing:
        print(f"  not offered by the books right now, skipping: {', '.join(missing)}")
    return [m for m in wanted if m in offered] or wanted


def flatten(data):
    rows = []
    for ev in data:
        for bk in ev.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk.get("outcomes", []):
                    side = o.get("name", "").lower()
                    side = "over" if side in OVER_NAMES else "under" if side in UNDER_NAMES else None
                    if side is None or not o.get("description"):
                        continue
                    rows.append(dict(event_id=ev["id"], home=ev["home_team"], away=ev["away_team"],
                                     commence=ev["commence_time"], book=bk["key"], market=mk["key"],
                                     player=o["description"], side=side,
                                     line=float(o.get("point", 0.5) if o.get("point") is not None else 0.5),
                                     price=float(o["price"])))
    return pd.DataFrame(rows)


def market_table(data):
    """One row per (game, market, player, line): no-vig consensus prob + best price for each side."""
    df = flatten(data)
    if df.empty:
        return df
    key = ["event_id", "home", "away", "commence", "market", "player", "line"]
    wide = df.pivot_table(index=key + ["book"], columns="side", values="price", aggfunc="max").reset_index()
    for s in ("over", "under"):
        if s not in wide:
            wide[s] = np.nan

    two = wide.over.notna() & wide.under.notna()
    io, iu = 1 / wide.over, 1 / wide.under
    wide["fair_over"] = np.where(two, io / (io + iu), io / (1 + C.ONE_SIDED_HOLD))
    wide["two_sided"] = two

    g = wide.groupby(key)
    out = pd.DataFrame({
        "fair_over": g.fair_over.median(),          # consensus across books
        "n_books": g.book.nunique(),
        "two_sided": g.two_sided.any(),
    })
    for s in ("over", "under"):
        idx = wide[wide[s].notna()].groupby(key)[s].idxmax()
        best = wide.loc[idx, key + [s, "book"]].set_index(key)
        out[f"best_{s}"], out[f"book_{s}"] = best[s], best["book"]
    return out.reset_index()


def to_american(dec):
    if pd.isna(dec):
        return ""
    return f"+{round((dec - 1) * 100)}" if dec >= 2 else f"{round(-100 / (dec - 1))}"
