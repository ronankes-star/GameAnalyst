"""One daily run: find games (Charts page, searches, own places), then save today's numbers for every tracked game.

A game stays tracked after it leaves the charts. That keeps the flops in the data, not only the hits.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .http import HttpError
from .roblox import Roblox
from .store import RawArchive, Store


@dataclass
class Plan:
    queries: list[str] = field(default_factory=list)
    search_pages: int = 2
    query_pages: dict[str, int] = field(default_factory=dict)  # search terms that get more (or fewer) pages
    place_ids: list[int] = field(default_factory=list)
    use_charts: bool = True
    limit: int | None = None  # collect at most this many games (for quick tests)
    badge_pages: int = 3
    pass_pages: int = 2
    quiet_below: int = 20  # players online. A quiet game gets its badges and passes once a week, not every day.
    detail_every: int = 7  # days between two badge and pass checks of a quiet game


@dataclass
class RunResult:
    day: str
    discovered: int = 0
    collected: int = 0
    skipped: int = 0
    quiet: int = 0  # quiet games whose badges and passes were not due today
    errors: list[str] = field(default_factory=list)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def stamp() -> str:
    return utc_now().isoformat(timespec="seconds")


def discover(rbx: Roblox, store: Store, raw: RawArchive, plan: Plan, day: str, result: RunResult) -> None:
    def track(universe_id: int, source: str) -> None:
        if store.track(universe_id, day, source):
            result.discovered += 1

    if plan.use_charts:
        charts = rbx.charts()
        raw.write("charts", day, charts)
        for sort_id, games in charts.items():
            store.add("chart_daily", [ranked_row(day, rank, game, sort_id=sort_id) for rank, game in enumerate(games, 1)])
            for game in games:
                track(game["universeId"], f"chart:{sort_id}")
    for query in plan.queries:
        hits = rbx.search(query, pages=plan.query_pages.get(query, plan.search_pages))
        raw.write("search", query, hits)
        store.add("search_daily", [ranked_row(day, rank, hit, query=query) for rank, hit in enumerate(hits, 1)])
        for hit in hits:
            track(hit["universeId"], f"search:{query}")
    for place_id in plan.place_ids:
        try:
            track(rbx.universe_for_place(place_id), f"place:{place_id}")
        except HttpError as e:
            result.errors.append(f"place {place_id}: HTTP {e.status}")
    store.commit()


def ranked_row(day: str, rank: int, game: dict, **key: str) -> dict:
    return {
        "day": day, **key, "rank": rank, "universe_id": game["universeId"],
        "player_count": game.get("playerCount"), "is_sponsored": int(bool(game.get("isSponsored"))),
    }


def game_row(day: str, universe_id: int, game: dict, votes: dict, icon: dict, collected_at: str) -> dict:
    creator = game.get("creator") or {}
    return {
        "day": day, "universe_id": universe_id, "root_place_id": game.get("rootPlaceId"), "name": game.get("name"),
        "creator_type": creator.get("type"), "creator_id": creator.get("id"), "creator_name": creator.get("name"),
        "creator_verified": int(bool(creator.get("hasVerifiedBadge"))),
        "playing": game.get("playing"), "visits": game.get("visits"), "favorites": game.get("favoritedCount"),
        "up_votes": votes.get("upVotes"), "down_votes": votes.get("downVotes"),
        "created": game.get("created"), "updated": game.get("updated"),
        "genre_l1": game.get("genre_l1"), "genre_l2": game.get("genre_l2"),
        "max_players": game.get("maxPlayers"), "price": game.get("price"),
        "icon_url": icon.get("imageUrl"), "collected_at": collected_at,
    }


def badge_row(day: str, universe_id: int, badge: dict) -> dict:
    stats = badge.get("statistics") or {}
    return {
        "day": day, "universe_id": universe_id, "badge_id": badge["id"], "name": badge.get("name"),
        "enabled": int(bool(badge.get("enabled"))), "created": badge.get("created"),
        "awarded_past_day": stats.get("pastDayAwardedCount"), "awarded_total": stats.get("awardedCount"),
    }


def pass_row(day: str, universe_id: int, game_pass: dict) -> dict:
    return {
        "day": day, "universe_id": universe_id, "pass_id": game_pass["id"], "name": game_pass.get("name"),
        "price": game_pass.get("price"), "for_sale": int(bool(game_pass.get("isForSale"))),
    }


def on_its_weekday(universe_id: int, day: str, every: int = 7) -> bool:
    """Each quiet game has its own weekday, from its universe id. So each day checks about a seventh of them."""
    return dt.date.fromisoformat(day).toordinal() % every == universe_id % every


def needs_details(store: Store, plan: Plan, universe_id: int, day: str, playing: int | None) -> bool:
    """Badges and passes cost two requests per game. A busy game gets them every day. A quiet game gets them on its
    own weekday, and at once when it was never checked or its last check is a week old (after missed days).

    Players, visits, favorites and votes come in cheap batches, so every game keeps those every day.
    """
    if (playing or 0) >= plan.quiet_below:
        return True
    last = store.last_details(universe_id, day)
    if last is None:
        return True
    age = (dt.date.fromisoformat(day) - dt.date.fromisoformat(last)).days
    return age >= plan.detail_every or on_its_weekday(universe_id, day, plan.detail_every)


def collect_day(
    rbx: Roblox,
    store: Store,
    raw: RawArchive,
    plan: Plan,
    day: str | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> RunResult:
    started = stamp()
    day = day or utc_now().date().isoformat()
    result = RunResult(day)
    discover(rbx, store, raw, plan, day, result)

    tracked = store.tracked()
    todo = [uid for uid in tracked if not store.has_game_day(day, uid)]
    result.skipped = len(tracked) - len(todo)
    if plan.limit is not None:
        todo = todo[: plan.limit]

    games = {game["id"]: game for game in rbx.games(todo)}
    votes = {vote["id"]: vote for vote in rbx.votes(todo)}
    icons = {icon["targetId"]: icon for icon in rbx.icons(todo)}

    for done, uid in enumerate(todo, 1):
        game = games.get(uid)
        if game is None:
            result.errors.append(f"{uid}: no game data")
            continue
        raw.write("games", uid, {"game": game, "votes": votes.get(uid), "icon": icons.get(uid)})
        store.add("game_daily", [game_row(day, uid, game, votes.get(uid, {}), icons.get(uid, {}), stamp())])
        store.save_text(day, uid, game.get("description"))
        if needs_details(store, plan, uid, day, game.get("playing")):
            try:
                badges = rbx.badges(uid, plan.badge_pages)
                raw.write("badges", uid, badges)
                store.add("badge_daily", [badge_row(day, uid, badge) for badge in badges])
                passes = rbx.game_passes(uid, plan.pass_pages)
                raw.write("passes", uid, passes)
                store.add("pass_daily", [pass_row(day, uid, game_pass) for game_pass in passes])
                store.mark_details(day, uid)
            except HttpError as e:
                result.errors.append(f"{uid}: HTTP {e.status} on {e.url.split('?')[0]}")
        else:
            result.quiet += 1
        store.commit()  # one commit per game, so a crash keeps the work done so far
        result.collected += 1
        if progress:
            progress(done, len(todo))

    store.log_run(started, stamp(), day, result.collected, rbx.http.requests_made, result.errors)
    return result


def backfill_text(store: Store, raw_root: str | Path) -> int:
    """Fill game_text from the raw archive, for the days collected before descriptions had a table.

    It is safe to run again: a description that is already saved is not saved twice. Returns the rows added.
    """
    added = 0
    for day in RawArchive.days(raw_root):
        for key, payload in RawArchive.read(raw_root, day, "games"):
            game = (payload or {}).get("game") or {}
            added += store.save_text(day, int(key), game.get("description"))
        store.commit()
    return added
