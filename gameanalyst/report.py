"""Read-only views over the store, for people."""

from __future__ import annotations

import datetime as dt
import re

from .store import Store

TAGS = re.compile(r"\[[^\]]*\]|【[^】]*】")
KEEP = set(" -'&!?:.,+")


def display_name(name: str | None, width: int = 32) -> str:
    """Drop update tags like "[UPD 21]" and emoji, so the names line up in a terminal."""
    text = TAGS.sub("", name or "")
    text = "".join(c for c in text if c.isalnum() or c in KEEP)
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 1] + "…"


def human(n: int | None) -> str:
    if n is None:
        return "-"
    for unit, size in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if abs(n) >= size:
            return f"{n / size:.1f}{unit}"
    return str(n)


def like_share(up: int | None, down: int | None) -> str:
    total = (up or 0) + (down or 0)
    return f"{100 * (up or 0) / total:.0f}%" if total else "-"


def days_since(iso: str | None, day: str) -> str:
    if not iso:
        return "-"
    return f"{(dt.date.fromisoformat(day) - dt.date.fromisoformat(iso[:10])).days}d"


def latest_day(store: Store) -> str | None:
    return store.db.execute("SELECT MAX(day) FROM game_daily").fetchone()[0]


def table_rows(
    store: Store, day: str, query: str | None = None, chart: str | None = None, own: bool = False, top: int = 20
) -> list[dict]:
    """One day's games, most players online first. Filter by a search term, a chart, or your own games."""
    where, args = ["g.day = ?"], [day]
    if own:
        where.append("g.universe_id IN (SELECT universe_id FROM game_sources WHERE source LIKE 'place:%')")
    if query:
        where.append("g.universe_id IN (SELECT universe_id FROM search_daily WHERE day = ? AND query = ?)")
        args += [day, query]
    if chart:
        where.append("g.universe_id IN (SELECT universe_id FROM chart_daily WHERE day = ? AND sort_id = ?)")
        args += [day, chart]
    sql = f"""
        SELECT g.universe_id, g.name, g.playing, g.visits, g.favorites, g.up_votes, g.down_votes,
               g.created, g.updated,
               (SELECT COUNT(*) FROM pass_daily p WHERE p.day = g.day AND p.universe_id = g.universe_id) AS passes,
               (SELECT COUNT(*) FROM badge_daily b WHERE b.day = g.day AND b.universe_id = g.universe_id) AS badges
        FROM game_daily g
        WHERE {' AND '.join(where)}
        ORDER BY g.playing DESC
        LIMIT ?"""
    cursor = store.db.execute(sql, [*args, top])
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def format_table(rows: list[dict], day: str) -> str:
    head = ["#", "Game", "Playing", "Visits", "Favs", "Likes", "Updated", "Age", "Passes", "Badges"]
    body = [
        [
            str(n), display_name(r["name"]), human(r["playing"]), human(r["visits"]), human(r["favorites"]),
            like_share(r["up_votes"], r["down_votes"]), days_since(r["updated"], day) + " ago",
            days_since(r["created"], day), str(r["passes"]), str(r["badges"]),
        ]
        for n, r in enumerate(rows, 1)
    ]
    widths = [max(len(cell) for cell in column) for column in zip(head, *body)]

    def line(cells: list[str]) -> str:
        return "  ".join(c.ljust(w) if i == 1 else c.rjust(w) for i, (c, w) in enumerate(zip(cells, widths)))

    note = f"Day {day} (UTC). Playing = players online at the moment the run saved the game."
    return "\n".join([note, line(head), *map(line, body)])
