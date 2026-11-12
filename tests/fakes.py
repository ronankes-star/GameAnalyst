"""A fake Roblox: it answers like the real web APIs do, from small canned data. Tests never call the live API."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from gameanalyst.collect import Plan, RunResult, collect_day
from gameanalyst.http import Http
from gameanalyst.roblox import Roblox
from gameanalyst.store import RawArchive, Store

A, B, C = 1001, 1002, 1003  # universe ids
PLACE_OF_C = 555
DAY = "2026-11-12"


DESCRIPTIONS = {  # A reads like an anime TD, B like a toilet TD, C has no description
    A: "Summon units from your favorite anime worlds and defend the base!",
    B: "Place cameramen to fight back against the toilets!",
}


def game(uid: int) -> dict:
    return {
        "id": uid, "rootPlaceId": uid * 10, "name": f"[UPD 3] Game {uid}", "description": DESCRIPTIONS.get(uid, ""),
        "creator": {"id": 7, "name": "Studio", "type": "Group", "hasVerifiedBadge": False},
        "playing": uid - 1000, "visits": uid * 1000, "favoritedCount": uid,
        "created": "2026-01-01T00:00:00Z", "updated": "2026-11-10T00:00:00Z",
        "genre_l1": "Strategy", "genre_l2": "Tower Defense", "maxPlayers": 4, "price": None,
    }


def badge(uid: int, n: int) -> dict:
    return {
        "id": uid * 10 + n, "name": f"Badge {n}", "enabled": True, "created": "2026-01-02T00:00:00Z",
        "statistics": {"pastDayAwardedCount": 10 * n, "awardedCount": 100 * n, "winRatePercentage": 0.0},
    }


class FakeRoblox:
    """A transport for Http. It records each URL. It can answer 429 a few times first, or 404 for some URLs."""

    def __init__(self, throttle_429: dict[str, int] | None = None, missing: tuple[str, ...] = ()):
        self.urls: list[str] = []
        self.throttle_429 = dict(throttle_429 or {})
        self.missing = missing

    def __call__(self, url: str, headers: dict, timeout: float) -> tuple[int, dict, bytes]:
        self.urls.append(url)
        for part, left in self.throttle_429.items():
            if part in url and left > 0:
                self.throttle_429[part] = left - 1
                return 429, {"Retry-After": "0"}, b"{}"
        if any(part in url for part in self.missing):
            return 404, {}, b'{"errors": [{"code": 404}]}'
        parsed = urlparse(url)
        body = self.route(parsed, {k: v[0] for k, v in parse_qs(parsed.query).items()})
        if body is None:
            return 404, {}, b"{}"
        return 200, {}, json.dumps(body).encode()

    def route(self, u, q: dict) -> dict | None:
        ids = [int(x) for x in q["universeIds"].split(",")] if "universeIds" in q else []
        if u.path.endswith("/get-sorts"):
            if q.get("sortsPageToken") == "s2":  # the second page of charts
                return {"sorts": [{"sortId": "top-earning", "contentType": "Games",
                                   "games": [{"universeId": A, "playerCount": 900}]}]}
            return {"nextSortsPageToken": "s2", "sorts": [
                {"sortId": "filters_v5", "contentType": "Filters"},
                {"sortId": "top-playing-now", "contentType": "Games",
                 "games": [{"universeId": A, "playerCount": 900}, {"universeId": B, "playerCount": 50}]},
            ]}
        if u.path.endswith("/omni-search"):
            if q.get("pageToken") == "p2":
                return {"searchResults": [{"contentGroupType": "Game", "contents": [{"universeId": C, "playerCount": 3}]}]}
            return {
                "searchResults": [
                    {"contentGroupType": "Game", "contents": [{"universeId": B, "playerCount": 50, "isSponsored": True}]},
                    {"contentGroupType": "Ad", "contents": [{"universeId": 9999}]},
                ],
                "nextPageToken": "p2",
            }
        if u.path.endswith(f"/places/{PLACE_OF_C}/universe"):
            return {"universeId": C}
        if u.netloc == "games.roblox.com" and u.path == "/v1/games/votes":
            return {"data": [{"id": i, "upVotes": 90, "downVotes": 10} for i in ids]}
        if u.netloc == "games.roblox.com" and u.path == "/v1/games":
            return {"data": [game(i) for i in ids]}
        if u.path == "/v1/games/icons":
            return {"data": [{"targetId": i, "state": "Completed", "imageUrl": f"https://cdn.test/{i}.png"} for i in ids]}
        if u.path.endswith("/badges"):
            uid = int(u.path.split("/")[-2])
            if q.get("cursor") == "c2":
                return {"data": [badge(uid, 3)], "nextPageCursor": None}
            return {"data": [badge(uid, 1), badge(uid, 2)], "nextPageCursor": "c2"}
        if u.path.endswith("/game-passes"):
            uid = int(u.path.split("/")[-2])
            return {"gamePasses": [{"id": uid * 100 + 1, "name": "2x Speed", "price": 99, "isForSale": True}],
                    "nextPageToken": None}
        return None


def fake_roblox(fake: FakeRoblox | None = None) -> tuple[Roblox, FakeRoblox]:
    fake = fake or FakeRoblox()
    return Roblox(Http(transport=fake, min_interval=0, sleep=lambda seconds: None)), fake


def run_fake_day(tmp_path: Path, fake: FakeRoblox | None = None, **plan) -> tuple[RunResult, Store]:
    rbx, _ = fake_roblox(fake)
    store = Store(tmp_path / "db.sqlite")
    raw = RawArchive(tmp_path / "raw", DAY)
    try:
        result = collect_day(rbx, store, raw, Plan(queries=["anime td"], place_ids=[PLACE_OF_C], **plan), DAY)
    finally:
        raw.close()
    return result, store
