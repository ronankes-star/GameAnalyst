"""The study as one self-contained web page: the hits vs flops comparison, then the list for a person to check.

No scripts or styles from the internet. Only the game icons load from Roblox's image servers.
"""

from __future__ import annotations

import math
import zlib
from html import escape

from .lists import CHECK, IN, Decision, Rules
from .report import display_name, human, list_note
from .study import (
    FADED, FLOP, GROUPS, HIT, MID, NEW_DAYS, ONE_DAY_CAN, ONE_DAY_CANT, TIER_NAMES, TIER_WORDS, TIERS, VERSUS,
    Feature, Study, fmt,
)

CSS = """
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --ring: rgba(11,11,11,0.10);
  --series-1: #2a78d6; --series-2: #eb6834;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
    --series-1: #3987e5; --series-2: #d95926;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --ring: rgba(255,255,255,0.10);
  --series-1: #3987e5; --series-2: #d95926;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1040px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 26px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 40px 0 8px; }
h3 { font-size: 15px; margin: 20px 0 6px; }
p, li { color: var(--ink-2); max-width: 75ch; }
.lead { margin: 0 0 20px; }
.card { background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; padding: 16px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.tile .value { font-size: 30px; font-weight: 650; }
.tile .label { color: var(--ink-2); font-size: 13px; }
table { border-collapse: collapse; width: 100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 8px; text-align: right; border-bottom: 1px solid var(--grid); white-space: nowrap; }
th:first-child, td:first-child { text-align: left; white-space: normal; }
td.words, th.words { text-align: left; color: var(--ink-2); }
tr.group td { color: var(--ink); font-weight: 600; padding-top: 16px; border-bottom: none; white-space: normal; }
.scroll { overflow-x: auto; }
.charts { display: grid; grid-template-columns: repeat(auto-fill, minmax(310px, 1fr)); gap: 12px; }
.chart h3 { margin: 0 0 2px; }
.chart .note { color: var(--muted); font-size: 12px; margin: 0 0 6px; }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg text { fill: var(--muted); font-size: 11px; }
svg .row-label { fill: var(--ink-2); font-size: 12px; }
svg .grid { stroke: var(--grid); stroke-width: 1; }
svg .base { stroke: var(--axis); stroke-width: 1; }
svg .dot { fill: var(--series-1); fill-opacity: .8; stroke: var(--surface); stroke-width: 1.5; }
svg .dot.own { fill: var(--series-2); fill-opacity: 1; }
svg .median { stroke: var(--ink); stroke-width: 2; stroke-linecap: round; }
#tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--ring); border-radius: 6px; padding: 4px 8px; font-size: 13px; display: none;
  box-shadow: 0 2px 8px rgba(0,0,0,.15); z-index: 10; }
.games { display: grid; grid-template-columns: repeat(auto-fill, minmax(290px, 1fr)); gap: 8px; }
.game { display: flex; gap: 10px; padding: 10px; align-items: flex-start; }
.game img, .game .no-icon { width: 48px; height: 48px; border-radius: 8px; flex: none; background: var(--grid); }
.game a { color: var(--ink); font-weight: 600; text-decoration: none; }
.game a:hover { text-decoration: underline; }
.game .meta { color: var(--ink-2); font-size: 13px; }
.game .why { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
.game.own { border-color: var(--series-2); }
code { font-size: 13px; }
details summary { cursor: pointer; font-weight: 600; margin: 12px 0; }
"""

SCRIPT = """
const tip = document.getElementById('tip');
document.querySelectorAll('svg.strip').forEach(svg => {
  const dots = [...svg.querySelectorAll('circle.dot')];
  svg.addEventListener('pointermove', e => {
    const box = svg.getBoundingClientRect();
    const scale = svg.viewBox.baseVal.width / box.width;
    const x = (e.clientX - box.left) * scale, y = (e.clientY - box.top) * scale;
    let best = null, bestD = 18 * 18;
    for (const d of dots) {
      const dx = d.cx.baseVal.value - x, dy = d.cy.baseVal.value - y, dist = dx * dx + dy * dy;
      if (dist < bestD) { best = d; bestD = dist; }
    }
    if (!best) { tip.style.display = 'none'; return; }
    tip.textContent = best.dataset.tip;
    tip.style.display = 'block';
    tip.style.left = Math.min(e.clientX + 12, window.innerWidth - tip.offsetWidth - 8) + 'px';
    tip.style.top = (e.clientY + 14) + 'px';
  });
  svg.addEventListener('pointerleave', () => { tip.style.display = 'none'; });
});
"""


