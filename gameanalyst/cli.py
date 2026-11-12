"""Command line: `collect`, `show`, `list` (a genre list and its checks), `study` (hits vs flops)."""

from __future__ import annotations

import argparse
import sys
import tomllib
import traceback
from pathlib import Path

from .collect import Plan, backfill_text, collect_day, stamp, utc_now
from .http import Http
from .lists import IN, Rules, build, list_path, members
from .report import format_review, format_table, latest_day, list_note, table_rows
from .roblox import Roblox
from .store import RawArchive, Store
from .study import format_study, run_study
from .study_page import study_page


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
    show.add_argument("--list", dest="list_name", help="only games in this genre list, e.g. anime-td")
    show.add_argument("--top", type=int, default=20)

    lists = commands.add_parser("list", help="a genre list: which games are in, which need a check, and why")
    lists.add_argument("name", nargs="?", default="anime-td", help="the list (default: anime-td)")
    lists.add_argument("--day", help="YYYY-MM-DD (default: the latest day)")
    lists.add_argument("--all", action="store_true", help="also print the games in the list and the ones left out")

    study = commands.add_parser("study", help="hits vs flops in a genre list, on one day")
    study.add_argument("name", nargs="?", default="anime-td", help="the list (default: anime-td)")
    study.add_argument("--day", help="YYYY-MM-DD (default: the latest day)")
    study.add_argument("--html", help="also write the report as a web page to this file")
    study.add_argument("--mark", action="append", default=[], metavar="LIST",
                       help="add a yes/no row: is the game also in this list? (repeatable)")

    parser.add_argument("--lists", default="lists", help="folder of genre lists (default: lists)")
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
        if args.command == "list":
            return run_list(args, store)
        if args.command == "study":
            return run_study_command(args, store)
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
        f"{result.skipped} already saved today, {result.quiet} quiet (badges and passes not due), "
        f"{len(result.errors)} errors, {rbx.http.requests_made} requests",
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
    ids = None
    if args.list_name:
        rules = load_rules(args)
        if rules is None:
            return 1
        ids = members(store, rules, day)
    rows = table_rows(store, day, query=args.query, chart=args.chart, own=args.own, top=args.top, ids=ids)
    print(format_table(rows, day))
    return 0


def load_rules(args: argparse.Namespace) -> Rules | None:
    name = getattr(args, "list_name", None) or args.name
    path = list_path(args.lists, name)
    if not path.exists():
        print(f"No list called {name}: {path} does not exist.")
        return None
    return Rules.load(path)


def rules_and_day(args: argparse.Namespace, store: Store) -> tuple[Rules, str] | None:
    rules = load_rules(args)
    if rules is None:
        return None
    day = args.day or latest_day(store)
    if not day:
        print("No data yet. Run: python -m gameanalyst collect")
        return None
    return rules, day


def run_list(args: argparse.Namespace, store: Store) -> int:
    found = rules_and_day(args, store)
    if found is None:
        return 1
    rules, day = found
    print(format_review(build(store, rules, day), rules, day, list_path(args.lists, rules.name), show_all=args.all))
    return 0


def run_study_command(args: argparse.Namespace, store: Store) -> int:
    found = rules_and_day(args, store)
    if found is None:
        return 1
    rules, day = found
    decisions = build(store, rules, day)
    ids = {game["universe_id"] for game, decision in decisions if decision.verdict == IN}
    marks = {}
    for name in args.mark:
        path = list_path(args.lists, name)
        if not path.exists():
            print(f"No list called {name}: {path} does not exist.")
            return 1
        other = Rules.load(path)
        marks[name] = (other.title, members(store, other, day))
    result = run_study(store, day, ids, marks)
    print(format_study(result, rules.title, list_note(decisions)))
    if args.html:
        path = Path(args.html)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(study_page(result, rules, decisions), encoding="utf-8", newline="\n")
        print(f"\nWrote {path}")
    return 0
