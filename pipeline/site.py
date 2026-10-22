"""Stage 7: render the static site into site/ from the files under data/.

site/index.html          landing page: hero + overview across every day
site/days/<date>.html    one in-depth page per day
site/assets/site.css     shared stylesheet (written here)
site/assets/logo.png     the helix logo (checked in)

Pure code: Vercel serves the folder as-is, nothing is built there.
"""

import csv
import html
import re
from datetime import date as Date

from markdown_it import MarkdownIt

import watchlist
from common import ACTIONS, DATA, MACRO_NAMES, SITE, clean_report, read_json

md = MarkdownIt("commonmark", {"html": False}).enable("table")
e = html.escape
GITHUB = "https://github.com/neozhixuan/gene-research"
FOOTER = ("An automated research experiment: news and prices from Yahoo Finance, worldview and picks by Claude, "
          "verification by TradingAgents on Gemini. Model output can be wrong. This is an experiment, not financial advice.")


# ---------- small helpers ----------

def render_md(text):
    text = re.sub(r"^\s*(Bull|Bear|Aggressive|Conservative|Neutral) Analyst:\s*", "", clean_report(text))
    return md.render(text.strip()).replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")


def chip(rating, cls="chip"):
    r = rating or "n/a"
    return f'<span class="{cls} r-{e(r.lower())}">{e(r)}</span>'


def dot(rating, title=""):
    r = (rating or "n/a").lower()
    return f'<span class="dot d-{e(r)}" title="{e(title)}"></span>'


def pct(x, signed=True):
    if x is None:
        return "–"
    if round(x * (100 if signed else 1) * 10) == 0:
        x = 0.0
    return (f"{x * 100:+.1f}%" if signed else f"{x * 100:.0f}%").replace("-", "−")


def tone(x):
    return "" if x is None else ("pos" if x > 0 else "neg" if x < 0 else "")


def seg_name(k):
    return k.replace("_", " ")


def seg_label(k):
    s = seg_name(k)
    return (s[:1].upper() + s[1:]).replace("Ai ", "AI ")


def weekday(d):
    return Date.fromisoformat(d).strftime("%a")


def nice_date(d):
    return Date.fromisoformat(d).strftime("%a %-d %b %Y")


# ---------- data loading ----------

def load_day(d):
    """Everything one day page or day card needs."""
    folder = DATA / d
    w = read_json(DATA / "worldview" / f"{d}.json")
    picks = read_json(folder / "picks.json", {}).get("picks", [])
    runs = read_json(folder / "runs.json") or [{"ticker": p["ticker"], "segment": p["segment"], "kind": "new"} for p in picks]
    return {
        "date": d,
        "w": w,
        "picks": {p["ticker"]: p for p in picks},
        "runs": runs,
        "agents": {r["ticker"]: read_json(folder / "agents" / f"{r['ticker']}.json") or {} for r in runs},
        "shortlist": read_json(folder / "shortlist.json", {}).get("shortlist", []),
        "market": read_json(folder / "market.json", {}),
    }


def usage_rows():
    path = DATA / "usage.csv"
    return list(csv.DictReader(open(path))) if path.exists() else []


# ---------- day page pieces ----------

def worldview_html(w):
    if not w:
        return "<p>No worldview for this day.</p>"
    order = {"new": 0, "stronger": 1, "weaker": 2, "retired": 3, "unchanged": 4}
    theses = sorted(w["theses"], key=lambda t: (order.get(t["change"], 9), -t["confidence"]))
    rows = "".join(f'''<li class="thesis">
  <div class="th-top"><span class="stance s-{e(t["stance"])}">{e(t["stance"])}</span><strong>{e(t["title"])}</strong>
  <span class="conf" title="confidence"><span style="width:{int(t["confidence"])}%"></span></span><span class="cn">{int(t["confidence"])}</span>
  <span class="chg c-{e(t["change"])}">{e(t["change"])}</span></div>
  <p class="note">{e(t["change_note"])}</p>
  <p class="segs">{" · ".join(e(seg_name(s)) for s in t["segments"])}</p>
</li>''' for t in theses)
    segs = "".join(f'<div class="seg st-{e(v["stance"])}"><span class="sg">{e(seg_name(k))}</span><span class="sv">{e(v["stance"])}</span><p>{e(v.get("note", ""))}</p></div>'
                   for k, v in w["segments"].items())
    lists = lambda xs: "".join(f"<li>{e(x)}</li>" for x in xs)
    return f'''<p class="regime">{e(w["regime"])}</p>
<h3>Theses</h3><ul class="theses">{rows}</ul>
<h3>Segments</h3><div class="segrid">{segs}</div>
<div class="two"><div><h3>Risks</h3><ul class="plain">{lists(w["risks"])}</ul></div><div><h3>Watching next</h3><ul class="plain">{lists(w["watch"])}</ul></div></div>'''


def action_html(rating):
    if rating not in ACTIONS:
        return ""
    out, held = ACTIONS[rating]
    return (f'<dl class="action"><div><dt>If you don&#39;t own it</dt><dd>{e(out)}</dd></div>'
            f'<div><dt>If you own it</dt><dd>{e(held)}</dd></div></dl>')


def models_html(a):
    m = a.get("models")
    if not m:
        return ""
    quick = e(m["quick"]) + (" (fallback: the default was overloaded)" if m.get("quick_is_fallback") else "")
    return (f'<p class="models">TradingAgents {e(m.get("tradingagents", ""))} on {e(m["provider"])} · '
            f'managers: {e(m["deep"])} · analysts, debaters, trader: {quick}</p>')


def history_html(w):
    return " ".join(f'<span title="{e(c["date"])}">{chip(c.get("rating"))}</span>' for c in w["checks"])


