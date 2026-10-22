"""Shared market constants used across fetch, digest, and site."""

MACRO_NAMES = {
    "^GSPC": "S&P 500",
    "^IXIC": "Nasdaq",
    "SMH": "Semis ETF",
    "^VIX": "VIX",
    "^TNX": "US 10y yield",
    "DX-Y.NYB": "Dollar index",
    "CL=F": "Crude oil",
    "BTC-USD": "Bitcoin",
}

# What each final rating means for you, depending on whether you already own the stock.
ACTIONS = {
    "Buy": ("Buy a full position (your normal size)", "Add to it"),
    "Overweight": ("Start a small position; add if the thesis holds", "Add a little"),
    "Hold": ("Don't buy yet; keep watching", "Keep it; no change"),
    "Underweight": ("Don't buy", "Trim: sell part of it"),
    "Sell": ("Don't buy", "Sell it all"),
}
