"""Pure scoring and ranking functions shared by track and screen."""


def correct(rating: str, excess: float, hold_band: float = 0.05) -> bool | None:
    """Whether a rating was correct given the stock's excess return vs QQQ.

    hold_band: symmetric tolerance for Hold ratings.
    Returns None for ratings with no grading rule.
    """
    if rating in ("Buy", "Overweight"):
        return excess > 0
    if rating in ("Sell", "Underweight"):
        return excess < 0
    if rating == "Hold":
        return abs(excess) <= hold_band
    return None


def rank(rows: list[dict], factors: dict) -> list[dict]:
    """Rank rows by a weighted composite of factors.

    factors: {key: (weight, higher_is_better)}
    Adds rank_<key> and score fields to each row in-place.
    Returns rows sorted descending by score.
    """
    for key, (w, higher) in factors.items():
        vals = sorted(r[key] for r in rows if r[key] is not None)
        for r in rows:
            if r[key] is None:
                r[f"rank_{key}"] = 0.5
            else:
                pos = vals.index(r[key]) / max(len(vals) - 1, 1)
                r[f"rank_{key}"] = pos if higher else 1 - pos
    for r in rows:
        r["score"] = round(sum(r[f"rank_{k}"] * w for k, (w, _) in factors.items()), 3)
    return sorted(rows, key=lambda r: r["score"], reverse=True)