def run_html(r, a, pick, shortlist, watch):
    t = r["ticker"]
    row = next((x for x in shortlist if x["ticker"] == t), {})
    a = a or {}
    if a.get("rating"):
        chain = f'''<div class="chain"><div><span class="lbl">Research manager</span>{chip(a.get("research_manager"))}</div><span class="arr">→</span>
<div><span class="lbl">Trader</span>{chip(a.get("trader"))}</div><span class="arr">→</span>
<div><span class="lbl">Portfolio manager (final)</span>{chip(a["rating"], "chip big")}</div></div>{action_html(a["rating"])}{models_html(a)}'''
        agents = "".join(f'<details{" open" if k == "Portfolio manager" else ""}><summary>{e(k)}</summary><div class="prose">{render_md(v)}</div></details>'
                         for k, v in a.get("outputs", {}).items() if v)
    else:
        chain = f'<p class="muted">TradingAgents did not run: {e(a.get("error") or a.get("skipped") or "no result")}</p>'
        agents = ""
    facts = (f'<dl class="facts"><div><dt>Price</dt><dd>{f"{row['price']:,.2f}" if row.get("price") else "–"}</dd></div><div><dt>Fwd P/E</dt><dd>{row.get("fwd_pe") or "–"}</dd></div>'
             f'<div><dt>Rev growth</dt><dd>{pct(row.get("rev_growth"))}</dd></div><div><dt>FCF yield</dt><dd>{pct(row.get("fcf_yield"))}</dd></div>'
             f'<div><dt>Off 52w high</dt><dd>{pct(row.get("drawdown"))}</dd></div><div><dt>Analysts</dt><dd>{row.get("coverage", "–")}</dd></div></dl>') if row else ""
    if r["kind"] == "recheck":
        w = watch.get(t, {})
        about = f'<p><strong>Re-check:</strong> on the watchlist since {e(w.get("added", "?"))}. Ratings so far: {history_html(w) if w else ""}</p>'
        if w.get("status") == "dropped" and w.get("dropped") == a.get("date"):
            about += f'<p><strong>Dropped from the watchlist today:</strong> {e(w["dropped_reason"])}.</p>'
    else:
        about = (f'<p><strong>Why watch:</strong> {e(pick.get("why", ""))}</p><p><strong>Main risk:</strong> {e(pick.get("risk", ""))}</p>')
    badge = '<span class="kind">re-check</span>' if r["kind"] == "recheck" else '<span class="kind new">new pick</span>'
    return f'''<article class="pick" id="{e(t)}">
  <header><h3>{e(t)}</h3>{badge}<span class="muted">{e(row.get("name") or "")} · {e(seg_name(r["segment"]))}</span></header>
  {facts}
  {about}
  {chain}
  {f'<div class="agents"><p class="lbl">Every agent&#39;s output</p>{agents}</div>' if agents else ""}
</article>'''


def market_html(m):
    cells = "".join(f'<div><span class="lbl">{e(name)}</span><strong>{m[k]["close"]:,.2f}</strong>'
                    f'<span class="n {tone(m[k].get("chg_1d"))}">{pct(m[k].get("chg_1d"))}</span></div>'
                    for k, name in MACRO_NAMES.items() if k in m and m[k].get("close") is not None)
    return f'<div class="market">{cells}</div>' if cells else ""


HOW_TO_READ = """<details class="howto"><summary>How to read a verdict</summary><div class="prose">
<p>Each stock goes through a team of AI agents. Analysts write reports, a bull and a bear debate them, the <strong>research manager</strong> judges the debate,
the <strong>trader</strong> proposes a trade, three risk analysts argue over it, and the <strong>portfolio manager</strong> has the final say. It can overrule the trader.</p>
<p>The final rating translates to an action depending on whether you already own the stock:</p>
<div class="tw"><table><thead><tr><th>Rating</th><th>If you don&#39;t own it</th><th>If you own it</th></tr></thead><tbody>
""" + "".join(f"<tr><td>{k}</td><td>{a}</td><td>{b}</td></tr>" for k, (a, b) in ACTIONS.items()) + """</tbody></table></div>
<p>The agents assume a $10,000 cash account with no positions. Nothing is traded automatically; you decide.</p></div></details>"""


def day_page(day, prev_d, next_d, watch):
    d, w = day["date"], day["w"]
    runs_html = "".join(run_html(r, day["agents"].get(r["ticker"]), day["picks"].get(r["ticker"], {}), day["shortlist"], watch)
                        for r in day["runs"]) or "<p class='muted'>No stocks ran this day.</p>"
    link = lambda x, label, rel: (f'<a href="{x}.html" rel="{rel}">{label}</a>' if x else f'<span class="off">{label}</span>')
    pager = (f'<nav class="pager" aria-label="Days">{link(prev_d, "← " + (prev_d or "Older"), "prev")}'
             f'<a href="../index.html#archive">All days</a>{link(next_d, (next_d or "Newer") + " →", "next")}</nav>')
    body = f'''<header class="slim"><a class="brand" href="../index.html"><img src="../assets/logo.png" alt="" width="40" height="40"><span>GENE RESEARCH</span></a>
<a class="back" href="../index.html">← Overview</a></header>
<main>
<header class="top"><div class="eyebrow">{e(nice_date(d))}</div>
<h1>{e(w["headline"] if w else "Daily AI-bottleneck research")}</h1>{market_html(day["market"])}</header>
<section><h2>Worldview</h2>{worldview_html(w)}</section>
<section><h2>Analysis</h2>{HOW_TO_READ}<div class="picks">{runs_html}</div></section>
{pager}
<footer>{e(FOOTER)}</footer>
</main>'''
    return page(f"Gene Research · {d}", body, "../", d and (w or {}).get("headline", ""))


# ---------- landing page pieces ----------

def stats(days, loaded, watch, track):
    analysed = {r["ticker"] for day in loaded for r in day["runs"] if day["agents"].get(r["ticker"], {}).get("rating")}
    avg = ((track or {}).get("summary") or {}).get("avg_vs_qqq")
    items = [(str(len(days)), "days of research"), (str(len(analysed)), "stocks analysed"),
             (str(len(watchlist.active(watch))), "on the watchlist"), (pct(avg), "new picks vs QQQ, avg")]
    return "".join(f'<div><strong>{e(v)}</strong><span>{e(k)}</span></div>' for v, k in items)


