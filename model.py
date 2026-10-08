"""Projection engine: player baselines -> matchup/game-script adjustments -> full probability distribution."""
import re
import numpy as np
import pandas as pd
import nflreadpy as nfl
from scipy import stats as st

import config as C

POS_MAP = {"FB": "RB", "HB": "RB"}


# ----------------------------------------------------------------------------- data
def load_data(season=C.SEASON, prior=C.PRIOR_SEASONS):
    seasons = list(range(season - prior, season + 1))
    ps = nfl.load_player_stats(seasons).to_pandas()
    ps = ps[(ps.season_type == "REG") & ps.player_id.notna()].copy()
    ps["position"] = ps["position"].replace(POS_MAP)
    ps = add_derived(ps)
    ps["t"] = ps["season"] * 100 + ps["week"]
    sched = nfl.load_schedules(seasons).to_pandas()
    sched = sched[sched.game_type == "REG"]
    try:
        inj = nfl.load_injuries([season]).to_pandas()
    except Exception:
        inj = pd.DataFrame(columns=["gsis_id", "week", "report_status", "practice_status"])
    return ps, sched, inj


def add_derived(ps):
    """Stat columns that props are written on but nflverse doesn't ship directly."""
    ps["any_td"] = ps["rushing_tds"].fillna(0) + ps["receiving_tds"].fillna(0)
    ps["opps"] = ps["carries"].fillna(0) + ps["targets"].fillna(0)
    ps["rush_rec_yards"] = ps["rushing_yards"].fillna(0) + ps["receiving_yards"].fillna(0)
    return ps


def norm_name(s):
    s = str(s).lower().replace(".", "").replace("'", "")
    s = re.sub(r"\b(jr|sr|ii|iii|iv|v)\b", "", s)
    return re.sub(r"[^a-z]", "", s)


# ----------------------------------------------------------------------------- game context
def game_context(sched, season, week):
    """Per team: opponent, implied team total, spread from the team's view (+ = favored)."""
    g = sched[(sched.season == season) & (sched.week == week)]
    rows = []
    for _, r in g.iterrows():
        tot, spr = r.total_line, r.spread_line          # nflverse: spread_line > 0 means HOME favored
        for team, opp, sign in [(r.home_team, r.away_team, 1), (r.away_team, r.home_team, -1)]:
            itt = (tot + sign * spr) / 2 if pd.notna(tot) and pd.notna(spr) else np.nan
            rows.append(dict(team=team, opp=opp, game_id=r.game_id, gameday=r.gameday,
                             itt=itt, team_spread=sign * spr if pd.notna(spr) else 0.0))
    ctx = pd.DataFrame(rows)
    season_lines = sched[(sched.season == season) & sched.total_line.notna()]
    avg_itt = season_lines.total_line.mean() / 2 if len(season_lines) else 22.0
    return ctx, avg_itt


def defense_factors(ps, season, week, stat, positions):
    """How much each defense allows to a position vs league average (shrunk toward 1.0)."""
    d = ps[(ps.season == season) & (ps.week < week) & ps.position.isin(positions)]
    if d.empty:
        return pd.DataFrame(columns=["opp", "position", "def_factor"])
    per_game = d.groupby(["opponent_team", "position", "week"])[stat].sum().reset_index()
    league = per_game.groupby("position")[stat].mean().rename("lg")
    agg = per_game.groupby(["opponent_team", "position"])[stat].agg(["mean", "count"]).reset_index()
    agg = agg.join(league, on="position")
    w = agg["count"] / (agg["count"] + C.DEF_SHRINK_GAMES)
    agg["def_factor"] = 1 + (agg["mean"] / agg["lg"].replace(0, np.nan) - 1).fillna(0) * w
    return agg.rename(columns={"opponent_team": "opp"})[["opp", "position", "def_factor"]]


# ----------------------------------------------------------------------------- baselines
def _weights(hist, season):
    hist = hist.sort_values("t", ascending=False).copy()
    hist["ago"] = hist.groupby("player_id").cumcount()
    hist = hist[hist.ago < C.MAX_GAMES]
    hist["w"] = 0.5 ** (hist.ago / C.HALF_LIFE_GAMES) * np.where(hist.season < season, C.PRIOR_SEASON_WEIGHT, 1.0)
    return hist


