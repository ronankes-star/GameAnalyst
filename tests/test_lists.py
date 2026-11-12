from pathlib import Path

import pytest

from gameanalyst.lists import CHECK, IN, OUT, Rules, Words, build, decide, members, normalize
from tests.fakes import A, B, C, DAY, run_fake_day

RULES = Rules.load(Path(__file__).parent.parent / "lists" / "anime-td.toml")


def verdict(name, genre="Tower Defense", description="", own=False, rules=RULES):
    return decide(rules, {"universe_id": 1, "name": name, "genre_l2": genre}, description, own=own)


def test_normalize_keeps_words_only():
    assert normalize("[🎃UPD] AnimeReversal: Re:Zero's") == "upd anime reversal re zeros"


def test_words_match_whole_words_and_the_longest_phrase():
    words = Words(["anime", "one punch", "one punch man", "アニメ"])
    assert words.count("animatronic friends") == {}
    assert words.count("one punch man td") == {"one punch man": 1}
    assert words.count(normalize("最強アニメタワー")) == {"アニメ": 1}


# Real names and descriptions from the first day of data (2026-11-12).
@pytest.mark.parametrize(
    "name, genre, description, expected",
    [
        ("[☀️UPD 21🏖️] Anime Adventures", "Tower Defense", "Can you summon the strongest heroes?", IN),
        ("Vanguards: Trail of the Saint", "Tower Defense", "Summon units to fight these enemies", IN),
        ("Sorcerer Tower Defense [NAOYA]", "Tower Defense", "First Jujutsu Kaisen Tower Defense game!", IN),
        ("[👊 OPM] Re:Rangers X", "Tower Defense", "", IN),
        ("[ ⚡️X3 SPEED ] AnimeReversal", "Tower Defense", "", IN),
        ("Fruit Tower Defense", "Tower Defense", "Place anime units and other units to fight back!", IN),
        ("[💥OG LOBBY] Toilet Tower Defense", "Tower Defense", "Place cameramen to fight back against toilets", OUT),
        ("Tower Defense Simulator", "Tower Defense", "Place units to defend against hordes of zombies!", OUT),
        ("[🎃HALLOWEEN🎃] Undertale Adventures X", "Tower Defense", "A tower defense game based on Undertale", OUT),
        ("Anime Fighting Simulator", "Incremental Simulator", "Train in anime worlds", OUT),
        ("Random Tower Defense", "Tower Defense", "Tags: Tower Defense, Strategy, Anime", CHECK),
        ("Anime Toilet Defense", "Tower Defense", "Stop the toilets!", CHECK),
        ("Roll Anime Defense", "Tycoon", "", CHECK),
    ],
)
def test_the_anime_td_words_sort_real_games(name, genre, description, expected):
    assert verdict(name, genre, description).verdict == expected


def test_every_verdict_says_why():
    decision = verdict("Anime Toilet Defense", description="Stop the toilets!")
    assert decision.reasons == ["theme: anime (name)", "other theme: toilet (name), toilets (description)"]


def test_your_own_games_always_wait_for_you():
    assert verdict("Romance TD [RELEASE]", own=True).verdict == CHECK
    assert verdict("Superhero TD", genre="", own=True).verdict == CHECK
    assert verdict("My Zombie Restaurant", genre="Tycoon", own=True).verdict == OUT


def test_your_decisions_win_over_the_words():
    rules = Rules.load(Path(__file__).parent.parent / "lists" / "anime-td.toml")
    rules.include[1] = "anime art in the icon"
    decision = verdict("Tower Defense Simulator", rules=rules)
    assert (decision.verdict, decision.by_hand, decision.reasons) == (IN, True, ["Ronan: anime art in the icon"])
    rules.include.clear()
    rules.exclude[1] = "not anime"
    assert verdict("Anime Adventures", rules=rules).verdict == OUT


def test_a_list_is_built_from_a_saved_day(tmp_path):
    _, store = run_fake_day(tmp_path)  # A reads like an anime TD, B like a toilet TD, C is your own game
    verdicts = {game["universe_id"]: decision.verdict for game, decision in build(store, RULES, DAY)}
    assert verdicts == {A: IN, B: OUT, C: CHECK}
    assert members(store, RULES, DAY) == {A}


@pytest.mark.parametrize(
    "name, description",
    [
        ("[⭐BACK⭐] Uma Tower Defense", "This is a fan project and not affiliated with CyGames in anyway."),
        ("[HALLOWEEN] Vocaloid Tower Defense", "Lead your Vocaloid team in this co op tower defense!"),
        ("[Railway!] Kivotos Tower Defense", "This is infact a fan game for blue archive"),
    ],
)
def test_anime_style_franchises_wait_for_a_person(name, description):
    decision = verdict(name, description=description)
    assert decision.verdict == CHECK and decision.reasons[0].startswith("weak sign:")


def test_a_genre_only_list_takes_every_game_of_the_genre():
    rules = Rules.load(Path(__file__).parent.parent / "lists" / "tower-defense.toml")
    assert not rules.has_theme
    assert verdict("[💥OG LOBBY] Toilet Tower Defense", rules=rules).verdict == IN
    assert verdict("Anime RNG TD", genre="Incremental Simulator", rules=rules).verdict == CHECK
    assert verdict("Anime Fighting Simulator", genre="Incremental Simulator", rules=rules).verdict == OUT
