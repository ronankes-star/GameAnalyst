from tests.fakes import A, B, C, DAY, FakeRoblox, run_fake_day


def count(store, table):
    return store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_a_day_is_saved(tmp_path):
    result, store = run_fake_day(tmp_path)
    assert (result.collected, result.discovered, result.errors) == (3, 3, [])
    assert count(store, "game_daily") == 3
    assert count(store, "badge_daily") == 9  # 3 badges for each of 3 games
    assert count(store, "pass_daily") == 3
    assert count(store, "chart_daily") == 2
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
