import pytest
from unittest.mock import patch
from validate import check_worldview, check_picks

TODAY = "2024-01-10"
SEGMENTS = {"compute", "power", "cooling"}

UNIVERSE = {"segments": {s: [] for s in SEGMENTS}}


def _worldview(**overrides):
    base = {
        "date": TODAY,
        "headline": "Test headline",
        "regime": "Test regime",
        "theses": [],
        "segments": {s: {"stance": "neutral", "note": ""} for s in SEGMENTS},
        "risks": ["risk1"],
        "watch": ["watch1"],
        "previous": None,
    }
    base.update(overrides)
    return base


def _thesis(**overrides):
    base = {
        "id": "test-thesis",
        "title": "Test thesis",
        "stance": "bullish",
        "confidence": 70,
        "segments": ["compute"],
        "evidence": ["evidence item"],
        "change": "unchanged",
        "change_note": "nothing changed",
    }
    base.update(overrides)
    return base


@patch("validate.today", return_value=TODAY)
@patch("validate.universe", return_value=UNIVERSE)
class TestCheckWorldview:
    def test_valid_worldview_no_errors(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(), errs)
        assert errs == []

    def test_missing_key_reported(self, mock_uni, mock_today):
        errs = []
        w = _worldview()
        del w["headline"]
        check_worldview(w, errs)
        assert any("headline" in e for e in errs)

    def test_wrong_date_reported(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(date="2024-01-09"), errs)
        assert any("date" in e for e in errs)

    def test_invalid_thesis_stance(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(theses=[_thesis(stance="maybe")]), errs)
        assert any("stance" in e for e in errs)

    def test_invalid_thesis_change(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(theses=[_thesis(change="maybe")]), errs)
        assert any("change" in e for e in errs)

    def test_confidence_out_of_range(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(theses=[_thesis(confidence=150)]), errs)
        assert any("confidence" in e for e in errs)

    def test_confidence_not_int(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(theses=[_thesis(confidence=70.5)]), errs)
        assert any("confidence" in e for e in errs)

    def test_unknown_segment_in_thesis(self, mock_uni, mock_today):
        errs = []
        check_worldview(_worldview(theses=[_thesis(segments=["unknown_seg"])]), errs)
        assert any("unknown_seg" in e for e in errs)

    def test_missing_segment_key(self, mock_uni, mock_today):
        errs = []
        w = _worldview()
        del w["segments"]["compute"]
        check_worldview(w, errs)
        assert any("compute" in e for e in errs)

    def test_invalid_segment_stance(self, mock_uni, mock_today):
        errs = []
        w = _worldview()
        w["segments"]["compute"] = {"stance": "bullish", "note": ""}
        check_worldview(w, errs)
        assert any("compute" in e for e in errs)

    def test_not_a_dict(self, mock_uni, mock_today):
        errs = []
        check_worldview(None, errs)
        assert errs


@patch("validate.today", return_value=TODAY)
class TestCheckPicks:
    SHORTLIST = [{"ticker": "NVDA"}, {"ticker": "AMD"}]

    def test_valid_picks_no_errors(self, mock_today):
        errs = []
        picks = {"picks": [{"ticker": "NVDA", "segment": "compute", "why": "w", "risk": "r", "thesis_ids": []}]}
        check_picks(picks, self.SHORTLIST, errs)
        assert errs == []

    def test_ticker_not_on_shortlist(self, mock_today):
        errs = []
        picks = {"picks": [{"ticker": "INTC", "segment": "compute", "why": "w", "risk": "r", "thesis_ids": []}]}
        check_picks(picks, self.SHORTLIST, errs)
        assert any("INTC" in e for e in errs)

    def test_more_than_two_picks(self, mock_today):
        errs = []
        pick = {"ticker": "NVDA", "segment": "compute", "why": "w", "risk": "r", "thesis_ids": []}
        check_picks({"picks": [pick, pick, pick]}, self.SHORTLIST, errs)
        assert any("2" in e for e in errs)

    def test_missing_field_reported(self, mock_today):
        errs = []
        pick = {"ticker": "NVDA", "segment": "compute"}
        check_picks({"picks": [pick]}, self.SHORTLIST, errs)
        assert any("why" in e for e in errs)

    def test_empty_picks(self, mock_today):
        errs = []
        check_picks({"picks": []}, self.SHORTLIST, errs)
        assert errs

    def test_missing_picks_key(self, mock_today):
        errs = []
        check_picks({}, self.SHORTLIST, errs)
        assert errs
