# Game Analyst (working name)

Why do some Roblox games take off while others don't, and what can a developer change?

Game Analyst saves public data on thousands of Roblox games every day. It breaks down the core loops of the top
games in each genre, and it compares your game with the winners. It gives odds, not promises, because luck is part
of the answer.

## Status

Milestone 1, the daily data collector, works. The first full run was on 2026-11-12.

Milestone 2 has its first version: a genre list of anime tower-defense games, and a first look at what separates
the hits from the flops in it (one day of data, no model). The list waits for Ronan's check. The plan for the
next milestones is in [AGENTS.md](AGENTS.md).

## What the daily run saves

- **Games:** players online, visits, favorites, likes and dislikes, created and updated dates, genre, creator, icon.
- **Badges:** how many players earned each badge in the past day and in total. In games with progression badges,
  this shows where players quit.
- **Game passes:** names and prices.
- **Descriptions:** saved on the days they change, so the genre lists can read them.
- **Charts and search:** the rank of each game on the Charts page, and for each search term in `watch.toml`.

A game stays tracked after it leaves the charts, so the flops stay in the data, not only the hits. Every raw
response also goes into `data/raw/<day>/` as gzipped JSON lines, so the fields that are not in use today are kept.

## Use it

It needs Python 3.12 or newer. The collector uses only the standard library.

```bash
py -3.14 -m venv .venv
.venv/Scripts/python -m pip install pytest
.venv/Scripts/python -m gameanalyst collect                      # today's snapshot, about 20-40 minutes
.venv/Scripts/python -m gameanalyst show --query "anime tower defense"
.venv/Scripts/python -m gameanalyst list                         # the anime TD list: counts and the games to check
.venv/Scripts/python -m gameanalyst list --all                   # also the games in it, and the TD games left out
.venv/Scripts/python -m gameanalyst show --list anime-td         # the usual table, only the games in the list
.venv/Scripts/python -m gameanalyst study --html out/anime-td-study.html   # hits vs flops, also as a web page
.venv/Scripts/python -m gameanalyst study tower-defense --mark anime-td    # every TD game; marks the anime TDs
.venv/Scripts/python -m pytest
```

On Ronan's PC, the Windows task "GameAnalyst daily" runs the collector every day at 12:30 PM. It uses `pythonw`, so
no window opens. If the PC is off at that time, the run starts as soon as the PC is back on. Each run adds a line to
`data/logs/collect.log`. `scripts/daily.cmd` does one run by hand.

## Genre lists

A genre list is a TOML file in `lists/`. `lists/anime-td.toml` sorts every saved game into "in", "check" or
"out", and it gives the reason for each verdict:

- **in:** Roblox files the game as Tower Defense, and its name or description shows the anime theme (the word
  "anime", a franchise like Jujutsu Kaisen, a character like Gojo, or a known anime TD title), and no other theme.
- **check:** the signs disagree, or the game shows an anime-style franchise like Vocaloid or Touhou. Only these
  games need a person's decision.
- **out:** not Tower Defense, another theme (toilets, Five Nights, Undertale), or no anime words at all.

To decide a game by hand, put its universe id under `[include]` or `[exclude]` in the file. These decisions win
over the words. `study --html` writes a page with every game's icon, a link to it on Roblox, and its reasons.

`lists/tower-defense.toml` has no theme words: the Roblox genre alone decides. It is the bigger comparison group.

The study puts each game in a tier: **hit** (1,000+ players online), **middle** (20-999), **faded** (under 20 now,
but 10M+ visits: it was big once), **flop** (under 20, under 10M visits, 30+ days old) and **new** (under 20, under
30 days old). For each number it shows the median per tier, and how often a random hit beats a random flop (and a
random faded game). One day of data shows differences, not causes.

## Rules

Public endpoints only, no login, and no bots in live games. The full list is in [AGENTS.md](AGENTS.md).