def hero_html(latest, days, loaded, watch, track):
    nav = (f'<a href="#today">Today</a><a href="#watchlist">Watchlist</a><a href="#track">Track record</a>'
           f'<a href="#archive">Archive</a><a href="{GITHUB}" rel="noopener">GitHub</a>')
    return f'''<header class="hero">
<canvas id="lava" aria-hidden="true"></canvas><div class="veil" aria-hidden="true"></div>
<div class="hero-in">
  <div class="hero-nav"><a class="brand" href="index.html"><img src="assets/logo.png" alt="" width="64" height="64"><span>GENE RESEARCH</span></a>
  <nav aria-label="Sections">{nav}</nav></div>
  <div class="hero-body">
    <div class="hero-text">
      <p>A daily research diary on AI&#39;s bottlenecks: compute, power, grid, cooling and the companies that supply them.
      Worldview by Claude, verification by TradingAgents on Gemini.</p>
      <a class="pill" href="days/{latest}.html"><span class="pill-dot" aria-hidden="true"></span>Read today&#39;s analysis →</a>
    </div>
    <div class="stats">{stats(days, loaded, watch, track)}</div>
  </div>
</div>
</header>'''


def glance_html(day):
    w = day["w"] or {}
    cards = []
    for r in day["runs"]:
        a = day["agents"].get(r["ticker"], {})
        rating = a.get("rating")
        act = action_html(rating) if rating else f'<p class="muted">Did not run: {e(a.get("error") or a.get("skipped") or "no result")}</p>'
        kind = '<span class="kind">re-check</span>' if r["kind"] == "recheck" else '<span class="kind new">new pick</span>'
        cards.append(f'''<a class="run" href="days/{day["date"]}.html#{e(r["ticker"])}">
  <div class="run-top"><span class="tk big">{e(r["ticker"])}</span>{kind}<span class="grow"></span>{chip(rating, "chip big")}</div>
  <p class="muted small">{e(seg_name(r["segment"]))}</p>{act}</a>''')
    runs = "".join(cards) or "<p class='muted'>No stocks ran today.</p>"
    return f'''<p class="eyebrow">{e(nice_date(day["date"]))}</p>
<p class="headline">{e(w.get("headline", ""))}</p>
<div class="runs">{runs}</div>
<p><a class="more" href="days/{day["date"]}.html">Full worldview and every agent&#39;s output →</a></p>'''


def board_html(watch, track):
    if not watch:
        return "<p class='muted'>Empty. Every new pick joins the watchlist.</p>"
    picks = (track or {}).get("picks", [])
    active, dropped = [], []
    for t, w in sorted(watch.items()):
        # tracking.json is newest first, so the last row for a ticker is the day it was added
        f = next((p for p in reversed(picks) if p["ticker"] == t), {})
        if w["status"] != "active":
            dropped.append(f'<li><span class="tk">{e(t)}</span> <span class="muted">{e(seg_name(w["segment"]))} · dropped {e(w.get("dropped", ""))}</span>: {e(w.get("dropped_reason", ""))}</li>')
            continue
        last = watchlist.last_rating(w)
        out, held = ACTIONS.get(last, ("–", "–"))
        dots = "".join(dot(c.get("rating"), f'{c["date"]}: {c.get("rating") or "no rating"}') for c in w["checks"])
        active.append(f'''<div class="wcard">
  <div class="run-top"><span class="tk big">{e(t)}</span><span class="grow"></span>{chip(last)}</div>
  <p class="muted small">{e(seg_name(w["segment"]))} · since {e(w["added"])}</p>
  <div class="dots" aria-label="Rating history, oldest first">{dots}</div>
  <dl class="nums"><div><dt>Since added</dt><dd class="{tone(f.get("return"))}">{pct(f.get("return"))}</dd></div>
  <div><dt>vs QQQ</dt><dd class="{tone(f.get("vs_qqq"))}">{pct(f.get("vs_qqq"))}</dd></div></dl>
  <dl class="mini"><div><dt>Don&#39;t own it</dt><dd>{e(out)}</dd></div><div><dt>Own it</dt><dd>{e(held)}</dd></div></dl>
</div>''')
    legend = "".join(f'<span>{dot(k)}{k}</span>' for k in ACTIONS)
    off = (f'<details class="dropped"><summary>Dropped ({len(dropped)})</summary><ul class="plain">{"".join(dropped)}</ul></details>' if dropped else "")
    return f'''<p class="muted">Every pick stays under watch. One name is re-checked each day (confident ones first, every {watchlist.RECHECK_AFTER_DAYS}+ days).
A name is dropped after two negative ratings in a row or three Holds in a row; at most {watchlist.MAX_ACTIVE} stay active.</p>
<div class="legend">{legend}</div>
<div class="board">{"".join(active) or "<p class='muted'>No active names.</p>"}</div>{off}'''


MARKS = {"new": ("+", "new"), "stronger": ("▲", "stronger"), "weaker": ("▼", "weaker"), "retired": ("×", "retired")}


def thesis_grid_html(days, loaded):
    by_day = {x["date"]: {t["id"]: t for t in (x["w"] or {}).get("theses", [])} for x in loaded}
    latest = {}
    for d in days:
        latest.update(by_day[d])
    if not latest:
        return "<p class='muted'>No theses yet.</p>"
    rows = sorted(latest.values(), key=lambda t: (t["change"] == "retired", -t["confidence"]))
    head = "".join(f'<th scope="col"><span>{weekday(d)}</span>{d[5:]}</th>' for d in days)
    body = ""
    for t in rows:
        cells = ""
        for d in days:
            x = by_day[d].get(t["id"])
            if not x:
                cells += '<td class="cell empty"></td>'
                continue
            c = int(x["confidence"])
            mark, label = MARKS.get(x["change"], ("", x["change"]))
            cls = "cell" + (" hi" if c >= 55 else "") + (" ret" if x["change"] == "retired" else "")
            cells += (f'<td class="{cls}" style="--c:{c}%" title="{e(d)}: {c} confidence, {e(label)}">'
                      f'{c}<i>{mark}</i></td>')
        body += (f'<tr><th scope="row"><span class="stance s-{e(t["stance"])}">{e(t["stance"][:4])}</span>'
                 f'<span class="rt">{e(t["title"])}</span></th>{cells}</tr>')
    return f'''<p class="muted">Each row is a thesis, each column a day. Shade is confidence (0–100). Marks: + new, ▲ stronger, ▼ weaker, × retired.</p>
<div class="grid-wrap" data-end><table class="grid"><thead><tr><th scope="col">Thesis</th>{head}</tr></thead><tbody>{body}</tbody></table></div>'''


