from pathlib import Path

import pytest

from gameanalyst.lists import Rules, build
from gameanalyst.store import Store
from gameanalyst.study import (
    FADED, FLOP, HIT, MID, NEW, auc, compare, format_study, game_rows, gap, ranks, run_study, tier,
)
from gameanalyst.study_page import study_page

DAY = "2026-11-12"
RULES = Rules.load(Path(__file__).parent.parent / "lists" / "anime-td.toml")


def add_game(store, uid, playing, *, created="2025-11-12", updated="2026-11-10", passes=(), badges=(), name=None,
             visits=None):
    """One saved game on DAY, with its passes (prices) and badges (past-day award counts)."""
    store.add("game_daily", [{
        "day": DAY, "universe_id": uid, "root_place_id": uid * 10, "name": name or f"Anime Game {uid}",
        "creator_type": "Group", "creator_id": 1, "creator_name": "Studio", "creator_verified": 0,
        "playing": playing, "visits": playing * 1000 if visits is None else visits, "favorites": playing * 10, "up_votes": 90, "down_votes": 10,
        "created": created, "updated": updated, "genre_l1": "Strategy", "genre_l2": "Tower Defense",
        "max_players": 4, "price": None, "icon_url": None, "collected_at": DAY,
    }])
    store.add("pass_daily", [{"day": DAY, "universe_id": uid, "pass_id": uid * 100 + n, "name": "pass", "price": p,
                              "for_sale": 1} for n, p in enumerate(passes)])
    store.add("badge_daily", [{"day": DAY, "universe_id": uid, "badge_id": uid * 100 + n, "name": "badge",
                               "enabled": 1, "created": DAY, "awarded_past_day": a, "awarded_total": a * 10}
                              for n, a in enumerate(badges)])
    store.mark_details(DAY, uid)


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "db.sqlite")
    add_game(store, 1, 50_000, passes=(99, 199, 499), badges=(9000, 4000), updated="2026-11-11")
    add_game(store, 2, 2_000, passes=(99, 299), badges=(800,), updated="2026-11-09")
    add_game(store, 3, 300, passes=(49,), badges=(30,))
    add_game(store, 4, 5, passes=(25,), updated="2026-06-01")
    add_game(store, 5, 0, updated="2026-01-01")
    add_game(store, 6, 2, created="2026-11-01", updated="2026-11-01")  # 11 days old: new, not a flop yet
    add_game(store, 7, 9, visits=50_000_000, updated="2025-12-01")  # quiet now, but big once: faded
    store.commit()
    return store


def test_ranks_share_ties():
    assert ranks([10, 20, 20, 5]) == [2, 3.5, 3.5, 1]


def test_auc_is_the_share_of_pairs_the_first_group_wins():
    assert auc([3, 4], [1, 2]) == 1.0
    assert auc([1, 2], [3, 4]) == 0.0
    assert auc([1, 3], [2, 2]) == 0.5
    assert auc([], [1]) is None


def test_a_small_gap_with_few_games_is_not_called_clear():
    assert not gap([2, 3], [1, 2.5]).clear
    assert gap(list(range(20, 40)), list(range(0, 20))).clear
    assert gap([], [1]).words == "too few games"


def test_tiers_follow_players_online_visits_and_age():
    assert tier(1_000, 400) == HIT
    assert tier(20, 400) == MID
    assert tier(19, 400, 9_999_999) == FLOP
    assert tier(19, 400, 10_000_000) == FADED
    assert tier(0, 10, 50_000_000) == NEW
    assert tier(None, None) == FLOP


def test_each_game_gets_its_numbers(store):
    rows = {row["universe_id"]: row for row in game_rows(store, DAY, [1, 2, 3, 4, 5, 6])}
    hit = rows[1]
    assert (hit["tier"], hit["passes"], hit["pass_median"], hit["pass_max"]) == (HIT, 3, 199, 499)
    assert (hit["badges"], hit["badge_day"], hit["since_update"], hit["age"]) == (2, 9000, 1, 365)
    assert (hit["like_share"], hit["fav_rate"]) == (90.0, 10.0)
    assert (rows[5]["passes"], rows[5]["pass_median"], rows[5]["badge_day"]) == (0, None, None)
    assert rows[6]["tier"] == NEW


def test_the_comparison_shows_medians_and_gaps(store):
    study = run_study(store, DAY, [1, 2, 3, 4, 5, 6, 7])
    assert study.counts() == {HIT: 2, MID: 1, FADED: 1, FLOP: 2, NEW: 1}
    assert study.medians["passes"][HIT] == 2.5 and study.medians["passes"][FLOP] == 0.5
    assert study.gaps["passes"][FLOP].auc == 1.0  # every hit has more passes than every flop
    assert study.gaps["since_update"][FADED].auc == 0.0  # every hit updated more recently than the faded game
    assert study.top_share(1) == pytest.approx(50_000 / 52_316)
    text = format_study(study, "Anime tower defense", "Every game is decided.")
    assert "Game passes for sale" in text and "Hit vs faded" in text and "can't show" in text


def test_a_mark_adds_a_yes_no_row_from_another_list(store):
    study = run_study(store, DAY, [1, 2, 3, 4, 5, 6, 7], marks={"anime-td": ("Anime tower defense", {1, 4})})
    assert study.features[-1].label == "In the anime tower defense list"
    assert study.medians["mark:anime-td"][HIT] == 50.0 and study.medians["mark:anime-td"][FLOP] == 50.0


def test_an_empty_list_does_not_break_the_study(store):
    study = run_study(store, DAY, [])
    assert study.counts() == {HIT: 0, MID: 0, FADED: 0, FLOP: 0, NEW: 0}
    assert study.gaps["passes"][FLOP].words == "too few games"
    assert "0 games in the list" in format_study(study, "Anime tower defense", "")


def test_the_web_page_holds_the_comparison_and_the_list(store):
    add_game(store, 7, 3, name="<script>alert(1)</script> Toilet TD")
    study = compare(DAY, game_rows(store, DAY, [1, 2, 3, 4, 5, 6]))
    page = study_page(study, RULES, build(store, RULES, DAY))
    assert page.startswith("<!doctype html>") and "</html>" in page
    assert "What separates the hits from the flops" in page and "Game passes for sale" in page
    assert "<script>alert(1)" not in page  # names are escaped
    assert page.count('class="dot') >= 6
