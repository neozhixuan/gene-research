from datetime import datetime, timezone, timedelta
from fetch import dedupe, tag_tickers


def _item(title, summary="", published=None, tickers=None):
    return {
        "title": title,
        "summary": summary,
        "published": published or datetime.now(timezone.utc).isoformat(),
        "source": "test",
        "tickers": tickers or [],
    }


class TestTagTickers:
    KNOWN = {"NVDA", "AMD", "INTC", "TSM"}

    def test_finds_ticker_in_title(self):
        item = _item("NVDA rises on AI demand")
        assert "NVDA" in tag_tickers(item, self.KNOWN)

    def test_finds_ticker_in_summary(self):
        item = _item("Chip stocks rally", summary="AMD leads gains")
        assert "AMD" in tag_tickers(item, self.KNOWN)

    def test_does_not_partial_match(self):
        item = _item("NVIDIA reports earnings")
        assert "NVDA" not in tag_tickers(item, self.KNOWN)

    def test_returns_sorted(self):
        item = _item("NVDA and AMD both rise")
        result = tag_tickers(item, self.KNOWN)
        assert result == sorted(result)

    def test_no_match_returns_empty(self):
        item = _item("Gold prices rise on inflation fears")
        assert tag_tickers(item, self.KNOWN) == []

    def test_passes_through_related_field(self):
        item = {**_item("some headline"), "related": ["TSM"]}
        assert "TSM" in tag_tickers(item, self.KNOWN)


class TestDedupe:
    def _cutoff(self, hours_ago=1):
        return datetime.now(timezone.utc) - timedelta(hours=hours_ago)

    def test_removes_duplicate_titles(self):
        items = [_item("NVDA rises"), _item("NVDA rises")]
        result = dedupe(items, self._cutoff())
        assert len(result) == 1

    def test_removes_old_articles(self):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=48)).isoformat()
        items = [_item("NVDA rises", published=old_time)]
        result = dedupe(items, self._cutoff())
        assert result == []

    def test_keeps_recent_articles(self):
        items = [_item("NVDA rises")]
        result = dedupe(items, self._cutoff())
        assert len(result) == 1

    def test_assigns_id(self):
        items = [_item("NVDA rises on AI demand")]
        result = dedupe(items, self._cutoff())
        assert "id" in result[0]
        assert len(result[0]["id"]) == 12

    def test_dedupes_case_insensitively(self):
        items = [_item("nvda rises"), _item("NVDA RISES")]
        result = dedupe(items, self._cutoff())
        assert len(result) == 1

    def test_skips_items_without_title(self):
        items = [_item("")]
        result = dedupe(items, self._cutoff())
        assert result == []
