import urllib.error

import pytest

from gameanalyst.http import Http, HttpError


def make(transport, **options):
    sleeps: list[float] = []
    http = Http(transport=transport, sleep=sleeps.append, clock=lambda: 0.0, **options)
    return http, sleeps


def test_a_429_is_retried_and_retry_after_is_honored():
    answers = iter([(429, {"Retry-After": "2"}, b""), (200, {}, b'{"ok": 1}')])
    http, sleeps = make(lambda url, headers, timeout: next(answers), min_interval=0)
    assert http.get_json("https://x.test") == {"ok": 1}
    assert sleeps == [2.0]
    assert http.requests_made == 2


def test_it_gives_up_after_max_retries():
    http, _ = make(lambda url, headers, timeout: (503, {}, b""), max_retries=2, min_interval=0)
    with pytest.raises(HttpError) as error:
        http.get_json("https://x.test")
    assert error.value.status == 503
    assert http.requests_made == 3


def test_client_errors_are_not_retried():
    http, _ = make(lambda url, headers, timeout: (404, {}, b"not found"), min_interval=0)
    with pytest.raises(HttpError):
        http.get_json("https://x.test")
    assert http.requests_made == 1


def test_network_errors_are_retried():
    calls = {"n": 0}

    def flaky(url, headers, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("connection reset")
        return 200, {}, b'{"ok": true}'

    http, _ = make(flaky, min_interval=0)
    assert http.get_json("https://x.test") == {"ok": True}


def test_requests_are_spaced_by_min_interval():
    http, sleeps = make(lambda url, headers, timeout: (200, {}, b"{}"), min_interval=0.5)
    http.get_json("https://x.test")
    http.get_json("https://x.test")
    assert sleeps == [0.5]


def test_commas_in_id_lists_stay_readable():
    seen: list[str] = []
    http, _ = make(lambda url, headers, timeout: (seen.append(url), (200, {}, b"{}"))[1], min_interval=0)
    http.get_json("https://x.test/v1/games", {"universeIds": "1,2,3"})
    assert seen == ["https://x.test/v1/games?universeIds=1,2,3"]
