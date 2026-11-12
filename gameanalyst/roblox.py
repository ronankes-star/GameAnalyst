"""Thin wrappers around Roblox's public web APIs (no login). They return the dicts that Roblox sends.

All endpoints and limits here were checked against the live API on 2026-11-12.
"""

from __future__ import annotations

import uuid
from typing import Iterable, Iterator

from .http import Http

GAMES = "https://games.roblox.com/v1/games"
VOTES = "https://games.roblox.com/v1/games/votes"
ICONS = "https://thumbnails.roblox.com/v1/games/icons"
BADGES = "https://badges.roblox.com/v1/universes/{uid}/badges"
PASSES = "https://apis.roblox.com/game-passes/v1/universes/{uid}/game-passes"
SEARCH = "https://apis.roblox.com/search-api/omni-search"
SORTS = "https://apis.roblox.com/explore-api/v1/get-sorts"
PLACE_UNIVERSE = "https://apis.roblox.com/universes/v1/places/{pid}/universe"

GAMES_BATCH = 50  # the games endpoint answers 400 above 50 ids
VOTES_ICONS_BATCH = 100


def chunks(items: list, size: int) -> Iterator[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class Roblox:
    def __init__(self, http: Http, session_id: str | None = None):
        self.http = http
        # Search and Charts want a session id. Any UUID works.
        self.session_id = session_id or str(uuid.uuid4())

    def games(self, universe_ids: Iterable[int]) -> list[dict]:
        return self._batched(GAMES, list(universe_ids), GAMES_BATCH)

    def votes(self, universe_ids: Iterable[int]) -> list[dict]:
        return self._batched(VOTES, list(universe_ids), VOTES_ICONS_BATCH)

    def icons(self, universe_ids: Iterable[int], size: str = "150x150") -> list[dict]:
        extra = {"size": size, "format": "Png", "isCircular": "false"}
        return self._batched(ICONS, list(universe_ids), VOTES_ICONS_BATCH, extra)

    def badges(self, universe_id: int, max_pages: int = 3) -> list[dict]:
        """Badges with their award counts: statistics.pastDayAwardedCount and statistics.awardedCount."""
        found, cursor = [], None
        for _ in range(max_pages):
            params = {"limit": 100, "sortOrder": "Asc"}
            if cursor:
                params["cursor"] = cursor
            page = self.http.get_json(BADGES.format(uid=universe_id), params)
            found.extend(page.get("data", []))
            cursor = page.get("nextPageCursor")
            if not cursor:
                break
        return found

    def game_passes(self, universe_id: int, max_pages: int = 2) -> list[dict]:
        found, token = [], None
        for _ in range(max_pages):
            params = {"passView": "Full", "pageSize": 100}
            if token:
                params["pageToken"] = token
            page = self.http.get_json(PASSES.format(uid=universe_id), params)
            found.extend(page.get("gamePasses", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return found

    def search(self, query: str, pages: int = 2) -> list[dict]:
        """Games for a search term, in Roblox's ranked order (about 40 per page)."""
        found, token = [], None
        for _ in range(pages):
            params = {"searchQuery": query, "sessionId": self.session_id, "pageType": "all"}
            if token:
                params["pageToken"] = token
            page = self.http.get_json(SEARCH, params)
            for group in page.get("searchResults", []):
                if group.get("contentGroupType") == "Game":
                    found.extend(group.get("contents", []))
            token = page.get("nextPageToken")
            if not token:
                break
        return found

    def charts(self) -> dict[str, list[dict]]:
        """The Charts page: sort id (top-trending, up-and-coming, top-playing-now, ...) -> ranked games."""
        page = self.http.get_json(SORTS, {"sessionId": self.session_id, "device": "computer", "country": "all"})
        return {
            sort["sortId"]: sort["games"]
            for sort in page.get("sorts", [])
            if sort.get("contentType") == "Games" and sort.get("games")
        }

    def universe_for_place(self, place_id: int) -> int:
        return int(self.http.get_json(PLACE_UNIVERSE.format(pid=place_id))["universeId"])

    def _batched(self, url: str, ids: list[int], size: int, extra: dict | None = None) -> list[dict]:
        rows: list[dict] = []
        for batch in chunks(ids, size):
            params = {"universeIds": ",".join(map(str, batch)), **(extra or {})}
            rows.extend(self.http.get_json(url, params).get("data", []))
        return rows
