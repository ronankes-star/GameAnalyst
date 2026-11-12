"""Command line: `python -m gameanalyst collect` and `python -m gameanalyst show`."""

from __future__ import annotations

import argparse
import sys
import tomllib
import traceback
from pathlib import Path

from .collect import Plan, backfill_text, collect_day, stamp, utc_now
from .http import Http
from .report import format_table, latest_day, table_rows
from .roblox import Roblox
from .store import RawArchive, Store


def load_watch(path: str | Path) -> dict:
    file = Path(path)
    return tomllib.loads(file.read_text(encoding="utf-8")) if file.exists() else {}


def log_line(data: Path, text: str) -> None:
    """Append to data/logs/collect.log. The scheduled run has no console, so this file is its only output."""
    logs = Path(data) / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    with open(logs / "collect.log", "a", encoding="utf-8") as log:
        log.write(text.rstrip("\n") + "\n")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError, OSError):
        pass  # no console (pythonw), or a stream that can't change
    parser = argparse.ArgumentParser(prog="gameanalyst", description="Daily public data on Roblox games.")
    parser.add_argument("--data", default="data", help="data folder (default: data)")
    commands = parser.add_subparsers(dest="command", required=True)

    collect = commands.add_parser("collect", help="save today's snapshot of every tracked game")
    collect.add_argument("--watch", default="watch.toml", help="search terms and own places (default: watch.toml)")
    collect.add_argument("--limit", type=int, help="save at most N games (for a quick test)")
    collect.add_argument("--no-charts", action="store_true", help="skip the Charts page")
    collect.add_argument("--no-search", action="store_true", help="skip the search terms")

    commands.add_parser("backfill-text", help="fill the descriptions table from the raw archive (safe to repeat)")

    show = commands.add_parser("show", help="print one day's numbers")
    show.add_argument("--day", help="YYYY-MM-DD (default: the latest day)")
    show.add_argument("--query", help="only games from this search term")
    show.add_argument("--chart", help="only games from this chart, e.g. top-trending")
    show.add_argument("--own", action="store_true", help="only your own games (the places in watch.toml)")
    show.add_argument("--top", type=int, default=20)

    args = parser.parse_args(argv)
    data = Path(args.data)
    store = Store(data / "gameanalyst.sqlite")
    try:
        if args.command == "collect":
            try:
                return run_collect(args, store, data)
            except Exception:
                log_line(data, f"{stamp()} run failed:\n{traceback.format_exc()}")
                raise
        if args.command == "backfill-text":
            print(f"Saved {backfill_text(store, data / 'raw')} descriptions from {data / 'raw'}.")
            return 0
        return run_show(args, store)
    finally:
        store.close()


def run_collect(args: argparse.Namespace, store: Store, data: Path) -> int:
    watch = load_watch(args.watch)
    search = watch.get("search", {})
    more_pages = {str(term): int(pages) for term, pages in search.get("more_pages", {}).items()}
    queries = list(dict.fromkeys([*search.get("queries", []), *more_pages]))
    plan = Plan(
        queries=[] if args.no_search else queries,
        search_pages=int(search.get("pages", 2)),
        query_pages=more_pages,
        place_ids=list(watch.get("places", {}).get("own", [])),
        use_charts=not args.no_charts,
        limit=args.limit,
    )
    rbx = Roblox(Http())
    day = utc_now().date().isoformat()
    raw = RawArchive(data / "raw", day)

    def progress(done: int, total: int) -> None:
        if done % 25 == 0 or done == total:
            print(f"  saved {done}/{total} games", flush=True)

    try:
        result = collect_day(rbx, store, raw, plan, day, progress)
    finally:
        raw.close()
    lines = [
        f"{stamp()} {result.day}: saved {result.collected} games, found {result.discovered} new, "
        f"{result.skipped} already saved today, {len(result.errors)} errors, {rbx.http.requests_made} requests",
        *(f"  error: {error}" for error in result.errors[:10]),
    ]
    for line in lines:
        print(line)
        log_line(data, line)
    return 0


def run_show(args: argparse.Namespace, store: Store) -> int:
    day = args.day or latest_day(store)
    if not day:
        print("No data yet. Run: python -m gameanalyst collect")
        return 1
    rows = table_rows(store, day, query=args.query, chart=args.chart, own=args.own, top=args.top)
    print(format_table(rows, day))
    return 0
