from utils.scoring import correct, rank


class TestCorrect:
    def test_buy_beats_qqq(self):
        assert correct("Buy", 0.01) is True

    def test_buy_trails_qqq(self):
        assert correct("Buy", -0.01) is False

    def test_overweight_beats_qqq(self):
        assert correct("Overweight", 0.001) is True

    def test_sell_trails_qqq(self):
        assert correct("Sell", -0.01) is True

    def test_sell_beats_qqq(self):
        assert correct("Sell", 0.01) is False

    def test_underweight_trails_qqq(self):
        assert correct("Underweight", -0.01) is True

    def test_hold_within_band(self):
        assert correct("Hold", 0.03) is True

    def test_hold_at_band_edge(self):
        assert correct("Hold", 0.05) is True

    def test_hold_outside_band(self):
        assert correct("Hold", 0.06) is False

    def test_hold_negative_within_band(self):
        assert correct("Hold", -0.03) is True

    def test_unknown_rating_returns_none(self):
        assert correct("Unknown", 0.10) is None

    def test_empty_rating_returns_none(self):
        assert correct("", 0.10) is None

    def test_custom_hold_band(self):
        assert correct("Hold", 0.08, hold_band=0.10) is True
        assert correct("Hold", 0.08, hold_band=0.05) is False


class TestRank:
    FACTORS = {"score_a": (0.6, True), "score_b": (0.4, False)}

    def _rows(self):
        return [
            {"score_a": 10, "score_b": 5},
            {"score_a": 5, "score_b": 1},
            {"score_a": 1, "score_b": 10},
        ]

    def test_returns_sorted_descending(self):
        rows = self._rows()
        result = rank(rows, self.FACTORS)
        scores = [r["score"] for r in result]
        assert scores == sorted(scores, reverse=True)

    def test_adds_score_field(self):
        rows = self._rows()
        result = rank(rows, self.FACTORS)
        assert all("score" in r for r in result)

    def test_none_value_gets_median_rank(self):
        rows = [{"score_a": None, "score_b": 5}, {"score_a": 10, "score_b": 1}]
        result = rank(rows, self.FACTORS)
        none_row = next(r for r in result if r["score_a"] is None)
        assert none_row[f"rank_score_a"] == 0.5

    def test_single_row_is_ranked(self):
        rows = [{"score_a": 10, "score_b": 5}]
        result = rank(rows, self.FACTORS)
        # Single row: position 0 out of 1 → rank 0 for higher=True, 1 for higher=False
        # score = 0.6*0.0 + 0.4*1.0 = 0.4
        assert result[0]["score"] == 0.4

    def test_higher_is_better_respected(self):
        rows = [{"score_a": 100, "score_b": 1}, {"score_a": 1, "score_b": 100}]
        result = rank(rows, {"score_a": (1.0, True)})
        assert result[0]["score_a"] == 100
