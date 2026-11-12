from gameanalyst.collect import Plan, backfill_text, collect_day
from gameanalyst.report import table_rows
from gameanalyst.store import RawArchive, Store
from gameanalyst.study import game_rows
from tests.fakes import A, B, C, DAY, PLACE_OF_C, FakeRoblox, fake_roblox, run_fake_day


def count(store, table):
    return store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_a_day_is_saved(tmp_path):
    result, store = run_fake_day(tmp_path)
    assert (result.collected, result.discovered, result.errors) == (3, 3, [])
    assert count(store, "game_daily") == 3
    assert count(store, "badge_daily") == 9  # 3 badges for each of 3 games
    assert count(store, "pass_daily") == 3
    assert count(store, "chart_daily") == 3  # two games in top-playing-now, one in top-earning
    assert count(store, "search_daily") == 2
    assert count(store, "runs") == 1
    sources = dict(store.db.execute("SELECT universe_id, source FROM tracked_games"))
    assert sources == {A: "chart:top-playing-now", B: "chart:top-playing-now", C: "search:anime td"}
    for kind in ("charts", "search", "games", "badges", "passes"):
        assert (tmp_path / "raw" / DAY / f"{kind}.jsonl.gz").exists()


def test_badge_award_counts_are_kept(tmp_path):
    _, store = run_fake_day(tmp_path)
    rows = store.db.execute(
        "SELECT name, awarded_past_day, awarded_total FROM badge_daily WHERE universe_id = ? ORDER BY badge_id", (A,)
    ).fetchall()
    assert rows == [("Badge 1", 10, 100), ("Badge 2", 20, 200), ("Badge 3", 30, 300)]


def test_a_second_run_on_the_same_day_changes_nothing(tmp_path):
    _, first = run_fake_day(tmp_path)
    before = first.db.execute("SELECT * FROM game_daily ORDER BY universe_id").fetchall()
    first.close()
    result, second = run_fake_day(tmp_path)
    assert (result.collected, result.skipped) == (0, 3)
    assert second.db.execute("SELECT * FROM game_daily ORDER BY universe_id").fetchall() == before


def test_limit_caps_the_run(tmp_path):
    result, store = run_fake_day(tmp_path, limit=2)
    assert result.collected == 2
    assert count(store, "game_daily") == 2


def test_one_broken_game_does_not_stop_the_run(tmp_path):
    result, store = run_fake_day(tmp_path, fake=FakeRoblox(missing=(f"/universes/{C}/badges",)))
    assert result.collected == 3
    assert len(result.errors) == 1 and str(C) in result.errors[0]
    assert count(store, "badge_daily") == 6


def test_rate_limits_are_waited_out(tmp_path):
    result, _ = run_fake_day(tmp_path, fake=FakeRoblox(throttle_429={"/game-passes": 2}))
    assert result.collected == 3 and result.errors == []


def test_descriptions_are_saved_with_the_games(tmp_path):
    _, store = run_fake_day(tmp_path)
    texts = store.texts(DAY)
    assert texts[A].startswith("Summon units") and texts[C] == ""


def test_a_term_can_get_its_own_page_count(tmp_path):
    fake = FakeRoblox()
    run_fake_day(tmp_path, fake=fake, search_pages=2, query_pages={"anime td": 1})
    assert sum("/omni-search" in url for url in fake.urls) == 1


def test_backfill_fills_descriptions_from_the_raw_archive(tmp_path):
    _, store = run_fake_day(tmp_path)
    store.db.execute("DELETE FROM game_text")
    assert backfill_text(store, tmp_path / "raw") == 3
    assert backfill_text(store, tmp_path / "raw") == 0  # safe to run again
    assert store.texts(DAY)[B].startswith("Place cameramen")


def collect_on(tmp_path, store, rbx, day, **plan):
    raw = RawArchive(tmp_path / "raw", day)
    try:
        return collect_day(rbx, store, raw, Plan(queries=["anime td"], place_ids=[PLACE_OF_C], **plan), day)
    finally:
        raw.close()


def test_quiet_games_get_badges_and_passes_once_a_week(tmp_path):
    rbx, _ = fake_roblox()
    store = Store(tmp_path / "db.sqlite")
    # A has 1 player online: quiet. B (2) and C (3) are busy enough at quiet_below=2.
    assert collect_on(tmp_path, store, rbx, "2026-11-12", quiet_below=2).quiet == 0  # never checked: check all
    assert collect_on(tmp_path, store, rbx, "2026-11-13", quiet_below=2).quiet == 1  # A was checked yesterday
    assert collect_on(tmp_path, store, rbx, "2026-11-19", quiet_below=2).quiet == 0  # a week later: check A again
    checks = store.db.execute("SELECT day FROM detail_checks WHERE universe_id = ? ORDER BY day", (A,)).fetchall()
    assert checks == [("2026-11-12",), ("2026-11-19",)]


def test_on_a_day_without_a_check_the_last_check_counts(tmp_path):
    rbx, _ = fake_roblox()
    store = Store(tmp_path / "db.sqlite")
    collect_on(tmp_path, store, rbx, "2026-11-12")
    collect_on(tmp_path, store, rbx, "2026-11-13")  # every fake game is quiet: no badges or passes saved today
    assert store.db.execute("SELECT COUNT(*) FROM pass_daily WHERE day = '2026-11-13'").fetchone()[0] == 0
    row = game_rows(store, "2026-11-13", [A])[0]
    assert (row["passes"], row["badges"]) == (1, 3)
    shown = {r["universe_id"]: (r["passes"], r["badges"]) for r in table_rows(store, "2026-11-13")}
    assert shown[A] == (1, 3)


def test_an_older_file_counts_every_saved_game_as_checked(tmp_path):
    _, store = run_fake_day(tmp_path)
    store.db.execute("DELETE FROM detail_checks")
    store.commit()
    store.close()
    store = Store(tmp_path / "db.sqlite")
    assert store.db.execute("SELECT COUNT(*) FROM detail_checks").fetchone()[0] == 3

