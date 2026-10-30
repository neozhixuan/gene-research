from datetime import datetime, timezone

from brief import candidates, check_brief, next_us_open, session_label
from usage import _totals

DATE = "2026-10-29"


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def test_open_same_evening_in_singapore():
    assert session_label(_utc("2026-10-30T11:55:00")) == "US open Fri 30 Oct, 21:30 SGT"


def test_open_after_close_rolls_to_monday_and_handles_dst_end():
    # Friday 22:00 SGT is after Friday's open; US clocks go back on 1 Nov 2026
    assert session_label(_utc("2026-10-30T14:00:00")) == "US open Mon 2 Nov, 22:30 SGT"


def test_open_in_winter_time():
    assert next_us_open(_utc("2026-12-01T12:00:00")).hour == 9


def _watch():
    return {
        "AAA": {"segment": "power", "status": "active", "checks": [{"date": "2026-10-20", "rating": "Hold"}, {"date": "2026-10-28", "rating": "Overweight"}]},
        "BBB": {"segment": "power", "status": "active", "checks": [{"date": "2026-10-28", "rating": "Underweight"}]},
        "CCC": {"segment": "power", "status": "dropped", "checks": [{"date": "2026-10-28", "rating": "Buy"}]},
        "DDD": {"segment": "power", "status": "active", "checks": [{"date": "2026-10-29", "rating": None}]},
    }


def test_candidates_are_active_buy_side_names_with_rated_price():
    track = {"picks": [{"ticker": "AAA", "date": "2026-10-28", "price": "100", "now": 110, "return": 0.1, "vs_qqq": 0.05},
                       {"ticker": "AAA", "date": "2026-10-20", "price": "90", "now": 110, "return": 0.22, "vs_qqq": 0.1}]}
    out = candidates(_watch(), track)
    assert [c["ticker"] for c in out] == ["AAA"]
    assert out[0]["rated_price"] == 100.0 and out[0]["rated_on"] == "2026-10-28"


def _brief(**over):
    b = {"date": DATE, "session": "US open Fri 30 Oct, 21:30 SGT", "written_at": "2026-10-30T20:10:00+08:00", "lean": "wait",
         "bottom_line": "x", "what_changed": ["a"], "trust": "t", "if_buying": ["b"],
         "names": [{"ticker": "AAA", "rating": "Overweight", "rated_on": DATE, "rated_price": 1.0, "last_price": None,
                    "since_rated": None, "catalyst": "", "take": "y"}],
         "sources": [{"title": "s", "url": "https://example.com"}]}
    b.update(over)
    return b


def test_valid_brief_passes():
    assert check_brief(_brief(), DATE, []) == []


def test_bad_lean_wrong_date_and_bad_source_are_reported():
    errs = check_brief(_brief(lean="buy", date="2026-10-28", sources=[{"title": "s", "url": "ftp://x"}]), DATE, [])
    assert any("lean" in x for x in errs) and any("date" in x for x in errs) and any("sources" in x for x in errs)


def test_name_missing_field_and_string_price():
    names = [{"ticker": "AAA", "rating": "Overweight", "rated_on": DATE, "rated_price": "1.0", "last_price": None, "since_rated": None, "take": "y"}]
    errs = check_brief(_brief(names=names), DATE, [])
    assert any("catalyst" in x for x in errs) and any("rated_price" in x for x in errs)


def test_usage_totals_tolerate_null_counts():
    t = _totals([{"input_tokens": 1, "output_tokens": None, "cache_read_input_tokens": 5}, {"output_tokens": 2}])
    assert t == {"input_tokens": 1, "output_tokens": 2, "cache_read_tokens": 5, "cache_write_tokens": 0, "model_calls": 2}
