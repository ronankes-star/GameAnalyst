# Game Analyst (working name)

An AI system that explains why Roblox games succeed or fail, and what a developer can change to do better.
First user: Ronan, the owner, who runs several Roblox games. Later users: other Roblox developers.

Scope: every kind of Roblox game, in every genre. Anime tower defense is only the first genre that gets a deep
study, because it is the first test of the riskiest assumption. The data, the lists and the study work for any
genre.

Keep the work real and visible: small commits with clear messages, tests, and a README that stays true.

## How to work with Ronan
- Explain things in ASD-STE100 Simplified Technical English: short sentences, active voice, one idea per sentence.
- He directs the product and checks the results. Show results (numbers, tables, charts) before you explain code.
- Ask before anything that costs money, publishes something, or uses his accounts.
- Never ask him to paste passwords, cookies or API keys into the chat. Keys go in environment variables.

## The product: three layers
1. **Market data.** Every day, save a snapshot of thousands of public Roblox games. Past days can't be collected
   later, so the collector must run every day from the start.
2. **Loop breakdown.** For the top games in a genre, tag the core loop and the features from recorded gameplay:
   time to first reward, first Robux offer, rebirths, daily rewards, social features, update cadence.
3. **Game doctor.** For a developer's own game: compare its loop and its Creator Hub numbers with the winners in
   its genre. Then rank the fixes and show the evidence for each one. Later, bots can playtest the developer's own
   game in Roblox Studio to measure the loop exactly.

## Model approach
- Not one huge neural network. There is too little data for one, it can't explain itself, and it costs too much.
- Use a stack instead:
  1. Pretrained models turn icons, thumbnails, titles, descriptions and gameplay clips into features
     (embeddings). Don't train these.
  2. A small model (gradient-boosted trees to start) learns from those features plus the stats. Give per-feature
     attributions (for example SHAP values) for every prediction.
  3. An LLM writes the breakdown in plain words from those numbers.
- Luck is part of the output. Predict odds or ranges (for example "60% under 50 CCU, 8% over 1,000"), not one score.
- Calibrate and backtest. At launch, predict each new game's 30-day peak CCU, then compare with the real result.
  Show a rating only if the model beats a simple baseline (genre + creator group size). If it doesn't, show
  benchmarks instead.
- A bigger sequence model comes later, after months of daily snapshots.

## Riskiest assumption
Features that you can see from outside a game explain a useful share of its success, next to thumbnails, trends,
YouTubers, ad spend and luck.
First experiment: anime tower-defense games. Tag them, then check what separates the hits from the flops. Search
shows only about 40-55 of them, so all 232 TD games are the bigger comparison group. Then the same study runs for
the other genres.

## Roadmap
- [x] M1 Daily data collector: built 2026-11-12 (`python -m gameanalyst collect`). The Windows task
  "GameAnalyst daily" runs it at 12:30 PM local with `pythonw` (log: `data/logs/collect.log`, plus the `runs` table).
- [ ] M2 Genre lists + the anime TD study (the riskiest-assumption test). First version 2026-11-12: `list` and
  `study`, lists `anime-td` and `tower-defense`. Open: Ronan's check of the anime TD list, then more days of data.
- [ ] M2b Discovery across all genres, so that every genre has its flops in the data, not only its chart
  toppers. Done 2026-11-12 (Ronan approved the plan): all 26 charts, 56 genre search terms (3 pages each), weekly
  badge and pass checks for quiet games, a longer gap for a host that answers 429. 6,330 games tracked. Open:
  watch the daily run time and the 429 errors in the `runs` table. The daily task stops a run after 2 hours, and
  the estimate is about 60-105 minutes a day; tracked games only grow.
- [ ] M3 Model v0 + backtest + calibration report
- [ ] M4 Breakdown report (LLM) for one game
- [ ] M5 Web app
- [ ] M6 Game doctor (Creator Hub import, Studio bot playtests of the developer's own game)

## M1: daily data collector
Goal: one command that saves today's snapshot of a list of games. A scheduler runs it once a day.
- Keep a seed list of universe IDs. Grow it with Roblox's public discovery and search endpoints (find and verify
  them first).
- Save append-only daily snapshots (for example SQLite, or Parquet split by date). Never overwrite past days.
- Save per game: stats (playing, visits, favorites, likes/dislikes), created and updated dates, genre, creator
  (user or group), game passes and prices, badges with daily and total award counts, icon and thumbnail ids.
- Throttle the requests. Retry with backoff on 429 and 5xx. Log failures and keep the run going.
- Tests use saved sample responses (fixtures). Tests never call the live API.
- When it works, schedule it daily on this PC (Windows Task Scheduler).

### Roblox endpoints
Checked on 2026-11-12 (public, no login):
- `GET https://apis.roblox.com/universes/v1/places/{placeId}/universe` -> `universeId`
- `GET https://games.roblox.com/v1/games?universeIds={id1,id2,...}` (50 per call, 400 above that) -> name,
  playing, visits, favoritedCount, created, updated, genre_l1, genre_l2, creator, ...
- `GET https://games.roblox.com/v1/games/votes?universeIds=...` (100 per call) -> upVotes, downVotes
- `GET https://thumbnails.roblox.com/v1/games/icons?universeIds=...&size=150x150&format=Png` (100 per call)
- `GET https://apis.roblox.com/game-passes/v1/universes/{universeId}/game-passes?passView=Full&pageSize=100` ->
  gamePasses (price, isForSale), paged by `pageToken`. The old games.roblox.com game-passes endpoint is 404.
- `GET https://apis.roblox.com/search-api/omni-search?searchQuery=...&sessionId={uuid}&pageType=all` -> about
  40 games per page, paged by `pageToken`.
