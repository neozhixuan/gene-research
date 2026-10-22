"""Text utilities for cleaning and repairing agent output."""

import re

_HEADING = re.compile(r"(?<=[.!?)])\s+((?:\d+\.\s+)?[A-Z][\w&/\-'' ]{2,40}?):\s")


def clean_report(text: str | None) -> str:
    """Repair agent output for display.

    Gemini sometimes leaks a fragment of its hidden reasoning as the first line
    (e.g. "শিল্পীthought"), and when TradingAgents falls back to free text the
    model can squash headings and a whole table onto one line. Both are fixed
    here; the stored output stays untouched.
    """
    text = re.sub(r"\A\s*\S*thought\s*\n", "", text or "")
    lines = []
    for line in text.split("\n"):
        if len(line) > 500:
            line = _HEADING.sub(r"\n\n**\1:** ", line)
        if line.count("|") > 8 and re.search(r"\|\s*-{3,}\s*\|", line):
            head, _, table = line.partition("|")
            line = f"{head.rstrip()}\n\n|{re.sub(r'\|\s+\|', '|\n|', table)}"
        lines.append(line)
    return "\n".join(lines)
