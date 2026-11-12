"""A first, descriptive look at the hits and the flops in one genre list, on one day. No model.

Every game gets one row of numbers. Players online at the moment of the snapshot puts each game in a tier, and
all-time visits split the quiet games into "faded" (big once) and "flop" (never big). Then each number is compared:
the median in each tier, and the share of hit-flop (and hit-faded) pairs in which the hit has the higher value
(the AUC; 50% means no gap).
"""

from __future__ import annotations

import datetime as dt
import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Iterable

from .report import TAGS
from .store import Store

HIT, MID, FADED, FLOP, NEW = "hit", "middle", "faded", "flop", "new"
TIERS = (HIT, MID, FADED, FLOP, NEW)
HIT_AT = 1_000  # players online, or more
FLOP_BELOW = 20  # players online
FADED_VISITS = 10_000_000  # a quiet game with this many visits was big once: it faded, it did not flop
NEW_DAYS = 30  # a quiet game younger than this is "new": it has not had its chance yet
VERSUS = (FLOP, FADED)  # the hits are compared with these tiers


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    group: str  # size | response | timing | choice
    unit: str = ""  # "%", "R$", "d" (days), "" (a count), "yes" (a share of games)


FEATURES = [
    Feature("playing", "Players online", "size"),
    Feature("visits", "Visits, all time", "size"),
    Feature("favorites", "Favorites", "size"),
    Feature("badge_day", "Top badge, earned in the past day", "size"),
    Feature("like_share", "Like share", "response", "%"),
    Feature("fav_rate", "Favorites per 1,000 visits", "response"),
    Feature("age", "Game age", "timing", "d"),
    Feature("since_update", "Days since the last update", "timing", "d"),
    Feature("passes", "Game passes for sale", "choice"),
    Feature("pass_median", "Median pass price", "choice", "R$"),
    Feature("pass_max", "Top pass price", "choice", "R$"),
    Feature("badges", "Badges", "choice"),
    Feature("max_players", "Server size", "choice"),
    Feature("group", "Made by a group, not a user", "choice", "yes"),
    Feature("name_tag", "Update tag in the name, like [UPD 5]", "choice", "yes"),
]
GROUPS = {
    "size": "Size. These are results of success, so they separate the tiers by definition.",
    "response": "Player response, scaled to the game's size.",
    "timing": "Timing.",
    "choice": "Choices a developer makes. These are the real question.",
}


def days_between(day: str, iso: str | None) -> int | None:
    if not iso:
        return None
    return (dt.date.fromisoformat(day) - dt.date.fromisoformat(iso[:10])).days


def tier(playing: int | None, age: int | None, visits: int | None = None) -> str:
    players = playing or 0
    if players >= HIT_AT:
        return HIT
    if players >= FLOP_BELOW:
        return MID
    if age is not None and age < NEW_DAYS:
        return NEW
    if (visits or 0) >= FADED_VISITS:
        return FADED
    return FLOP


def mark_feature(name: str, title: str) -> Feature:
    """A yes/no number: is the game also in another list? For example: is this TD game an anime TD?"""
    return Feature(f"mark:{name}", f"In the {title.lower()} list", "choice", "yes")


def game_rows(
    store: Store, day: str, universe_ids: Iterable[int], marks: dict[str, set[int]] | None = None
) -> list[dict]:
    """One row of numbers per game on this day, most players first. `marks`: list name -> its universe ids."""
    ids = sorted(set(universe_ids))
    if not ids:
        return []
    slots = ",".join("?" * len(ids))
    cursor = store.db.execute(
        f"""SELECT g.universe_id, g.root_place_id, g.name, g.icon_url, g.creator_name, g.creator_type,
                   g.playing, g.visits, g.favorites, g.up_votes, g.down_votes, g.created, g.updated, g.max_players,
                   g.universe_id IN (SELECT universe_id FROM game_sources WHERE source LIKE 'place:%') AS own
            FROM game_daily g WHERE g.day = ? AND g.universe_id IN ({slots})
            ORDER BY g.playing DESC, g.universe_id""",
        [day, *ids],
    )
    names = [column[0] for column in cursor.description]
    games = [dict(zip(names, row)) for row in cursor.fetchall()]

    # Badges and passes as of each game's last check on or before the day (quiet games are checked weekly).
    last = (f"WITH last AS (SELECT universe_id, MAX(day) AS day FROM detail_checks WHERE day <= ? "
            f"AND universe_id IN ({slots}) GROUP BY universe_id) ")
    prices: dict[int, list[int]] = {uid: [] for uid in ids}
    for uid, price in store.db.execute(
        last + "SELECT p.universe_id, p.price FROM pass_daily p JOIN last ON p.universe_id = last.universe_id "
        "AND p.day = last.day WHERE p.for_sale = 1 AND p.price IS NOT NULL",
        [day, *ids],
    ):
        prices[uid].append(price)
    badges = {
        uid: (count, top_day)
        for uid, count, top_day in store.db.execute(
            last + "SELECT b.universe_id, SUM(b.enabled), MAX(b.awarded_past_day) FROM badge_daily b JOIN last "
            "ON b.universe_id = last.universe_id AND b.day = last.day GROUP BY b.universe_id",
            [day, *ids],
        )
    }

    rows = []
    for g in games:
        uid = g["universe_id"]
        votes = (g["up_votes"] or 0) + (g["down_votes"] or 0)
        passes = sorted(prices.get(uid, []))
        badge_count, badge_day = badges.get(uid, (0, None))
        age = days_between(day, g["created"])
        rows.append({
            **g,
            "like_share": 100 * (g["up_votes"] or 0) / votes if votes else None,
            "fav_rate": 1000 * (g["favorites"] or 0) / g["visits"] if g["visits"] else None,
            "age": age,
            "since_update": days_between(day, g["updated"]),
            "passes": len(passes),
            "pass_median": statistics.median(passes) if passes else None,
            "pass_max": passes[-1] if passes else None,
            "badges": badge_count or 0,
            "badge_day": badge_day,
            "group": int(g["creator_type"] == "Group"),
            "name_tag": int(bool(TAGS.search(g["name"] or ""))),
            **{f"mark:{name}": int(uid in members) for name, members in (marks or {}).items()},
            "tier": tier(g["playing"], age, g["visits"]),
        })
    return rows