SEG_SHORT = {"overweight": "OW", "neutral": "N", "underweight": "UW"}


def segment_grid_html(days, loaded, segments):
    by_day = {x["date"]: (x["w"] or {}).get("segments", {}) for x in loaded}
    head = "".join(f'<th scope="col"><span>{weekday(d)}</span>{d[5:]}</th>' for d in days)
    body = ""
    for s in segments:
        cells = ""
        for d in days:
            v = by_day[d].get(s)
            if not v:
                cells += '<td class="cell empty"></td>'
                continue
            st = v["stance"]
            cells += f'<td class="cell sg-{e(st)}" title="{e(d)}: {e(st)}. {e(v.get("note", ""))}">{SEG_SHORT.get(st, "?")}</td>'
        body += f'<tr><th scope="row"><span class="rt">{e(seg_label(s))}</span></th>{cells}</tr>'
    return f'''<p class="muted">OW overweight · N neutral · UW underweight. Hover or tap a cell for the day&#39;s note.</p>
<div class="grid-wrap" data-end><table class="grid seg-grid"><thead><tr><th scope="col">Segment</th>{head}</tr></thead><tbody>{body}</tbody></table></div>'''


def tracking_html(t):
    picks = (t or {}).get("picks", [])
    if not picks:
        return "<p class='muted'>No picks tracked yet.</p>"
    s, sc = t["summary"], t.get("scorecard", {})
    rows = "".join(f'<tr><td>{e(p["date"])}</td><td class="tk">{e(p["ticker"])}</td><td>{e(p.get("kind", "new"))}</td><td>{chip(p["rating"] or None)}</td><td class="n">{p["price"]}</td>'
                   f'<td class="n">{p["now"]}</td><td class="n {tone(p["return"])}">{pct(p["return"])}</td><td class="n {tone(p["vs_qqq"])}">{pct(p["vs_qqq"])}</td>'
                   f'<td class="n {tone(p["vs_smh"])}">{pct(p["vs_smh"])}</td><td>{"✓" if p["correct"] else "✗" if p["correct"] is False else "pending"}</td></tr>' for p in picks)
    cards = "".join(f'<div><span class="lbl">{e(k)}</span><strong>{pct(v["hit_rate"], False)}</strong><span class="muted">{v["graded"]} graded · {pct(v["avg_vs_qqq"])} vs QQQ</span></div>'
                    for k, v in sc.items()) or f'<p class="muted">Ratings are graded after {t["rules"]["grade_after_days"]} days. None are old enough yet.</p>'
    return f'''<p>{s["picks"]} new picks, {s["beating_qqq"]} beating QQQ since they were picked, average {pct(s["avg_vs_qqq"])} vs QQQ.</p>
<div class="score">{cards}</div>
<div class="tw"><table class="track"><thead><tr><th>Date</th><th>Ticker</th><th>Run</th><th>Rating</th><th>Then</th><th>Now</th><th>Return</th><th>vs QQQ</th><th>vs SMH</th><th>Rating right?</th></tr></thead><tbody>{rows}</tbody></table></div>'''


def review_html():
    """The latest monthly review, if any."""
    reviews = sorted((DATA / "reviews").glob("*.md"))
    if not reviews:
        return ""
    return f'<h3>Monthly review {e(reviews[-1].stem)}</h3><div class="prose">{render_md(reviews[-1].read_text())}</div>'


def day_cards_html(loaded):
    cards = []
    for x in reversed(loaded):
        w = x["w"] or {}
        counts = {k: sum(1 for t in w.get("theses", []) if t["change"] == k) for k in ("new", "stronger", "weaker")}
        moves = " · ".join(f"{n} {k}" for k, n in counts.items() if n) or "no thesis changes"
        tickers = "".join(f'<span class="tkr"><span class="tk">{e(r["ticker"])}</span>{chip(x["agents"].get(r["ticker"], {}).get("rating"))}</span>'
                          for r in x["runs"])
        mk = "".join(f'<span>{e(lbl)} <b class="{tone(x["market"].get(k, {}).get("chg_1d"))}">{pct(x["market"].get(k, {}).get("chg_1d"))}</b></span>'
                     for k, lbl in (("^GSPC", "S&P 500"), ("SMH", "SMH")) if k in x["market"])
        cards.append(f'''<a class="dcard" href="days/{x["date"]}.html">
  <p class="eyebrow">{weekday(x["date"])} · {x["date"]}</p>
  <p class="dh">{e(w.get("headline", "No worldview"))}</p>
  <p class="clamp">{e(w.get("regime", ""))}</p>
  <p class="lbl">{e(moves)}</p>
  <div class="tkrs">{tickers}</div>
  <div class="mk">{mk}</div>
</a>''')
    return f'<div class="dcards">{"".join(cards)}</div>'


