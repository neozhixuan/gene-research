import pytest
from watchlist import active, due_recheck, last_rating, record, trim, MAX_ACTIVE


def _make_entry(segment="compute", added="2024-01-01", status="active", checks=None):
    return {"segment": segment, "added": added, "status": status, "checks": checks or []}


def _check(date, rating):
    return {"date": date, "rating": rating, "kind": "new"}


class TestActive:
    def test_returns_only_active(self):
        watch = {
            "NVDA": _make_entry(status="active"),
            "AMD": _make_entry(status="dropped"),
        }
        assert set(active(watch)) == {"NVDA"}


class TestLastRating:
    def test_returns_last_rated_check(self):
        w = _make_entry(checks=[_check("2024-01-01", "Buy"), _check("2024-01-05", "Hold")])
        assert last_rating(w) == "Hold"

    def test_skips_unrated_check(self):
        w = _make_entry(checks=[_check("2024-01-01", "Buy"), {"date": "2024-01-05", "rating": None, "kind": "new"}])
        assert last_rating(w) == "Buy"

    def test_empty_checks_returns_none(self):
        assert last_rating(_make_entry()) is None


class TestDueRecheck:
    def test_empty_watchlist(self):
        assert due_recheck({}, "2024-01-10") is None

    def test_not_due_yet(self):
        watch = {"NVDA": _make_entry(checks=[_check("2024-01-09", "Buy")])}
        assert due_recheck(watch, "2024-01-10") is None

    def test_due_after_cutoff(self):
        watch = {"NVDA": _make_entry(checks=[_check("2024-01-01", "Buy")])}
        assert due_recheck(watch, "2024-01-10") == "NVDA"

    def test_positive_rating_prioritised(self):
        watch = {
            "NVDA": _make_entry(checks=[_check("2024-01-01", "Hold")]),
            "AMD": _make_entry(checks=[_check("2024-01-02", "Buy")]),
        }
        assert due_recheck(watch, "2024-01-10") == "AMD"

    def test_dropped_names_excluded(self):
        watch = {"NVDA": _make_entry(status="dropped", checks=[_check("2024-01-01", "Buy")])}
        assert due_recheck(watch, "2024-01-10") is None


class TestRecord:
    def test_creates_new_entry(self):
        watch = {}
        record(watch, "NVDA", "compute", "2024-01-10", "Buy", "new")
        assert "NVDA" in watch
        assert watch["NVDA"]["status"] == "active"

    def test_appends_check(self):
        watch = {}
        record(watch, "NVDA", "compute", "2024-01-10", "Buy", "new")
        record(watch, "NVDA", "compute", "2024-01-15", "Hold", "recheck")
        assert len(watch["NVDA"]["checks"]) == 2

    def test_deduplicates_same_day(self):
        watch = {}
        record(watch, "NVDA", "compute", "2024-01-10", "Buy", "new")
        record(watch, "NVDA", "compute", "2024-01-10", "Hold", "recheck")
        assert len(watch["NVDA"]["checks"]) == 1
        assert watch["NVDA"]["checks"][0]["rating"] == "Hold"

    def test_drops_on_two_consecutive_negatives(self):
        watch = {}
        record(watch, "NVDA", "compute", "2024-01-10", "Sell", "new")
        record(watch, "NVDA", "compute", "2024-01-15", "Underweight", "recheck")
        assert watch["NVDA"]["status"] == "dropped"
        assert "negative twice" in watch["NVDA"]["dropped_reason"]

    def test_drops_on_three_consecutive_holds(self):
        watch = {}
        for d in ("2024-01-10", "2024-01-15", "2024-01-20"):
            record(watch, "NVDA", "compute", d, "Hold", "recheck")
        assert watch["NVDA"]["status"] == "dropped"
        assert "three Holds" in watch["NVDA"]["dropped_reason"]

    def test_positive_then_negative_does_not_drop(self):
        watch = {}
        record(watch, "NVDA", "compute", "2024-01-10", "Buy", "new")
        record(watch, "NVDA", "compute", "2024-01-15", "Sell", "recheck")
        assert watch["NVDA"]["status"] == "active"

    def test_revives_dropped_on_new_pick(self):
        watch = {"NVDA": _make_entry(status="dropped", checks=[_check("2024-01-01", "Sell")])}
        record(watch, "NVDA", "compute", "2024-01-20", "Buy", "new")
        assert watch["NVDA"]["status"] == "active"
        assert watch["NVDA"]["added"] == "2024-01-20"


class TestTrim:
    def test_no_op_when_under_limit(self):
        watch = {f"T{i}": _make_entry(checks=[_check("2024-01-01", "Buy")]) for i in range(MAX_ACTIVE)}
        trim(watch, "2024-01-10")
        assert len(active(watch)) == MAX_ACTIVE

    def test_drops_stalest_non_positive_when_over(self):
        watch = {}
        for i in range(MAX_ACTIVE + 1):
            date = f"2024-01-{i + 1:02d}"
            watch[f"T{i}"] = _make_entry(checks=[_check(date, "Hold")])
        trim(watch, "2024-01-20")
        assert len(active(watch)) == MAX_ACTIVE

    def test_spares_positive_ratings(self):
        watch = {}
        for i in range(MAX_ACTIVE):
            watch[f"T{i}"] = _make_entry(checks=[_check("2024-01-01", "Buy")])
        watch["EXTRA"] = _make_entry(checks=[_check("2024-01-05", "Hold")])
        trim(watch, "2024-01-20")
        assert watch["EXTRA"]["status"] == "dropped"
        assert all(watch[f"T{i}"]["status"] == "active" for i in range(MAX_ACTIVE))