def _x_scale(feature: Feature, values: list[float]):
    """A function value -> 0..1, and the tick values. Log scale (with zero) for counts, linear for shares."""
    if feature.unit in ("%", "yes"):
        return (lambda v: v / 100), [0, 25, 50, 75, 100]
    top = max(values or [1])
    log_top = math.log10(1 + max(top, 1))
    ticks = [0] + [10**k for k in range(0, int(math.floor(log_top)) + 1)]
    if 1 - math.log10(1 + ticks[-1]) / log_top >= 0.15:  # label the top end too, when there is room for it
        ticks.append(int(top))
    return (lambda v: math.log10(1 + max(v, 0)) / log_top), ticks


def _tick_label(feature: Feature, value: float) -> str:
    if feature.unit in ("%", "yes"):
        return f"{value:.0f}%"
    return human(int(value))


def strip_chart(study: Study, feature: Feature, tiers: tuple[str, ...], width: int = 480) -> str:
    """One row of dots per tier on a shared x scale, with the median of each row as a short dark line."""
    rows = {name: [r for r in study.tier_rows(name) if r[feature.key] is not None] for name in tiers}
    values = [r[feature.key] for name in tiers for r in rows[name]]
    if not values:
        return ""
    to_unit, ticks = _x_scale(feature, values)
    left, right, row_h, top = 74, width - 12, 30, 6
    height = top + row_h * len(tiers) + 22
    x = lambda v: left + (right - left) * to_unit(v)  # noqa: E731
    parts = [f'<svg class="strip" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{escape(feature.label)} by tier">']
    for t in ticks:
        parts.append(f'<line class="grid" x1="{x(t):.1f}" x2="{x(t):.1f}" y1="{top}" y2="{height - 22}"/>')
        parts.append(f'<text x="{x(t):.1f}" y="{height - 6}" text-anchor="middle">'
                     f'{escape(_tick_label(feature, t))}</text>')
    parts.append(f'<line class="base" x1="{left}" x2="{right}" y1="{height - 22}" y2="{height - 22}"/>')
    for i, name in enumerate(tiers):
        mid_y = top + row_h * i + row_h / 2
        parts.append(f'<text class="row-label" x="0" y="{mid_y + 4:.1f}">{TIER_NAMES[name]} '
                     f'({len(rows[name])})</text>')
        for r in rows[name]:
            jitter = (zlib.crc32(str(r["universe_id"]).encode()) % 1000) / 1000 * 14 - 7
            tip = f"{display_name(r['name'], 48)}: {fmt(feature, r[feature.key])}"
            own = " own" if r.get("own") else ""
            parts.append(f'<circle class="dot{own}" cx="{x(r[feature.key]):.1f}" cy="{mid_y + jitter:.1f}" r="4" '
                         f'data-tip="{escape(tip)}"/>')
        median = study.medians[feature.key][name]
        if median is not None and feature.unit != "yes":
            parts.append(f'<line class="median" x1="{x(median):.1f}" x2="{x(median):.1f}" '
                         f'y1="{mid_y - 11:.1f}" y2="{mid_y + 11:.1f}"/>')
    parts.append("</svg>")
    return "".join(parts)


def _game_card(game: dict, decision: Decision) -> str:
    name = escape(display_name(game["name"], 60) or str(game["universe_id"]))
    link = f"https://www.roblox.com/games/{game['root_place_id']}" if game.get("root_place_id") else "#"
    icon = (f'<img src="{escape(game["icon_url"])}" alt="" loading="lazy">' if game.get("icon_url")
            else '<div class="no-icon"></div>')
    genre = escape(game.get("genre_l2") or game.get("genre_l1") or "no genre")
    own = " own" if game.get("own") else ""
    return (
        f'<div class="card game{own}">{icon}'
        f'<div><a href="{escape(link)}" target="_blank" rel="noopener">{name}</a>'
        f'<div class="meta">{human(game["playing"])} online · {human(game["visits"])} visits · {genre}</div>'
        f'<div class="why">{escape("; ".join(decision.reasons))} · id {game["universe_id"]}</div></div></div>'
    )


def _games_block(title: str, note: str, items: list[tuple[dict, Decision]], open_: bool = True) -> str:
    cards = "".join(_game_card(game, decision) for game, decision in items)
    body = f'<p>{note}</p><div class="games">{cards}</div>' if items else "<p>None.</p>"
    return f'<details{" open" if open_ else ""}><summary>{escape(title)} ({len(items)})</summary>{body}</details>'