def usage_html():
    rows = usage_rows()
    if not rows:
        return "<p class='muted'>No runs recorded yet. Each daily run adds a row once it finishes.</p>"
    num = lambda v: float(v) if v not in ("", None) else 0.0
    k = lambda v: f"{num(v) / 1000:,.0f}k" if v not in ("", None) else "–"

    def total(n):
        rs = rows[-n:]
        return {f: sum(num(r[f]) for r in rs) for f in ("claude_output", "claude_cache_read", "claude_cost_usd", "gemini_calls")}, len(rs)

    cards = ""
    for label, n in (("Last 5 runs", 5), ("Last 20 runs", 20)):
        t, got = total(n)
        cards += (f'<div><span class="lbl">{label} ({got})</span><strong>${t["claude_cost_usd"]:,.2f}</strong>'
                  f'<span class="muted">Claude {t["claude_output"] / 1000:,.0f}k out · {t["claude_cache_read"] / 1e6:,.1f}M cache read · Gemini {t["gemini_calls"]:,.0f} calls</span></div>')
    body = "".join(f'<tr><td>{e(r["date"])}</td><td class="n">{k(r["claude_input"])}</td><td class="n">{k(r["claude_output"])}</td>'
                   f'<td class="n">{k(r["claude_cache_read"])}</td><td class="n">{k(r["claude_cache_write"])}</td>'
                   f'<td class="n">{"$" + format(num(r["claude_cost_usd"]), ",.2f") if r["claude_cost_usd"] else "–"}</td>'
                   f'<td class="n">{r["gemini_calls"]}</td><td class="n">{k(r["gemini_input"])}</td><td class="n">{k(r["gemini_output"])}</td></tr>'
                   for r in reversed(rows[-20:]))
    return f'''<p class="muted">Tokens each daily run used. Claude figures come from the run's own session; the dollar figure is the API list-price equivalent,
which is not what a Claude plan charges, but it moves with your plan's usage limits. Most of the volume is cache reads: every step re-reads the conversation so far.</p>
<div class="score">{cards}</div>
<div class="tw"><table class="track"><thead><tr><th>Date</th><th>Claude in</th><th>Claude out</th><th>Cache read</th><th>Cache write</th><th>Cost equiv.</th>
<th>Gemini calls</th><th>Gemini in</th><th>Gemini out</th></tr></thead><tbody>{body}</tbody></table></div>'''


def landing_page(days, loaded, watch, track, segments):
    latest = loaded[-1]
    body = f'''{hero_html(latest["date"], days, loaded, watch, track)}
<main>
<section id="today"><h2>Today at a glance</h2>{glance_html(latest)}</section>
<section id="watchlist"><h2>Watchlist</h2>{board_html(watch, track)}</section>
<section id="worldview"><h2>Worldview over time</h2>{thesis_grid_html(days, loaded)}</section>
<section id="segments"><h2>Segment stance over time</h2>{segment_grid_html(days, loaded, segments)}</section>
<section id="track"><h2>Track record</h2>{tracking_html(track)}{review_html()}</section>
<section id="archive"><h2>Every day</h2>{day_cards_html(loaded)}</section>
<section id="usage"><h2>Usage</h2>{usage_html()}</section>
<footer><p>Sources: Yahoo Finance for news and prices; Claude for the worldview and picks; <a href="https://github.com/TauricResearch/TradingAgents" rel="noopener">TradingAgents</a> on Gemini for verification.
Code on <a href="{GITHUB}" rel="noopener">GitHub</a>.</p><p>{e(FOOTER)}</p></footer>
</main>
<script>{LAVA_JS}</script>'''
    return page("Gene Research", body, "", "Daily AI-bottleneck research diary: worldview by Claude, verification by TradingAgents.", cls="landing")


# ---------- shell ----------

