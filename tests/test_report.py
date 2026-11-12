from gameanalyst.report import display_name, format_table, human, like_share, table_rows
from tests.fakes import B, C, DAY, run_fake_day


def test_display_name_drops_update_tags_and_emoji():
    assert display_name("[☀️UPD 21🏖️] Anime Adventures") == "Anime Adventures"
    assert display_name("A" * 40, width=10) == "AAAAAAAAA…"


def test_numbers_are_short():
    assert human(45_395_632_108) == "45.4B"
    assert human(1_500) == "1.5K"
    assert human(12) == "12"
    assert human(None) == "-"


def test_like_share():
    assert like_share(90, 10) == "90%"
    assert like_share(0, 0) == "-"


def test_own_games_count_even_when_a_search_found_them_first(tmp_path):
    _, store = run_fake_day(tmp_path)  # C is found by search first, then by its place id
    assert [row["universe_id"] for row in table_rows(store, DAY, own=True)] == [C]


def test_a_search_table_lists_most_players_first(tmp_path):
    _, store = run_fake_day(tmp_path)
    rows = table_rows(store, DAY, query="anime td")
    assert [row["universe_id"] for row in rows] == [C, B]
    assert (rows[0]["passes"], rows[0]["badges"]) == (1, 3)
    text = format_table(rows, DAY)
    assert "Game 1003" in text and "90%" in text and "2d ago" in text
