# Game Analyst (working name)

Why do some Roblox games take off while others don't, and what can a developer change?

Game Analyst saves public data on thousands of Roblox games every day. It breaks down the core loops of the top
games in each genre, and it compares your game with the winners. It gives odds, not promises, because luck is part
of the answer.

## Status

Milestone 1, the daily data collector, works. The first full run was on 2026-11-12. The plan for the next
milestones is in [AGENTS.md](AGENTS.md).

## What the daily run saves

- **Games:** players online, visits, favorites, likes and dislikes, created and updated dates, genre, creator, icon.
- **Badges:** how many players earned each badge in the past day and in total. In games with progression badges,
  this shows where players quit.
- **Game passes:** names and prices.
- **Charts and search:** the rank of each game on the Charts page, and for each search term in `watch.toml`.

A game stays tracked after it leaves the charts, so the flops stay in the data, not only the hits. Every raw
response also goes into `data/raw/<day>/` as gzipped JSON lines, so the fields that are not in use today are kept.

## Use it

It needs Python 3.12 or newer. The collector uses only the standard library.

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install pytest
.venv/Scripts/python -m gameanalyst collect                      # today's snapshot, about 10-15 minutes
.venv/Scripts/python -m gameanalyst show --query "anime tower defense"
.venv/Scripts/python -m pytest
```

On Ronan's PC, the Windows task "GameAnalyst daily" runs the collector every day at 12:30 PM. It uses `pythonw`, so
no window opens. If the PC is off at that time, the run starts as soon as the PC is back on. Each run adds a line to
`data/logs/collect.log`. `scripts/daily.cmd` does one run by hand.

## Rules

Public endpoints only, no login, and no bots in live games. The full list is in [AGENTS.md](AGENTS.md).