def page(title, body, up, description="", cls="day"):
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title><meta name="description" content="{e(description or "")}">
<meta name="theme-color" content="#0b0405"><link rel="icon" href="{up}assets/logo.png">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@400;500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<link rel="stylesheet" href="{up}assets/site.css">
</head><body class="{cls}">{body}
<script>document.querySelectorAll("[data-end]").forEach(function(el){{el.scrollLeft=el.scrollWidth}})</script>
</body></html>'''


def main():
    days = sorted(p.stem for p in (DATA / "worldview").glob("*.json"))
    if not days:
        raise SystemExit("no worldviews yet")
    loaded = [load_day(d) for d in days]
    watch = watchlist.load()
    track = read_json(DATA / "tracking.json")
    from common import universe
    segments = list(universe()["segments"])
    (SITE / "days").mkdir(parents=True, exist_ok=True)
    (SITE / "assets").mkdir(parents=True, exist_ok=True)
    (SITE / "assets" / "site.css").write_text(CSS)
    for i, day in enumerate(loaded):
        prev_d = days[i - 1] if i else None
        next_d = days[i + 1] if i + 1 < len(days) else None
        (SITE / "days" / f"{day['date']}.html").write_text(day_page(day, prev_d, next_d, watch))
    (SITE / "index.html").write_text(landing_page(days, loaded, watch, track, segments))
    print(f"site: landing + {len(days)} day pages, latest = {days[-1]}")


# Lava lamp: metaballs drawn into a tiny canvas that CSS scales up (the upscale
# blurs it for free). ~30fps, paused off-screen, a single still frame for
# prefers-reduced-motion.
LAVA_JS = r"""
(function(){
var c=document.getElementById("lava");if(!c||!c.getContext)return;
var x=c.getContext("2d"),W=0,H=0,img=null,run=true,last=0,t0=performance.now();
var mq=window.matchMedia("(prefers-reduced-motion: reduce)");
var B=[[.18,.62,.24,.9,.07,.31,0],[.42,.35,.19,.6,.09,.23,1.7],[.70,.70,.27,.7,.05,.27,3.1],
       [.88,.30,.17,.5,.08,.35,4.4],[.55,.88,.21,.8,.06,.19,2.2],[.08,.20,.15,.6,.10,.29,5.3],[.32,.95,.16,.7,.07,.33,.9]];
function size(){var r=c.getBoundingClientRect(),s=150/Math.max(r.width,r.height,1);
  W=Math.max(16,Math.round(r.width*s));H=Math.max(16,Math.round(r.height*s));c.width=W;c.height=H;img=x.createImageData(W,H)}
function ss(a,b,v){v=(v-a)/(b-a);v=v<0?0:v>1?1:v;return v*v*(3-2*v)}
function frame(now){
  var t=(now-t0)/1000,m=Math.min(W,H),bl=[],i,px,py,k,f,dx,dy,o=0,d=img.data;
  for(i=0;i<B.length;i++){var b=B[i];
    bl.push([(b[0]+b[4]*Math.sin(t*b[5]*.35+b[6]))*W,(b[1]+b[3]*.22*Math.sin(t*b[5]*.22+b[6]*1.3))*H,(b[2]*m)*(b[2]*m)])}
  for(py=0;py<H;py++){var lift=.72+.42*py/H;
    for(px=0;px<W;px++){f=0;
      for(k=0;k<bl.length;k++){dx=px-bl[k][0];dy=py-bl[k][1];f+=bl[k][2]/(dx*dx+dy*dy+1)}
      var haze=ss(.25,.95,f),edge=ss(.92,1.12,f),core=ss(1.3,3.6,f);
      var r=11+52*haze,g=4+4*haze,bb=6+8*haze;
      r+=(150-r)*edge;g+=(14-g)*edge;bb+=(30-bb)*edge;
      r+=(222-r)*core*.85;g+=(36-g)*core*.85;bb+=(48-bb)*core*.85;
      d[o]=Math.min(255,r*lift);d[o+1]=g*lift;d[o+2]=bb*lift;d[o+3]=255;o+=4}}
  x.putImageData(img,0,0)}
function loop(now){if(!run||mq.matches)return;if(now-last>33){last=now;frame(now)}requestAnimationFrame(loop)}
function start(){if(mq.matches){frame(t0+12000);return}requestAnimationFrame(loop)}
size();frame(t0+12000);
window.addEventListener("resize",function(){size();frame(performance.now())});
if(mq.addEventListener)mq.addEventListener("change",start);
if("IntersectionObserver" in window)new IntersectionObserver(function(es){var v=es[0].isIntersecting;if(v&&!run){run=true;start()}else if(!v)run=false}).observe(c);
start();
})();
"""


CSS = r""":root{--bg:#f5f3f2;--surface:#fff;--ink:#1d1517;--muted:#6b5e61;--line:#e2dadb;--accent:#a3122a;--accent-ink:#fff;--pos:#17734a;--neg:#b0302b;
--buy:#17734a;--buy-bg:#e1f2e9;--ow:#3d7d2a;--ow-bg:#e8f2df;--hold:#7a6410;--hold-bg:#f6efd2;--uw:#a4520f;--uw-bg:#f9e8d8;--sell:#a8302b;--sell-bg:#f8e1df;
--display:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;--body:"Source Serif 4",Georgia,serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#0e0a0b;--surface:#181213;--ink:#ece4e5;--muted:#a3959a;--line:#2f2427;--accent:#ff5468;--accent-ink:#1a0306;--pos:#6fd3a0;--neg:#f08a84;
--buy:#6fd3a0;--buy-bg:#163a2a;--ow:#a3d483;--ow-bg:#24361a;--hold:#e3c95e;--hold-bg:#3a3214;--uw:#f0a466;--uw-bg:#40280f;--sell:#f08a84;--sell-bg:#421a18;color-scheme:dark}}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 var(--display)}
a{color:var(--accent)}img{display:block}
main{max-width:1080px;margin:0 auto;padding:36px max(16px,env(safe-area-inset-right)) 64px max(16px,env(safe-area-inset-left));display:flex;flex-direction:column;gap:44px}
h1,h2,h3{margin:0;text-wrap:balance}h1{font-size:2rem;line-height:1.15;max-width:32ch}
h2{font-size:1.4rem;border-bottom:2px solid var(--ink);padding-bottom:6px;margin-bottom:14px;display:flex;align-items:center;gap:10px}
h2::before{content:"";width:9px;height:9px;border-radius:50%;background:var(--accent);flex:none}
h3{font-size:1.08rem;margin:18px 0 8px}
section{display:flex;flex-direction:column;scroll-margin-top:16px;min-width:0}section>p{margin:0 0 10px}
.eyebrow,.lbl{font:0.72rem var(--mono);text-transform:uppercase;letter-spacing:.07em;color:var(--accent);margin:0}.lbl{color:var(--muted)}
.muted{color:var(--muted)}.small{font-size:.85rem;margin:0}.grow{flex:1}.cap{text-transform:capitalize}
.regime{font:1.05rem/1.6 var(--body);max-width:68ch;margin:0}

/* ---- hero (always dark) ---- */
.hero{position:relative;isolation:isolate;overflow:hidden;color:#fff;background:#0b0405 radial-gradient(60% 60% at 30% 70%,#5c0a16 0,transparent 70%),radial-gradient(45% 50% at 80% 30%,#4a0812 0,transparent 70%);
min-height:min(100svh,820px);display:flex}
#lava{position:absolute;inset:-2%;width:104%;height:104%;z-index:-2;display:block}
.veil{position:absolute;inset:0;z-index:-1;background:linear-gradient(180deg,rgba(8,2,3,.55) 0,rgba(8,2,3,0) 28%,rgba(8,2,3,0) 55%,rgba(8,2,3,.6) 100%),radial-gradient(70% 60% at 0 100%,rgba(8,2,3,.55),transparent 70%)}
.hero-in{width:100%;max-width:1240px;margin:0 auto;padding:28px max(20px,env(safe-area-inset-right)) 44px max(20px,env(safe-area-inset-left));display:flex;flex-direction:column;justify-content:space-between;gap:40px}
.hero-nav{display:flex;align-items:center;justify-content:space-between;gap:16px 28px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:10px;color:inherit;text-decoration:none}
.brand span{font:600 1.05rem var(--display);letter-spacing:.22em}
.brand img{filter:contrast(2.2);mix-blend-mode:screen;margin:-12px -8px -12px -14px}
.slim .brand img{margin:-8px -6px -8px -10px}
.hero nav{display:flex;flex-wrap:wrap;gap:6px 26px}
.hero nav a{color:rgba(255,255,255,.86);text-decoration:none;font-size:.95rem;padding:4px 0;border-bottom:1px solid transparent}
.hero nav a:hover{color:#fff;border-bottom-color:rgba(255,255,255,.7)}
.hero-body{display:flex;align-items:flex-end;justify-content:space-between;gap:36px 48px}
.hero-text{max-width:500px;display:flex;flex-direction:column;gap:26px;align-items:flex-start}
.hero-text p{margin:0;font:1.15rem/1.5 var(--display);color:rgba(255,255,255,.92);text-shadow:0 1px 18px rgba(0,0,0,.35)}
.pill{display:inline-flex;align-items:center;gap:14px;padding:7px 26px 7px 7px;border-radius:999px;background:#060203;color:#fff;text-decoration:none;font-weight:600;
box-shadow:0 0 0 1px rgba(255,80,96,.35),0 10px 30px rgba(0,0,0,.35);transition:box-shadow .2s}
.pill:hover{box-shadow:0 0 0 1px rgba(255,110,124,.8),0 10px 30px rgba(0,0,0,.45)}
.pill-dot{width:42px;height:42px;border-radius:50%;background:radial-gradient(circle at 38% 35%,#ff4d5e,#b3101f 55%,#5e0610);flex:none}
.stats{display:flex;flex-direction:column;gap:26px;text-align:right}
.stats div{display:flex;flex-direction:column}
.stats strong{font:500 3rem/1 var(--display);letter-spacing:-.01em;font-variant-numeric:tabular-nums}
.stats span{font-size:.95rem;color:rgba(255,255,255,.85);margin-top:4px}
@media(max-width:760px){
 .hero{min-height:auto}
 .hero-in{padding-top:20px;padding-bottom:32px;gap:56px}
 .hero-nav{flex-direction:column;align-items:flex-start;gap:14px}
 .brand span{font-size:.95rem}
 .hero nav{gap:4px 16px}.hero nav a{font-size:.88rem}
 .hero-body{flex-direction:column;align-items:stretch}
 .hero-text p{font-size:1.05rem}
 .stats{display:grid;grid-template-columns:1fr 1fr;gap:20px 16px;text-align:left;border-top:1px solid rgba(255,255,255,.22);padding-top:20px}
 .stats strong{font-size:2.1rem}.stats span{font-size:.85rem}
}

/* ---- day page header ---- */
.slim{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px max(16px,env(safe-area-inset-right)) 12px max(16px,env(safe-area-inset-left));
background:#0b0405;color:#fff;border-bottom:2px solid var(--accent)}
.slim .brand span{font-size:.85rem;letter-spacing:.2em}
.back{color:#fff;text-decoration:none;font-size:.9rem;opacity:.9}.back:hover{opacity:1;text-decoration:underline}
@media(max-width:400px){.slim .brand span{font-size:.75rem;letter-spacing:.14em}}
.top{display:flex;flex-direction:column;gap:12px}
.market{display:grid;grid-template-columns:repeat(auto-fill,minmax(118px,1fr));gap:6px;margin-top:6px}
.market div{background:var(--surface);border:1px solid var(--line);padding:6px 10px;display:flex;flex-direction:column}
.market strong{font-variant-numeric:tabular-nums;font-weight:500}.market .n{text-align:left;font:.8rem var(--mono)}
.pager{display:flex;justify-content:space-between;gap:10px;flex-wrap:wrap;border-top:1px solid var(--line);padding-top:16px}
.pager a,.pager span{font:.85rem var(--mono)}.pager .off{color:var(--muted);opacity:.6}

/* ---- worldview (day page) ---- */
.theses{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}.thesis{background:var(--surface);border:1px solid var(--line);padding:10px 14px}
.th-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}.th-top strong{flex:1 1 220px;font-size:1rem}
.stance,.chg,.chip{font:500 .7rem var(--mono);text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:2px;white-space:nowrap}
.s-bullish{color:var(--pos);background:var(--buy-bg)}.s-bearish{color:var(--neg);background:var(--sell-bg)}.s-neutral{color:var(--hold);background:var(--hold-bg)}
.chg{border:1px solid var(--line);color:var(--muted)}.c-new,.c-stronger{color:var(--accent);border-color:var(--accent)}.c-weaker,.c-retired{color:var(--uw);border-color:var(--uw)}
.conf{width:70px;height:6px;background:var(--line);display:inline-block}.conf span{display:block;height:100%;background:var(--accent)}.cn{font:.75rem var(--mono);color:var(--muted)}
.note{margin:6px 0 2px;font:.95rem/1.5 var(--body)}.segs{margin:0;font:.72rem var(--mono);color:var(--muted)}
.segrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}.seg{background:var(--surface);border:1px solid var(--line);padding:9px 12px;border-top:3px solid var(--line)}
.seg p{margin:4px 0 0;font-size:.85rem;color:var(--muted)}.sg{font-weight:600;text-transform:capitalize}.sv{float:right;font:.7rem var(--mono);text-transform:uppercase}
.st-overweight{border-top-color:var(--pos)}.st-overweight .sv{color:var(--pos)}.st-underweight{border-top-color:var(--neg)}.st-underweight .sv{color:var(--neg)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:640px){.two{grid-template-columns:1fr}}.plain{margin:0;padding-left:18px;font:.95rem/1.5 var(--body)}

/* ---- analysis (day page) ---- */
.picks{display:flex;flex-direction:column;gap:16px}.pick{background:var(--surface);border:1px solid var(--line);padding:16px;display:flex;flex-direction:column;gap:10px;min-width:0;scroll-margin-top:16px}
.pick header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.pick h3{font:600 1.8rem var(--mono);margin:0}.pick p{margin:0;font:.98rem/1.55 var(--body);max-width:70ch}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0}.facts div{display:flex;flex-direction:column}.facts dt{font:.68rem var(--mono);text-transform:uppercase;color:var(--muted)}.facts dd{margin:0;font-variant-numeric:tabular-nums}
.chain{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:10px 0;border-block:1px solid var(--line)}.chain div{display:flex;flex-direction:column;gap:4px}.arr{color:var(--muted)}.chip.big{font-size:.9rem}
.r-buy{color:var(--buy);background:var(--buy-bg)}.r-overweight{color:var(--ow);background:var(--ow-bg)}.r-hold{color:var(--hold);background:var(--hold-bg)}.r-underweight{color:var(--uw);background:var(--uw-bg)}.r-sell{color:var(--sell);background:var(--sell-bg)}.r-n\/a{color:var(--muted);border:1px solid var(--line)}
.agents{display:flex;flex-direction:column;gap:4px}details{border:1px solid var(--line)}summary{cursor:pointer;padding:7px 12px;font-weight:600}details[open] summary{border-bottom:1px solid var(--line)}
.prose{font:.98rem/1.6 var(--body);padding:4px 16px 12px;max-width:70ch;overflow-wrap:anywhere}.prose h1,.prose h2,.prose h3,.prose h4{font:600 1rem var(--display);border:0;margin:14px 0 4px;display:block}.prose h2::before{display:none}
.tw{overflow-x:auto;max-width:100%}table{border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:5px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{border-bottom-color:var(--ink)}
.prose td{white-space:normal;min-width:8ch}
.n{text-align:right}.tk{font-family:var(--mono);font-weight:500}.tk.big{font-size:1.35rem;font-weight:600}.pos{color:var(--pos)}.neg{color:var(--neg)}
.score{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}.score div{background:var(--surface);border:1px solid var(--line);padding:8px 12px;display:flex;flex-direction:column;min-width:150px}.score strong{font-size:1.4rem}
.kind{font:500 .68rem var(--mono);text-transform:uppercase;letter-spacing:.06em;padding:2px 6px;border:1px solid var(--line);color:var(--muted);white-space:nowrap}.kind.new{color:var(--accent);border-color:var(--accent)}
.action{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0}.action div{background:var(--bg);padding:8px 10px;border:1px solid var(--line)}.action dt{font:.68rem var(--mono);text-transform:uppercase;color:var(--muted)}.action dd{margin:2px 0 0;font-weight:600}
@media(max-width:520px){.action{grid-template-columns:1fr}}.models{font:.75rem var(--mono)!important;color:var(--muted)}
.howto{margin-bottom:14px;background:var(--surface)}.howto .prose{max-width:none}

/* ---- landing sections ---- */
.headline{font:600 1.45rem/1.3 var(--display);margin:4px 0 16px;max-width:46ch;text-wrap:balance}
.runs,.board{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.run,.wcard,.dcard{background:var(--surface);border:1px solid var(--line);padding:14px 16px;display:flex;flex-direction:column;gap:10px;color:inherit;text-decoration:none;min-width:0}
a.run,a.dcard{transition:border-color .15s,transform .15s}a.run:hover,a.dcard:hover{border-color:var(--accent)}
.run-top{display:flex;align-items:center;gap:10px}
.more{font-weight:600;text-decoration:none}.more:hover{text-decoration:underline}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font:.72rem var(--mono);color:var(--muted);margin-bottom:10px}.legend span{display:inline-flex;align-items:center;gap:5px}
.dots{display:flex;flex-wrap:wrap;gap:5px}.dot{width:12px;height:12px;border-radius:50%;display:inline-block;background:var(--line)}
.d-buy{background:var(--buy)}.d-overweight{background:var(--ow)}.d-hold{background:var(--hold)}.d-underweight{background:var(--uw)}.d-sell{background:var(--sell)}
.nums,.mini{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0}.nums dt,.mini dt{font:.66rem var(--mono);text-transform:uppercase;color:var(--muted)}
.nums dd{margin:0;font:500 1.25rem var(--display);font-variant-numeric:tabular-nums}.mini dd{margin:2px 0 0;font-size:.88rem}
.dropped{margin-top:12px;background:var(--surface)}.dropped ul{padding:10px 12px 10px 30px}
.grid-wrap{overflow-x:auto;width:fit-content;max-width:100%;border:1px solid var(--line);background:var(--surface);-webkit-overflow-scrolling:touch}
.grid{border-collapse:separate;border-spacing:0;width:max-content}
.grid th,.grid td{border-bottom:1px solid var(--line)}.grid tr:last-child>*{border-bottom:0}
.grid thead th{font:.68rem var(--mono);text-transform:uppercase;color:var(--muted);text-align:center;padding:8px 6px;border-bottom-color:var(--ink)}
.grid thead th span{display:block;opacity:.7}.grid thead th:first-child{text-align:left}
.grid th[scope=row],.grid thead th:first-child{position:sticky;left:0;background:var(--surface);z-index:1;border-right:1px solid var(--line);text-align:left;white-space:normal;
width:300px;min-width:300px;max-width:300px;padding:8px 12px;font-weight:500}
.grid th[scope=row]{display:table-cell}.grid th[scope=row] .stance{margin-right:8px;font-size:.62rem;padding:1px 5px;vertical-align:1px}
.rt{font-size:.9rem;line-height:1.3}
.cell{width:62px;min-width:62px;text-align:center;font:500 .8rem var(--mono);padding:8px 4px;
background:color-mix(in srgb,var(--accent) var(--c,0%),var(--surface));color:var(--ink);position:relative;border-left:1px solid var(--surface)}
.cell.hi{color:#fff}.cell.ret{opacity:.45}.cell i{font-style:normal;font-size:.68rem;margin-left:3px}.cell.empty{background:var(--surface)}
.sg-overweight{background:var(--buy-bg);color:var(--pos)}.sg-neutral{background:var(--bg);color:var(--muted)}.sg-underweight{background:var(--sell-bg);color:var(--neg)}
.seg-grid th[scope=row],.seg-grid thead th:first-child{width:200px;min-width:200px;max-width:200px}
@media(max-width:600px){.grid th[scope=row],.grid thead th:first-child{width:170px;min-width:170px;max-width:170px;padding:8px}.rt{font-size:.82rem}
 .seg-grid th[scope=row],.seg-grid thead th:first-child{width:140px;min-width:140px;max-width:140px}
 .grid th[scope=row] .stance{display:block;width:max-content;margin:0 0 3px}}
.dcards{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.dh{font:600 1.08rem/1.3 var(--display);margin:0}.clamp{margin:0;font:.92rem/1.5 var(--body);color:var(--muted);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.tkrs{display:flex;flex-wrap:wrap;gap:6px 12px}.tkr{display:inline-flex;align-items:center;gap:6px}
.mk{display:flex;gap:16px;font:.78rem var(--mono);color:var(--muted);border-top:1px solid var(--line);padding-top:8px;margin-top:auto}.mk b{font-weight:500}
footer{font:.88rem/1.5 var(--body);color:var(--muted);max-width:70ch;border-top:1px solid var(--line);padding-top:16px}footer p{margin:0 0 8px}
a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}.hero a:focus-visible{outline-color:#fff}
@media(max-width:400px){main{gap:36px}.runs,.board,.dcards{grid-template-columns:1fr}h1{font-size:1.6rem}.headline{font-size:1.25rem}}
"""

if __name__ == "__main__":
    main()