def ranks(values: list[float]) -> list[float]:
    """Ranks from 1, with the average rank for ties."""
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start
        while end + 1 < len(order) and values[order[end + 1]] == values[order[start]]:
            end += 1
        for i in range(start, end + 1):
            result[order[i]] = (start + end) / 2 + 1
        start = end + 1
    return result


def auc(high: list[float], low: list[float]) -> float | None:
    """The share of (high, low) pairs where the `high` value is bigger. Ties count half."""
    if not high or not low:
        return None
    rank = ranks([*high, *low])
    rank_sum = sum(rank[: len(high)])
    return (rank_sum - len(high) * (len(high) + 1) / 2) / (len(high) * len(low))


def auc_error(a: float, n_high: int, n_low: int) -> float:
    """Standard error of an AUC (Hanley and McNeil, 1982)."""
    q1, q2 = a / (2 - a), 2 * a * a / (1 + a)
    variance = (a * (1 - a) + (n_high - 1) * (q1 - a * a) + (n_low - 1) * (q2 - a * a)) / (n_high * n_low)
    return math.sqrt(max(variance, 0.0))


@dataclass
class Gap:
    """How one number differs between the hits and another tier."""

    auc: float | None
    n_hit: int
    n_other: int
    clear: bool = False  # the 95% range of the AUC does not include 50%

    @property
    def words(self) -> str:
        if self.auc is None:
            return "too few games"
        share = max(self.auc, 1 - self.auc)
        side = "higher" if self.auc > 0.5 else "lower"
        if not self.clear:
            return f"no clear gap ({100 * share:.0f}%)"
        return f"hits {side} ({100 * share:.0f}%)"


def gap(hits: list[float], flops: list[float]) -> Gap:
    a = auc(hits, flops)
    if a is None:
        return Gap(None, len(hits), len(flops))
    error = auc_error(a, len(hits), len(flops))
    return Gap(a, len(hits), len(flops), clear=abs(a - 0.5) > 1.96 * error)


@dataclass
class Study:
    day: str
    rows: list[dict]
    features: list[Feature] = field(default_factory=lambda: list(FEATURES))
    medians: dict[str, dict[str, float | None]] = field(default_factory=dict)  # feature -> tier -> median
    gaps: dict[str, dict[str, Gap]] = field(default_factory=dict)  # feature -> FLOP or FADED -> hits vs that tier

    def tier_rows(self, name: str) -> list[dict]:
        return [row for row in self.rows if row["tier"] == name]

    def counts(self) -> dict[str, int]:
        return {name: len(self.tier_rows(name)) for name in TIERS}

    def top_share(self, top: int = 5) -> float | None:
        """The share of all players online in the list that the `top` biggest games hold."""
        players = sorted((row["playing"] or 0 for row in self.rows), reverse=True)
        total = sum(players)
        return sum(players[:top]) / total if total else None


def compare(day: str, rows: list[dict], extra: Iterable[Feature] = ()) -> Study:
    study = Study(day, rows, features=[*FEATURES, *extra])
    for feature in study.features:
        values: Callable[[str], list[float]] = lambda name, key=feature.key: [
            row[key] for row in study.tier_rows(name) if row.get(key) is not None
        ]
        if feature.unit == "yes":  # a share of games, not a median
            middle: Callable[[list[float]], float] = lambda v: 100 * sum(v) / len(v)  # noqa: E731
        else:
            middle = statistics.median
        study.medians[feature.key] = {name: (middle(values(name)) if values(name) else None) for name in TIERS}
        study.gaps[feature.key] = {other: gap(values(HIT), values(other)) for other in VERSUS}
    return study


