"""Settings for the NFL player prop value finder. Tune these, then re-run backtest.py."""
import os

# ---- Season / data ----
SEASON = 2026
PRIOR_SEASONS = 1            # how many past seasons feed the player baselines
PRIOR_SEASON_WEIGHT = 0.6    # last season's games count 60% as much as this season's
HALF_LIFE_GAMES = 5          # recency decay: a game 5 games ago counts half as much
MAX_GAMES = 17               # look-back window per player
MIN_GAMES = 2                # skip players with fewer games than this

# ---- Odds API (https://the-odds-api.com) ----
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
REGIONS = "us"               # each region multiplies credit cost
BOOKMAKERS = ""              # e.g. "draftkings,fanduel,betmgm,caesars" (overrides REGIONS if set)
CACHE_DIR = "cache"

# Market key -> how to model it. Six markets are on; the rest are off to fit the free Odds API plan
# (500 credits/month; a run costs about 15 credits per market). Turn more on by removing the "# ".
#   stat: nflverse column  | vol: opportunity column (None = the stat IS volume)
#   k: shrinkage strength for efficiency (in units of vol) | script: pass/rush/none
#   alpha: how strongly the team implied total moves the mean (1.0 = proportional)
MARKETS = {
    "player_pass_yds":            dict(stat="passing_yards",         vol="attempts", pos=["QB"],             kind="yards", k=150, script="pass", alpha=0.6),
    "player_pass_tds":            dict(stat="passing_tds",           vol="attempts", pos=["QB"],             kind="td",    k=200, script="pass", alpha=1.0),
    "player_rush_yds":            dict(stat="rushing_yards",         vol="carries",  pos=["RB", "QB"],       kind="yards", k=60,  script="rush", alpha=0.0),
    "player_reception_yds":       dict(stat="receiving_yards",       vol="targets",  pos=["WR", "TE", "RB"], kind="yards", k=30,  script="pass", alpha=0.6),
    "player_receptions":          dict(stat="receptions",            vol="targets",  pos=["WR", "TE", "RB"], kind="count", k=30,  script="pass", alpha=0.4),
    "player_anytime_td":          dict(stat="any_td",                vol="opps",     pos=["RB", "WR", "TE"], kind="td",    k=60,  script="none", alpha=1.0),
    # "player_pass_attempts":       dict(stat="attempts",              vol=None,       pos=["QB"],             kind="count", k=0,   script="pass", alpha=0.3),
    # "player_pass_completions":    dict(stat="completions",           vol="attempts", pos=["QB"],             kind="count", k=150, script="pass", alpha=0.4),
    # "player_pass_interceptions":  dict(stat="passing_interceptions", vol="attempts", pos=["QB"],             kind="td",    k=300, script="pass", alpha=0.0),
    # "player_rush_attempts":       dict(stat="carries",               vol=None,       pos=["RB"],             kind="count", k=0,   script="rush", alpha=0.0),
    # "player_rush_reception_yds":  dict(stat="rush_rec_yards",        vol="opps",     pos=["RB", "WR", "TE"], kind="yards", k=40,  script="none", alpha=0.4),
}

# ---- Model knobs (tuned on a 2025 walk-forward backtest; re-run backtest.py after changing) ----
DEF_SHRINK_GAMES = 16        # opponent adjustment gets weight g/(g+16); 4 games played -> 20%
SCRIPT_PASS_PER_PT = 0.008   # each point a team is favored by trims pass volume 0.8%
SCRIPT_RUSH_PER_PT = 0.006   # ...and adds 0.6% rush volume
ADJ_STRENGTH = 0.75          # dampens matchup/game-script multipliers (full strength was overconfident)
PROJ_ERR = 0.25              # extra uncertainty in our own mean (25% of the projection)
DIST_PRIOR_GAMES = 8         # shrink each player's volatility toward his position's

# ---- Value / staking ----
MODEL_WEIGHT = 0.35          # final prob blends model and no-vig market in odds space, 35% model. The market is sharp; respect it.
ONE_SIDED_MODEL_WEIGHT = 0.15  # less trust in the model when a book posts only one side (anytime TD), since the de-vig is a guess
MAX_PRICE_DEC = 4.0          # ignore longshots above +300: tail probabilities are where both model and de-vig are least reliable
CACHE_MAX_AGE_HOURS = 12     # reuse the last odds pull if it is newer than this (saves API credits); --fresh forces a new pull
ONE_SIDED_HOLD = 0.07        # assumed vig when a book only posts one side (e.g. anytime TD "Yes")
MIN_EV = 0.03                # only show plays with >= +3% expected value
MAX_RAW_EDGE = 0.15          # model vs market gaps bigger than this usually mean missing news: flagged
KELLY_FRACTION = 0.25        # quarter Kelly
MAX_STAKE_PCT = 0.02         # never more than 2% of bankroll on one prop
BET_LOG = "bet_log.csv"