def player_baselines(hist, market, season=None):
    """Weighted volume x shrunk efficiency, plus within-player volatility.
    Role-change dampener: if a player's volume this season is far below last season's, last season's
    games are weighted down in proportion (a 2-target decoy no longer inherits a 10-target past)."""
    m = C.MARKETS[market]
    stat, vol = m["stat"], m["vol"]
    h = hist[hist.position.isin(m["pos"])].copy()
    h["x"] = h[stat].fillna(0)
    h["v"] = h[vol].fillna(0) if vol else h["x"]
    if season is not None:
        cur = h[h.season == season].groupby("player_id").v.agg(["mean", "size"])
        prior = h[h.season < season].groupby("player_id").v.mean()
        ratio = (cur["mean"] / prior).where(cur["size"] >= C.ROLE_MIN_GAMES).clip(C.ROLE_FLOOR, 1.0)
        f = h.player_id.map(ratio).fillna(1.0)
        h["w"] = np.where(h.season < season, h.w * f, h.w)
    h["wx"], h["wv"] = h.w * h.x, h.w * h.v

    g = h.groupby("player_id")
    b = pd.DataFrame({
        "w_sum": g.w.sum(), "wx": g.wx.sum(), "wv": g.wv.sum(), "games": g.size(),
        "position": g.position.first(), "name": g.player_display_name.first(),
    })
    b["vol_hat"] = b.wv / b.w_sum
    if vol:
        pos_eff = h.groupby("position").apply(lambda d: d.x.sum() / max(d.v.sum(), 1e-9), include_groups=False)
        prior = b.position.map(pos_eff)
        b["eff"] = (b.wx + m["k"] * prior) / (b.wv + m["k"])
        b["base_mean"] = b.vol_hat * b.eff
    else:
        b["base_mean"] = b.vol_hat

    # within-player volatility (weighted), used for the distribution shape
    h = h.join(b.base_mean.rename("bm"), on="player_id")
    h["sq"] = h.w * (h.x - h.bm) ** 2
    b["var_p"] = h.groupby("player_id").sq.sum() / b.w_sum
    return b[b.games >= C.MIN_GAMES]


def distribution_priors(b, kind):
    """Position-level volatility: CV for yards, variance/mean for counts."""
    ok = b[(b.games >= 5) & (b.base_mean > b.base_mean.quantile(0.4))]
    if kind == "yards":
        return (np.sqrt(ok.var_p) / ok.base_mean).groupby(ok.position).median()
    return (ok.var_p / ok.base_mean).groupby(ok.position).median()


# ----------------------------------------------------------------------------- projections
def build_projections(ps, sched, season, week, team_of=None):
    """One row per (player, market) for every team playing in `week`.
    team_of: optional Series player_id -> team (backtests pass the real team)."""
    hist = _weights(ps[ps.t < season * 100 + week], season)
    if team_of is None:
        team_of = hist.sort_values("t").groupby("player_id").team.last()
    ctx, avg_itt = game_context(sched, season, week)
    out = []
    for market, m in C.MARKETS.items():
        b = player_baselines(hist, market, season)
        if b.empty:
            continue
        b = b.join(team_of.rename("team"), how="inner").reset_index()
        b = b.merge(ctx, on="team", how="inner")
        b = b.merge(defense_factors(ps, season, week, m["stat"], m["pos"]),
                    on=["opp", "position"], how="left")
        b["def_factor"] = b.def_factor.fillna(1.0)

        env = (b.itt / avg_itt).fillna(1.0).clip(0.6, 1.5) ** m["alpha"]
        s = b.team_spread.clip(-14, 14)
        script = {"pass": 1 - C.SCRIPT_PASS_PER_PT * s,
                  "rush": 1 + C.SCRIPT_RUSH_PER_PT * s}.get(m["script"], 1.0)
        b["adj"] = (env * script * b.def_factor) ** C.ADJ_STRENGTH
        b["mean"] = b.base_mean * b["adj"]

        pri = distribution_priors(b, m["kind"]) if m["kind"] != "td" else None
        n, k = b.games, C.DIST_PRIOR_GAMES
        if m["kind"] == "yards":
            cv_p = np.sqrt(b.var_p) / b.base_mean.replace(0, np.nan)
            cv = ((n * cv_p.fillna(1) + k * b.position.map(pri).fillna(0.6)) / (n + k))
            b["var"] = (cv * b["mean"]) ** 2 + (C.PROJ_ERR * b["mean"]) ** 2
        elif m["kind"] == "count":
            d_p = b.var_p / b.base_mean.replace(0, np.nan)
            d = ((n * d_p.fillna(1) + k * b.position.map(pri).fillna(1.0)) / (n + k)).clip(lower=0.6)
            b["var"] = d * b["mean"] + (C.PROJ_ERR * b["mean"]) ** 2
        else:
            b["var"] = b["mean"] + (C.PROJ_ERR * b["mean"]) ** 2
        b["market"], b["kind"] = market, m["kind"]
        out.append(b[["player_id", "name", "position", "team", "opp", "game_id", "market", "kind",
                      "games", "base_mean", "adj", "mean", "var", "itt", "team_spread", "def_factor"]])
    proj = pd.concat(out, ignore_index=True) if out else pd.DataFrame()
    proj["name_key"] = proj.name.map(norm_name)
    return proj


def prob_over_under(mean, var, kind, line):
    """Returns (P over, P under, P push) for a line, using gamma (yards) or negative binomial (counts/TDs)."""
    mean = max(mean, 1e-6)
    var = max(var, mean * 1.0001) if kind != "yards" else max(var, 1e-6)
    if kind == "yards":
        dist = st.gamma(a=mean ** 2 / var, scale=var / mean)
        if float(line).is_integer():
            p_over, p_under = dist.sf(line + 0.5), dist.cdf(line - 0.5)
        else:
            p_over, p_under = dist.sf(line), dist.cdf(line)
    else:
        n = mean ** 2 / (var - mean)
        dist = st.nbinom(n, n / (n + mean))
        if float(line).is_integer():
            p_over, p_under = dist.sf(line), dist.cdf(line - 1)
        else:
            p_over, p_under = dist.sf(np.floor(line)), dist.cdf(np.floor(line))
    return float(p_over), float(p_under), float(max(0.0, 1 - p_over - p_under))
