from tests.fakes import A, B, C, PLACE_OF_C, fake_roblox


def test_games_are_asked_for_50_at_a_time():
    rbx, fake = fake_roblox()
    ids = list(range(2000, 2120))
    assert [row["id"] for row in rbx.games(ids)] == ids
    assert sum("games.roblox.com/v1/games?" in url for url in fake.urls) == 3


def test_votes_and_icons_take_100_per_call():
    rbx, fake = fake_roblox()
    rbx.votes(range(2000, 2150))
    rbx.icons(range(2000, 2150))
    assert sum("/v1/games/votes?" in url for url in fake.urls) == 2
    assert sum("/v1/games/icons?" in url for url in fake.urls) == 2


def test_badges_follow_the_page_cursor():
    rbx, _ = fake_roblox()
    assert [b["name"] for b in rbx.badges(A)] == ["Badge 1", "Badge 2", "Badge 3"]


def test_search_keeps_the_rank_order_and_skips_non_games():
    rbx, _ = fake_roblox()
    assert [hit["universeId"] for hit in rbx.search("anime td", pages=3)] == [B, C]


def test_search_stops_at_the_page_limit():
    rbx, _ = fake_roblox()
    assert [hit["universeId"] for hit in rbx.search("anime td", pages=1)] == [B]


def test_charts_skip_rows_that_are_not_games():
    rbx, _ = fake_roblox()
    assert list(rbx.charts()) == ["top-playing-now", "top-earning"]


def test_charts_follow_the_pages_of_charts():
    rbx, fake = fake_roblox()
    assert [g["universeId"] for g in rbx.charts()["top-earning"]] == [A]
    assert sum("/get-sorts" in url for url in fake.urls) == 2 and "sortsPageToken=s2" in fake.urls[-1]
    assert list(rbx.charts(max_pages=1)) == ["top-playing-now"]


def test_a_place_id_turns_into_its_universe_id():
    rbx, _ = fake_roblox()
    assert rbx.universe_for_place(PLACE_OF_C) == C
