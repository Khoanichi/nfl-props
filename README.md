# NFL Prop Value Finder

Finds player props where the price is better than the true probability. It does **not** look for
"locks." A -300 favorite that hits 75% of the time is a losing bet if it should be -400.
The only thing that matters is your win probability vs. the price.

## How it works
1. **Baseline** (`model.py`): recency-weighted volume (targets, carries, attempts) x efficiency
   (yards per target, etc.), with efficiency shrunk toward the position average so a hot two-game
   stretch doesn't fool it. Last season counts at 60%.
2. **Adjustments**: team implied total (from the spread and total), game script (favorites run,
   underdogs pass), and how much the opponent allows to that position. All dampened, because the
   backtest showed full-strength adjustments were overconfident.
3. **Distribution**: gamma for yards (right-skewed: a WR can go for 150 but never -50),
   negative binomial for receptions/attempts/TDs. Gives P(over) and P(under) for any line.
4. **Market** (`odds.py`): pulls every book's line, removes the vig, takes the consensus.
5. **Value** (`find_value.py`): final probability = 35% model + 65% market. Shows a play only if
   the best available price is +3% EV or better. Stake = quarter Kelly, capped at 2% of bankroll.
6. **Grading** (`grade.py`): scores your logged plays against real box scores.

## Setup (Windows, PowerShell)
```powershell
cd prop_model
py -m pip install -r requirements.txt
setx ODDS_API_KEY "your_key_here"     # free key at the-odds-api.com; open a NEW terminal after this
```

## Weekly routine
```powershell
py backtest.py --season 2025               # once, or after changing config.py
py find_value.py --week 5 --log            # Thu/Sat after props post (uses API credits)
py find_value.py --week 5 --cache cache\odds_XXXX.json   # re-run free on saved odds
py grade.py                                # Tuesday, after the week finishes
```
Each run costs about 15 credits per market turned on in `config.py` (6 on = about 90). The free plan is
500 a month, enough for one run a week with 6 markets. Turn on the other 5 markets if you move to a paid plan.
A run reuses odds pulled in the last 12 hours for free; add `--fresh` to force a new pull.

## Use it from your phone
`report.py` turns each run into a phone-friendly page (`docs/index.html`). Two ways to get it on your phone:

**Hands-off (recommended):** put this folder in a GitHub repo and let GitHub run it for you.
1. Create a repo on github.com, upload these files.
2. Repo Settings > Secrets and variables > Actions > New secret: `ODDS_API_KEY`.
3. Repo Settings > Pages > Source: Deploy from branch, branch `main`, folder `/docs`.
4. The included workflow (`.github/workflows/props.yml`) runs Saturday morning, grades on Tuesday,
   and republishes the page. Bookmark `https://<you>.github.io/<repo>/` on your phone.
   You can also trigger a run anytime from the GitHub mobile app (Actions tab > Weekly props > Run workflow).

**Manual:** run `py find_value.py --week auto --log` then `py report.py` on your PC and open
`docs\index.html` from Google Drive or email on your phone.

## The phone page
Every priced prop is on the page, one card per player and side. Filters at the top: market chips, a
player/team search, minimum model win %, minimum edge, sort by edge, model % or kickoff, and a box to
include the "check news" plays (model and market disagree by 15%+; usually a role change the stats
haven't caught up with). Defaults show plays at +3% edge or better.

## Games dashboard (games.html)
One card per game: consensus spread and total, how far each has moved since we first saw it, and the
public's share of tickets and money on each side (from Action Network's public feed, unofficial; if it
is down the card shows lines only, or you can supply a splits.csv with columns away,home,market,side,tickets,money).
A "Trap?" tag appears when two or more of these line up: 70%+ of tickets on one side, the line moving
against that side, or money share far above ticket share. Charts at the bottom: plays by market, overs vs
unders, and running profit by week once picks are graded. Costs 2 API credits per run.

## Reading the output
| column | meaning |
|---|---|
| proj | model's projected mean |
| model / market_ | model's win % vs. the no-vig market win % |
| ev_pct | expected profit per $100, using the best price found |
| stake | % of bankroll (quarter Kelly) |
| flags | **BIG-GAP:check-news** = model and market disagree by 15%+. Usually the market knows something (injury, role change). Check before betting. **Q-tag**, **small-sample**, **one-sided-mkt** = lower trust |

## Backtest (2025, weeks 4-18, ~10,800 projections)
- Probabilities are well calibrated from 20% to 50%; slightly overconfident above 55%,
  which is why the market gets 65% of the vote.
- The model beats a plain recent average by 0.5-2% on passing and receiving, and ties on rushing.
- Takeaway: public box-score data alone won't beat sharp books. Realistic edges come from
  **line shopping**, **reacting to injury news before lines move**, and **softer books**.

## Rules that keep you solvent
- Judge it after 200+ graded bets, not one week.
- Don't combine correlated props as if independent (QB pass yards + his WR's receiving yards).
- Track closing line value: if lines keep moving toward your side after you bet, you're finding real edges.

## Good next upgrades
- Wind/weather (15+ mph wind cuts passing and kicking)
- Snap counts and routes run (`nfl.load_snap_counts`, `load_ff_opportunity`) to catch role changes early
- Teammate injuries: redistribute vacated targets/carries
- An LLM step that reads injury and beat-reporter news and flags plays the numbers can't see
