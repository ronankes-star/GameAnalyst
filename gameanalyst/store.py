"""The SQLite store and the raw archive.

Every table is keyed by day, and rows are only ever added. A past day never changes. A second run on the same
day keeps the first values (INSERT OR IGNORE).
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import TextIO

TABLES = (
    "tracked_games", "game_sources", "game_daily", "badge_daily", "pass_daily", "chart_daily", "search_daily", "runs",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracked_games (
    universe_id INTEGER PRIMARY KEY,
    first_seen  TEXT NOT NULL,
    source      TEXT NOT NULL  -- how the game was first found: chart:<sort>, search:<query>, place:<id>
);
CREATE TABLE IF NOT EXISTS game_sources (  -- every way a game was found, not only the first one
    universe_id INTEGER NOT NULL, source TEXT NOT NULL, first_seen TEXT NOT NULL,
    PRIMARY KEY (universe_id, source)
);
INSERT OR IGNORE INTO game_sources SELECT universe_id, source, first_seen FROM tracked_games;
CREATE TABLE IF NOT EXISTS game_daily (
    day TEXT NOT NULL, universe_id INTEGER NOT NULL,
    root_place_id INTEGER, name TEXT,
    creator_type TEXT, creator_id INTEGER, creator_name TEXT, creator_verified INTEGER,
    playing INTEGER, visits INTEGER, favorites INTEGER, up_votes INTEGER, down_votes INTEGER,
    created TEXT, updated TEXT, genre_l1 TEXT, genre_l2 TEXT, max_players INTEGER, price INTEGER,
    icon_url TEXT, collected_at TEXT NOT NULL,
    PRIMARY KEY (day, universe_id)
);
CREATE TABLE IF NOT EXISTS badge_daily (
    day TEXT NOT NULL, universe_id INTEGER NOT NULL, badge_id INTEGER NOT NULL,
    name TEXT, enabled INTEGER, created TEXT, awarded_past_day INTEGER, awarded_total INTEGER,
    PRIMARY KEY (day, badge_id)
);
CREATE TABLE IF NOT EXISTS pass_daily (
    day TEXT NOT NULL, universe_id INTEGER NOT NULL, pass_id INTEGER NOT NULL,
    name TEXT, price INTEGER, for_sale INTEGER,
    PRIMARY KEY (day, pass_id)
);
CREATE TABLE IF NOT EXISTS chart_daily (
    day TEXT NOT NULL, sort_id TEXT NOT NULL, rank INTEGER NOT NULL,
    universe_id INTEGER NOT NULL, player_count INTEGER, is_sponsored INTEGER,
    PRIMARY KEY (day, sort_id, rank)
);
CREATE TABLE IF NOT EXISTS search_daily (
    day TEXT NOT NULL, query TEXT NOT NULL, rank INTEGER NOT NULL,
    universe_id INTEGER NOT NULL, player_count INTEGER, is_sponsored INTEGER,
    PRIMARY KEY (day, query, rank)
);
CREATE TABLE IF NOT EXISTS runs (
    started_at TEXT NOT NULL, finished_at TEXT, day TEXT NOT NULL,
    games INTEGER, requests INTEGER, errors INTEGER, error_log TEXT
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def commit(self) -> None:
        self.db.commit()

    def track(self, universe_id: int, day: str, source: str) -> bool:
        """Start to track a game, and remember this source for it. Returns True when the game is new."""
        self.db.execute("INSERT OR IGNORE INTO game_sources VALUES (?, ?, ?)", (universe_id, source, day))
        cursor = self.db.execute("INSERT OR IGNORE INTO tracked_games VALUES (?, ?, ?)", (universe_id, day, source))
        return cursor.rowcount == 1

    def tracked(self) -> list[int]:
        return [row[0] for row in self.db.execute("SELECT universe_id FROM tracked_games ORDER BY first_seen, rowid")]

    def has_game_day(self, day: str, universe_id: int) -> bool:
        query = "SELECT 1 FROM game_daily WHERE day = ? AND universe_id = ?"
        return self.db.execute(query, (day, universe_id)).fetchone() is not None

    def add(self, table: str, rows: list[dict]) -> int:
        """Insert the rows that are not there yet. Returns how many were added."""
        if table not in TABLES:
            raise ValueError(f"unknown table: {table}")
        if not rows:
            return 0
        columns = list(rows[0])
        sql = (
            f"INSERT OR IGNORE INTO {table} ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' * len(columns))})"
        )
        before = self.db.total_changes
        self.db.executemany(sql, [tuple(row[c] for c in columns) for row in rows])
        return self.db.total_changes - before

    def log_run(self, started: str, finished: str, day: str, games: int, requests: int, errors: list[str]) -> None:
        self.db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?)",
            (started, finished, day, games, requests, len(errors), "\n".join(errors[:50])),
        )
        self.db.commit()


class RawArchive:
    """Every raw response of a day, as gzipped JSON lines: <root>/<day>/<kind>.jsonl.gz.

    The tables keep only the fields in use today. The archive keeps everything, so later features can be
    built from old days.
    """

    def __init__(self, root: str | Path, day: str):
        self.dir = Path(root) / day
        self._files: dict[str, TextIO] = {}

    def write(self, kind: str, key: object, payload: object) -> None:
        handle = self._files.get(kind)
        if handle is None:
            self.dir.mkdir(parents=True, exist_ok=True)
            handle = gzip.open(self.dir / f"{kind}.jsonl.gz", "at", encoding="utf-8")
            self._files[kind] = handle
        handle.write(json.dumps({"key": key, "data": payload}, separators=(",", ":")) + "\n")

    def close(self) -> None:
        for handle in self._files.values():
            handle.close()
        self._files.clear()