- `GET https://apis.roblox.com/explore-api/v1/get-sorts?sessionId={uuid}&device=computer&country=all` -> the
  Charts page: top-trending, up-and-coming, top-playing-now, fun-with-friends, top-revisited (about 320 games).
  That is only the first page of charts. Pass `nextSortsPageToken` back as `sortsPageToken` to page on: 26 charts
  in 5 pages, about 900 games. They include top-earning, top-paid-access, top-rated, most-popular, and
  "trending-in-<genre>" for 15 genres. The only filters are device and country. There is no genre filter, and a
  genre parameter changes nothing (checked 2026-11-12). The collector reads every page.
- `GET https://badges.roblox.com/v1/universes/{universeId}/badges?limit=100` -> per badge
  `statistics.pastDayAwardedCount` and `statistics.awardedCount`. `winRatePercentage` came back 0.0 for every
  badge, so don't rely on it. In games with progression badges, the counts show where players drop off.
  Paged by `cursor`.
- `GET https://games.roblox.com/v2/groups/{groupId}/games?accessFilter=2&limit=50&sortOrder=Desc` and
  `GET https://games.roblox.com/v2/users/{userId}/games?...` (same parameters) -> a creator's public games: `id`
  (the universe id), name, description, placeVisits. Paged by `nextPageCursor`. Checked 2026-11-12. Not used:
  the creators of 53 anime TD candidates had only 3 more anime TDs.
- Dead ends, checked 2026-11-12: `games.roblox.com/v1/games/recommendations/game/{universeId}` answers with an
  empty list, and `games.roblox.com/v1/games/list?keyword=...` is 404.
- The games endpoint cuts `description` at 1,000 characters.

## M2: genre lists + the anime TD study
- `python -m gameanalyst list` sorts every game of a day into in / check / out for a genre list, with the reason
  for each verdict. The words and Ronan's own decisions live in `lists/<name>.toml`. His decisions win over the
  words. Don't rely on a list before he checks it (the "check" group, and a skim of "in").
- `python -m gameanalyst study [NAME] [--mark OTHER] [--html out/NAME-study.html]` compares the hits of a list
  with its flops and its faded games on one day. Tiers: hit 1,000+ players online; middle 20-999; faded under 20
  now but 10M+ visits (big once); flop under 20, under 10M visits, 30+ days old; new under 20 and under 30 days old
  (left out of the comparison). For each number: the median per tier, and "hit vs flop" / "hit vs faded" = the
  AUC (the share of pairs where the hit is higher). It is "clear" only when its 95% range (Hanley-McNeil) leaves
  out 50%. `--mark OTHER` adds a yes/no row: is the game also in list OTHER?
- Lists: `anime-td` (genre + anime words; "maybe" words like Vocaloid or Touhou always go to "check") and
  `tower-defense` (genre only, the comparison group).
- Search, checked 2026-11-12: pages 1-3 hold a term's best matches. Deeper, about every third page holds more TD
  games, mostly not anime. Franchise terms ("bleach tower defense") and anime name terms ("anime royale") found
  almost no TD games that the general terms had not found. On 2026-11-12, 1,491 tracked games held 232 TD games
  and only 39 anime TDs (+15 to check). Search favors games that were big once: 10 of the 16 quiet anime TDs had
  10M+ visits. So the anime TD list grows mainly with time (new launches), not with more search terms.

## Code map
- `gameanalyst/http.py`: the polite client (0.3 s between two requests to the same host, a longer gap after a 429,
  retries with backoff, honors Retry-After). Each round trip takes about 0.3 s, so a run costs about 0.68 s per game
  that gets its badges and passes, and almost nothing for the other games (they come in batches).
- `gameanalyst/roblox.py`: endpoint wrappers with their batch and page limits.
- `gameanalyst/store.py`: SQLite tables (append-only, keyed by day) and the raw archive
  `data/raw/<day>/<kind>.jsonl.gz`. `game_text` keeps descriptions, one row per change. `detail_checks` keeps
  the days a game's badges and passes were saved: every day for busy games, once a week for games with under 20
  players online (each on its own weekday, so the load stays even). The study and `show` read each game's last check. The file is in WAL mode,
  so people can read while the daily run writes.
- `gameanalyst/collect.py`: one daily run (find games, then save each tracked game). `backfill_text` fills
  `game_text` from the raw archive (`python -m gameanalyst backfill-text`).
- `gameanalyst/lists.py` and `lists/*.toml`: genre lists (in / check / out, with reasons).
- `gameanalyst/study.py`: hits vs flops on one day. `gameanalyst/study_page.py`: the same as one web page.
- `gameanalyst/report.py` and `gameanalyst/cli.py`: the text views and the commands.
- `watch.toml`: search terms (with more pages for some terms) and Ronan's own place ids. `scripts/daily.cmd`: the
  entry point for a scheduler.
- `tests/`: a fake Roblox in `tests/fakes.py`. Tests never call the live API.

## Hard rules
- Never automate the Roblox client. Never send bots into live public games: Roblox lists bot use as banned
  behavior. Bots may only playtest a developer's own game in Studio.
- Public endpoints only. Never use a Roblox account cookie (`.ROBLOSECURITY`).
- No secrets in git. Keys live in environment variables, and `.env` stays ignored.
- Raw data stays out of git (`data/` is ignored). Commit code, schemas and small fixtures.
- Send a generic User-Agent. Never put Ronan's name or email in requests.

## Environment
- Windows 11. Shells: PowerShell and Git Bash.
- Python: use `py -3.14` (3.14.7) with a project virtual environment. The `python` on PATH is 3.12 without numpy or
  Pillow.
- Node 24 is installed (for the web app later). `uv` is not installed.
- GitHub account: ronankes-star. Push only when Ronan says so.
