from gameanalyst.cli import log_line, main


def test_log_line_appends_one_line_each_time(tmp_path):
    log_line(tmp_path, "first")
    log_line(tmp_path, "second\n")
    assert (tmp_path / "logs" / "collect.log").read_text(encoding="utf-8") == "first\nsecond\n"


def test_show_with_no_data_says_what_to_run(tmp_path, capsys):
    assert main(["--data", str(tmp_path), "show"]) == 1
    assert "python -m gameanalyst collect" in capsys.readouterr().out
