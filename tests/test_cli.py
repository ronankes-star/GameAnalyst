from pathlib import Path

from gameanalyst.cli import log_line, main
from tests.fakes import run_fake_day


def test_log_line_appends_one_line_each_time(tmp_path):
    log_line(tmp_path, "first")
    log_line(tmp_path, "second\n")
    assert (tmp_path / "logs" / "collect.log").read_text(encoding="utf-8") == "first\nsecond\n"


def test_show_with_no_data_says_what_to_run(tmp_path, capsys):
    assert main(["--data", str(tmp_path), "show"]) == 1
    assert "python -m gameanalyst collect" in capsys.readouterr().out


LISTS = str(Path(__file__).parent.parent / "lists")


def fake_data(tmp_path):
    """A data folder that holds one fake day: A reads like an anime TD, B like a toilet TD, C is your own game."""
    _, store = run_fake_day(tmp_path)
    store.close()
    (tmp_path / "db.sqlite").rename(tmp_path / "gameanalyst.sqlite")
    return ["--data", str(tmp_path), "--lists", LISTS]


def test_list_prints_the_games_to_check(tmp_path, capsys):
    assert main([*fake_data(tmp_path), "list"]) == 0
    out = capsys.readouterr().out
    assert "in: 1   check: 1" in out and "your own game" in out


def test_show_can_keep_only_the_games_in_a_list(tmp_path, capsys):
    assert main([*fake_data(tmp_path), "show", "--list", "anime-td"]) == 0
    out = capsys.readouterr().out
    assert "Game 1001" in out and "Game 1002" not in out


def test_an_unknown_list_says_so(tmp_path, capsys):
    assert main([*fake_data(tmp_path), "list", "nope"]) == 1
    assert "No list called nope" in capsys.readouterr().out