def run_study(
    store: Store, day: str, universe_ids: Iterable[int], marks: dict[str, tuple[str, set[int]]] | None = None
) -> Study:
    """`marks`: list name -> (its title, its universe ids). Each one adds a yes/no row to the comparison."""
    marks = marks or {}
    rows = game_rows(store, day, universe_ids, {name: ids for name, (_, ids) in marks.items()})
    return compare(day, rows, [mark_feature(name, title) for name, (title, _) in marks.items()])


TIER_WORDS = {
    HIT: f"{HIT_AT:,}+ players online",
    MID: f"{FLOP_BELOW}-{HIT_AT - 1:,} players online",
    FADED: f"under {FLOP_BELOW} online now, but {FADED_VISITS // 1_000_000}M+ visits: big once",
    FLOP: f"under {FLOP_BELOW} online, under {FADED_VISITS // 1_000_000}M visits, {NEW_DAYS}+ days old",
    NEW: f"under {FLOP_BELOW} online, under {NEW_DAYS} days old",
}
TIER_NAMES = {HIT: "Hit", MID: "Middle", FADED: "Faded", FLOP: "Flop", NEW: "New"}

ONE_DAY_CAN = [
    "Which games are big today, and how big the gaps between them are.",
    "How today's hits differ from today's flops in the numbers that anyone can see from outside the game.",
    "What a typical hit looks like today: its passes, prices, badges and update habits.",
]
ONE_DAY_CANT = [
    "Cause and effect. A hit can have more passes because it is a hit, not the other way around.",
    "Trends. Growth, decline, retention and the effect of an update need many days of snapshots.",
    "Peaks. Players online is one moment. It changes with the hour, the day of the week and update days.",
    "Launch odds. A forecast needs games that we saw at launch and then followed for 30 days (M3).",
    "The whole market. Search shows the games that Roblox ranks, and it favors games that were big once. Games "
    "that never took off are mostly missing, so the flop group is small and not complete.",
    "Thumbnails, YouTubers, ads, trends and luck. These are not in the data yet.",
]


def fmt(feature: Feature, value: float | None) -> str:
    from .report import human

    if value is None:
        return "-"
    if feature.unit in ("%", "yes"):
        return f"{value:.0f}%"
    if feature.unit == "d":
        return f"{value:.0f}d"
    if feature.unit == "R$":
        return f"R${human(round(value))}"
    if abs(value) < 10 and value != int(value):
        return f"{value:.1f}"
    return human(round(value))


def format_study(study: Study, title: str, list_note: str) -> str:
    counts = study.counts()
    lines = [
        f"{title}, day {study.day} (UTC). {len(study.rows)} games in the list. {list_note}",
        "",
        "Tiers (players online at the moment of the snapshot, and visits of all time):",
        *(f"  {TIER_NAMES[name]:<7} {TIER_WORDS[name]:<56} {counts[name]:>4} games" for name in TIERS),
    ]
    share = study.top_share()
    if share is not None:
        lines.append(f"The 5 biggest games hold {100 * share:.0f}% of all players online in the list.")
    lines += [
        "",
        "Medians by tier. The last two columns: pick one hit and one flop (or one faded game) at random.",
        "The % says how often the hit has the higher value, or the lower one. 50% means no gap.",
    ]
    head = ["", *(TIER_NAMES[name] for name in TIERS), "Hit vs flop", "Hit vs faded"]
    rows: list[list[str] | str] = []
    for group, note in GROUPS.items():
        rows.append(note)
        for feature in (f for f in study.features if f.group == group):
            medians = study.medians[feature.key]
            rows.append([
                f"  {feature.label}",
                *(fmt(feature, medians[name]) for name in TIERS),
                *(study.gaps[feature.key][other].words for other in VERSUS),
            ])
    table = [head, *(row for row in rows if isinstance(row, list))]
    widths = [max(len(row[i]) for row in table) for i in range(len(head))]
    for row in [head, *rows]:
        if isinstance(row, str):
            lines.append(row)
            continue
        cells = [row[0].ljust(widths[0]), *(c.rjust(w) for c, w in zip(row[1:-2], widths[1:-2]))]
        lines.append("  ".join([*cells, *(c.ljust(w) for c, w in zip(row[-2:], widths[-2:]))]).rstrip())
    lines += [
        "",
        f"\"No clear gap\" means the gap could be luck with this few games ({counts[HIT]} hits, "
        f"{counts[FLOP]} flops, {counts[FADED]} faded). New games stay out of both columns.",
        "",
        "What one day of data can show:",
        *(f"  - {line}" for line in ONE_DAY_CAN),
        "What one day of data can't show:",
        *(f"  - {line}" for line in ONE_DAY_CANT),
    ]
    return "\n".join(lines)