def study_page(study: Study, rules: Rules, decisions: list[tuple[dict, Decision]]) -> str:
    counts = study.counts()
    share = study.top_share()
    note = list_note(decisions)
    tiles = [
        (str(len(study.rows)), "games in the list"),
        (str(counts[HIT]), f"hits: {TIER_WORDS[HIT]}"),
        (str(counts[FADED]), f"faded: {TIER_WORDS[FADED]}"),
        (str(counts[FLOP]), f"flops: {TIER_WORDS[FLOP]}"),
        (f"{100 * share:.0f}%" if share is not None else "-", "of all players online sit in the 5 biggest games"),
    ]
    tile_html = "".join(f'<div class="card tile"><div class="value">{v}</div><div class="label">{escape(label)}</div>'
                        f"</div>" for v, label in tiles)

    heads = "".join(f"<th>{TIER_NAMES[name]}</th>" for name in TIERS)
    table = [f'<table><thead><tr><th>Number</th>{heads}<th class="words">Hit vs flop</th>'
             f'<th class="words">Hit vs faded</th></tr></thead><tbody>']
    for group, group_note in GROUPS.items():
        table.append(f'<tr class="group"><td colspan="{len(TIERS) + 3}">{escape(group_note)}</td></tr>')
        for feature in (f for f in study.features if f.group == group):
            medians = study.medians[feature.key]
            cells = "".join(f"<td>{escape(fmt(feature, medians[name]))}</td>" for name in TIERS)
            gaps = "".join(f'<td class="words">{escape(study.gaps[feature.key][other].words)}</td>'
                           for other in VERSUS)
            table.append(f"<tr><td>{escape(feature.label)}</td>{cells}{gaps}</tr>")
    table.append("</tbody></table>")

    charts = []
    for feature in study.features:
        if feature.group == "size" or feature.unit == "yes":
            continue
        svg = strip_chart(study, feature, (HIT, MID, FADED, FLOP), width=340)
        if svg:
            gaps = study.gaps[feature.key]
            charts.append(f'<div class="card chart"><h3>{escape(feature.label)}</h3>'
                          f'<p class="note">Hits vs flops: {escape(gaps[FLOP].words)}. Hits vs faded: '
                          f'{escape(gaps[FADED].words)}. Dark line = median.</p>{svg}</div>')

    by_verdict: dict[str, list] = {IN: [], CHECK: [], "out": []}
    for game, decision in decisions:
        by_verdict[decision.verdict].append((game, decision))
    genre_out = [(g, d) for g, d in by_verdict["out"] if (g.get("genre_l2") or "") in rules.genre_l2]
    genre_names = ", ".join(sorted(rules.genre_l2))
    has_own = any(r.get("own") for r in study.rows)

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(rules.title)} study</title><style>{CSS}</style></head>
<body><main>
<h1>{escape(rules.title)}: hits vs flops</h1>
<p class="lead">Day {escape(study.day)} (UTC). One snapshot, no model. {escape(note)}</p>
<div class="tiles">{tile_html}</div>

<h2>Players online, every game in the list</h2>
<p>Each dot is one game. The scale is logarithmic: each step is ten times the one before.
{"Orange dots are your own games. " if has_own else ""}Hover a dot to see the game.</p>
<div class="card">{strip_chart(study, study.features[0], TIERS, width=960)}</div>

<h2>What separates the hits from the flops</h2>
<p>Each row compares one number. The tier columns show the median game (for yes/no rows: the share of games).
"Hit vs flop": pick one hit and one flop at random. The % says how often the hit has the higher (or the lower)
value. 50% means no gap. "Hit vs faded" does the same with the games that were big once. "No clear gap" means
that the gap could be luck with this few games ({counts[HIT]} hits, {counts[FLOP]} flops, {counts[FADED]} faded).
New games (under {NEW_DAYS} days old) stay out of both columns, because they have not had their chance yet.</p>
<div class="card scroll">{"".join(table)}</div>
<div class="charts" style="margin-top:12px">{"".join(charts)}</div>

<h2>What one day of data can and can't show</h2>
<div class="tiles">
<div class="card"><h3>It can show</h3><ul>{"".join(f"<li>{escape(x)}</li>" for x in ONE_DAY_CAN)}</ul></div>
<div class="card"><h3>It can't show</h3><ul>{"".join(f"<li>{escape(x)}</li>" for x in ONE_DAY_CANT)}</ul></div>
</div>

<h2>The list: please check it</h2>
<p>The words in <code>lists/{escape(rules.name)}.toml</code> sort every saved game. Click a name to open the game on
Roblox. To decide a game, put its id under <code>[include]</code> or <code>[exclude]</code> in that file, then run
the study again. Your decisions win over the words.</p>
{_games_block("To check", "The signs disagree. Only these games need a decision.", by_verdict[CHECK])}
{_games_block("In the list", "Look for games that are not anime TDs.", by_verdict[IN])}
{_games_block(f"Left out, but Roblox files them as {genre_names}", "Look for anime TDs that the words missed.",
              genre_out, open_=False)}
</main><div id="tip"></div><script>{SCRIPT}</script></body></html>
"""

