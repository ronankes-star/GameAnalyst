import sqlite3

from gameanalyst.store import RawArchive, Store


def test_a_description_is_saved_only_when_it_changes(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    assert store.save_text("2026-11-12", 1, "Defend the base!")
    assert not store.save_text("2026-11-13", 1, "Defend the base!")
    assert store.save_text("2026-11-14", 1, "Now with raids!")
    assert store.save_text("2026-11-15", 1, "Defend the base!")  # changed back: that is a change too
    assert store.db.execute("SELECT COUNT(*) FROM game_text").fetchone()[0] == 3


def test_texts_gives_each_game_its_description_on_that_day(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    store.save_text("2026-11-12", 1, "old")
    store.save_text("2026-11-14", 1, "new")
    store.save_text("2026-11-12", 2, None)
    assert store.texts("2026-11-13") == {1: "old", 2: ""}
    assert store.texts("2026-11-14") == {1: "new", 2: ""}
    assert store.texts("2026-11-11") == {}


def test_people_can_read_while_the_daily_run_writes(tmp_path):
    writer = Store(tmp_path / "db.sqlite")
    writer.track(1, "2026-11-12", "search:td")  # a write that is not committed yet
    reader = Store(tmp_path / "db.sqlite", timeout=0.5)  # must not wait for the writer
    assert reader.tracked() == []
    writer.commit()
    assert reader.tracked() == [1]


def test_an_old_file_gets_its_game_sources_filled(tmp_path):
    old = sqlite3.connect(tmp_path / "db.sqlite")  # a file from before game_sources existed
    old.execute("CREATE TABLE tracked_games (universe_id INTEGER PRIMARY KEY, first_seen TEXT, source TEXT)")
    old.execute("INSERT INTO tracked_games VALUES (5, '2026-11-12', 'chart:top-trending')")
    old.commit()
    old.close()
    store = Store(tmp_path / "db.sqlite")
    assert store.db.execute("SELECT * FROM game_sources").fetchall() == [(5, "chart:top-trending", "2026-11-12")]


def test_the_raw_archive_reads_back_what_it_wrote(tmp_path):
    raw = RawArchive(tmp_path, "2026-11-12")
    raw.write("games", 7, {"game": {"description": "hi"}})
    raw.write("games", 8, {"game": {}})
    raw.close()
    assert RawArchive.days(tmp_path) == ["2026-11-12"]
    assert list(RawArchive.read(tmp_path, "2026-11-12", "games")) == [(7, {"game": {"description": "hi"}}), (8, {"game": {}})]
    assert list(RawArchive.read(tmp_path, "2026-11-12", "badges")) == []
    assert RawArchive.days(tmp_path / "missing") == []
