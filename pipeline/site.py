"""Stage 7: render the static site into site/ from the files under data/.

site/index.html          landing page: hero + overview across every day
site/days/<date>.html    one in-depth page per day
site/assets/site.css     shared stylesheet (written here)
site/assets/logo.png     the helix logo (checked in)
site/news/<date>.json    that day's articles, loaded on demand by the landing page's news archive

Pure code: Vercel serves the folder as-is, nothing is built there.
"""

import csv
import html
import json
import re
import urllib.parse
from datetime import date as Date

from markdown_it import MarkdownIt

import watchlist
from digest import RELEVANT
from constants.market import ACTIONS, MACRO_NAMES
from utils.common import DATA, SITE, read_json, segment_of, universe, write_json
from utils.text import clean_report

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
    if not rating:  # skipped by the daily TradingAgents cap, or failed
        return f'<span class="{cls} r-n/a" title="No TradingAgents rating: the run was skipped or failed">not run</span>'
    return f'<span class="{cls} r-{e(rating.lower())}">{e(rating)}</span>'


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
        "news": load_news(d, w),
        "brief": read_json(folder / "brief.json"),
        "brief_usage": ((read_json(folder / "usage.json", {}) or {}).get("claude") or {}).get("brief")
                       or (read_json(folder / "brief_meta.json", {}) or {}).get("usage"),
    }


NEWS_ORDER = ["market_macro"]  # then the universe segments, then "other"


def load_news(d, w):
    """The day's articles, tagged with segment, whether the digest kept them, and whether the worldview cites them."""
    path = DATA / d / "news.jsonl"
    if not path.exists():
        return []
    seg_of = segment_of()
    cited = set(re.findall(r"\(([0-9a-f]{12})\)", json.dumps((w or {}).get("theses", []))))
    out = []
    for line in open(path):
        it = json.loads(line)
        out.append({**it, "segment": seg_of.get(it["tickers"][0], "other") if it.get("tickers") else "market_macro",
                    "kept": bool(it.get("tickers") or RELEVANT.search(f"{it['title']} {it.get('summary', '')}")),
                    "cited": it.get("id") in cited})
    return out


def publisher(it):
    """The feed is Yahoo's, so name the outlet from the article's own link."""
    host = re.sub(r"^www\.", "", urllib.parse.urlparse(it.get("link") or "").netloc)
    return "Yahoo Finance" if host.endswith("yahoo.com") or not host else host


def news_item_html(it):
    when = (it.get("published") or "")[11:16]
    tick = "".join(f'<span class="tk">{e(t)}</span>' for t in it.get("tickers", []))
    summ = it.get("summary") or ""
    summ = summ[:220].rsplit(" ", 1)[0] + "…" if len(summ) > 220 else summ
    return (f'<li class="news{" cited" if it["cited"] else ""}"><div class="nh"><span class="nt">{e(when)}</span>'
            f'<a href="{e(it["link"])}" rel="noopener" target="_blank">{e(it["title"])}</a></div>'
            f'<div class="nm">{tick}<span class="muted">{e(publisher(it))}</span>{"<span class=cite>cited in worldview</span>" if it["cited"] else ""}</div>'
            + (f'<p>{e(summ)}</p>' if summ and summ != it["title"] else "") + '</li>')


def news_html(items, segments):
    if not items:
        return "<p class='muted'>No news stored for this day.</p>"
    kept = [it for it in items if it["kept"]]
    groups = []
    for g in NEWS_ORDER + segments + ["other"]:
        its = sorted((it for it in kept if it["segment"] == g), key=lambda it: not it["cited"])
        if its:
            n_cited = sum(it["cited"] for it in its)
            groups.append(f'<details class="ngroup"{" open" if n_cited else ""}><summary>{e(seg_label(g) if g in segments else g.replace("_", " ").capitalize())}'
                          f' <span class="muted">{len(its)}{f" · {n_cited} cited" if n_cited else ""}</span></summary><ul class="nlist">{"".join(map(news_item_html, its))}</ul></details>')
    dropped = [it for it in items if not it["kept"]]
    if dropped:
        groups.append(f'<details class="ngroup"><summary>Off-topic <span class="muted">{len(dropped)} · left out of the digest</span></summary>'
                      f'<ul class="nlist">{"".join(map(news_item_html, dropped))}</ul></details>')
    return (f'<p class="muted">Every article the pipeline pulled for this day, grouped by segment. Claude read the {len(kept)} on-topic ones as one-line '
            f'summaries; the ones marked <span class="cite">cited in worldview</span> are the evidence behind a thesis.</p>{"".join(groups)}')


def news_json(items):
    """Compact per-day file the landing page's news archive loads on demand."""
    return [{"i": it.get("id"), "t": it["title"], "l": it["link"], "s": publisher(it), "p": it.get("published"),
             "k": it.get("tickers", []), "g": it["segment"], "c": int(it["cited"]), "r": int(it["kept"]),
             "m": (it.get("summary") or "")[:220]} for it in items]


def usage_rows():
    path = DATA / "usage.csv"
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


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


def day_page(day, prev_d, next_d, watch, segments):
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
{f'<section id="brief"><h2>Before the open</h2>{brief_html(day, "../")}</section>' if day.get("brief") else ""}
<section id="news"><h2>News ({sum(it["kept"] for it in day["news"])})</h2>{news_html(day["news"], segments)}</section>
{pager}
<footer>{e(FOOTER)}</footer>
</main>'''
    return page(f"Gene Research · {d}", body, "../", d and (w or {}).get("headline", ""))


def skip_reason(a):
    r = a.get("error") or a.get("skipped") or "no result"
    if r.startswith("over --max"):
        return f"the daily cap of {r.split()[-1]} TradingAgents runs (Gemini free tier) was used by the earlier names"
    return r


LEANS = {"wait": "Wait a session", "small": "Small positions only", "stands": "Ratings still stand"}


def lean_chip(b):
    lean = b.get("lean", "")
    return f'<span class="lean l-{e(lean)}">{e(LEANS.get(lean, lean))}</span>'


def brief_usage_line(u, rates):
    if not u:
        return ""
    cost = sum((u.get(k) or 0) * rates.get(r, 0) for k, r in (("input_tokens", "input"), ("output_tokens", "output"),
               ("cache_read_tokens", "cache_read"), ("cache_write_tokens", "cache_write"))) / 1e6 if rates else None
    return (f'{u.get("model_calls", 0)} Claude calls, {(u.get("cache_read_tokens") or 0) / 1e6:,.1f}M tokens read from cache, '
            f'{(u.get("output_tokens") or 0) / 1e3:,.0f}k written' + (f' (≈${cost:,.2f} at API prices)' if cost is not None else ""))


def brief_html(day, up=""):
    b = day["brief"]
    names = ""
    for x in b.get("names", []):
        since = x.get("since_rated")
        price = (f'rated {e(x.get("rated_on", ""))} at {x["rated_price"]:,.2f}' if isinstance(x.get("rated_price"), (int, float)) else f'rated {e(x.get("rated_on", ""))}')
        last = (f' · last close {x["last_price"]:,.2f} <b class="{tone(since)}">({pct(since)})</b>' if isinstance(x.get("last_price"), (int, float)) else "")
        cat = f'<p class="cat">{e(x["catalyst"])}</p>' if x.get("catalyst") else ""
        names += f'''<div class="bname">
  <div class="run-top"><span class="tk big">{e(x.get("ticker", ""))}</span><span class="grow"></span>{chip(x.get("rating"))}</div>
  <p class="muted small">{price}{last}</p>{cat}
  <p class="take">{e(x.get("take", ""))}</p>
</div>'''
    lis = lambda xs: "".join(f"<li>{e(t)}</li>" for t in xs)
    srcs = "".join(f'<li><a href="{e(s["url"])}" rel="noopener">{e(s["title"])}</a></li>' for s in b.get("sources", []))
    written = b.get("written_at", "")[:16].replace("T", " ")
    rates = (read_json(DATA.parent / "plan.json", {}) or {}).get("api_rates_usd_per_mtok") or {}
    usage = brief_usage_line(day.get("brief_usage"), rates)
    meta = " · ".join(x for x in (f"Written {e(written)} SGT" if written else "", e(b.get("note", "")), f"This brief used {usage}" if usage else "") if x)
    return f'''<div class="brief">
<div class="brief-head"><span class="eyebrow">{e(b.get("session", ""))}</span>{lean_chip(b)}</div>
<p class="bl">{e(b.get("bottom_line", ""))}</p>
<div class="two"><div><h3>What changed since the ratings</h3><ul class="plain">{lis(b.get("what_changed", []))}</ul></div>
<div><h3>If you still buy</h3><ul class="plain">{lis(b.get("if_buying", []))}</ul></div></div>
{f'<div class="bnames">{names}</div>' if names else '<p class="muted">Nothing on the watchlist is rated Buy or Overweight.</p>'}
<p class="trust"><strong>How far to trust the ratings.</strong> {e(b.get("trust", ""))}</p>
{f'<details class="srcs"><summary>Sources ({len(b.get("sources", []))})</summary><ul class="plain">{srcs}</ul></details>' if srcs else ""}
<p class="muted small">{meta}. A read on the site&#39;s own ratings by Claude, not financial advice.</p>
</div>'''


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
        act = action_html(rating) if rating else f'<p class="muted">Not run: {e(skip_reason(a))}</p>'
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


def baselines_html(t):
    b = (t or {}).get("baselines")
    if not b or not b.get("pick_days"):
        return ""
    st = b["strategies"]
    ranked = sorted((v for v in st.values() if v["avg_return"] is not None), key=lambda v: -v["avg_return"])
    rows = "".join(f'<tr class="{"me" if v["label"] in (st["picks"]["label"], st["ta_positive"]["label"]) else ""}"><td>{e(v["label"])}</td>'
                   f'<td class="n {tone(v["avg_return"])}">{pct(v["avg_return"])}</td><td class="n {tone(v.get("avg_vs_qqq"))}">{pct(v.get("avg_vs_qqq"))}</td>'
                   f'<td class="n">{v["days"]}</td></tr>' for v in ranked)
    verdict = ("Too early to tell: give it about three months of picks before reading anything into this."
               if b["pick_days"] < 60 else "")
    return f'''<h3>Is the AI adding anything?</h3>
<p class="muted">Each strategy "buys" on the days a pick was made, at that day's close, and holds to today. If Claude's picks don't beat the screen's #1
(no AI) and the random shortlist pick over time, the AI steps aren't adding value; if the Buy / Overweight picks don't beat the rest, treat
TradingAgents' ratings as commentary rather than signals. {verdict}</p>
<div class="tw"><table class="track"><thead><tr><th>Strategy</th><th>Avg return</th><th>vs QQQ</th><th>Pick days</th></tr></thead><tbody>{rows}</tbody></table></div>'''


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
{baselines_html(t)}
<h3>Every pick and re-check</h3>
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
  {lean_chip(x["brief"]) if x.get("brief") else ""}
  <div class="mk">{mk}</div>
</a>''')
    return f'<div class="dcards">{"".join(cards)}</div>'


def news_archive_html(loaded):
    counts = {}
    for day in loaded:
        for it in day["news"]:
            if it["kept"]:
                for t in it.get("tickers", []):
                    counts[t] = counts.get(t, 0) + 1
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:16]
    chips = "".join(f'<button type="button" class="tchip" data-q="{e(t)}">{e(t)} <span>{n}</span></button>' for t, n in top)
    total = sum(it["kept"] for day in loaded for it in day["news"])
    return f'''<p class="muted">{total:,} on-topic articles across {len(loaded)} days. The newest week loads first; search covers what is loaded.</p>
<div class="nfilters"><input id="nq" type="search" placeholder="Search headlines or a ticker" aria-label="Search news">
<label><input id="ncited" type="checkbox"> Only cited in a worldview</label></div>
<div class="tchips" aria-label="Most-mentioned tickers">{chips}</div>
<ul id="nresults" class="nlist"><li class="muted">Loading…</li></ul>
<button id="nmore" type="button" class="pill-sm" hidden>Load 7 more days</button>
<script>{NEWS_JS}</script>'''


def usage_html():
    rows = usage_rows()
    if not rows:
        return "<p class='muted'>No runs recorded yet. Each daily run adds a row once it finishes.</p>"
    num = lambda v: float(v) if v not in ("", None) else None
    plan = read_json(DATA.parent / "plan.json", {})

    def avg(field):
        vals = [x for x in (num(r.get(field)) for r in rows) if x is not None]
        return sum(vals) / len(vals) if vals else None

    def fmt(x, unit=""):
        if x is None:
            return "–"
        return f"{x / 1e6:,.1f} million{unit}" if x >= 1e6 else f"{x / 1e3:,.0f} thousand{unit}" if x >= 1e3 else f"{x:,.0f}{unit}"

    calls, read, wrote, cached = avg("claude_calls"), avg("claude_cache_read"), avg("claude_output"), avg("claude_cache_write")
    rates = plan.get("api_rates_usd_per_mtok") or {}

    def cost(r):
        """API-equivalent cost of one run from its token counts and the list prices in plan.json."""
        parts = [(r.get("claude_input"), "input"), (r.get("claude_output"), "output"),
                 (r.get("claude_cache_read"), "cache_read"), (r.get("claude_cache_write"), "cache_write")]
        if not rates or num(r.get("claude_cache_read")) is None:
            return None
        return sum((num(v) or 0) * rates.get(k, 0) for v, k in parts) / 1e6

    def brief_cost(r):
        """API-equivalent cost of the brief inside a run (already part of cost(r))."""
        if not rates or num(r.get("brief_cache_read")) is None:
            return None
        return sum((num(r.get(f"brief_{k}")) or 0) * rates.get(k, 0) for k in ("input", "output", "cache_read", "cache_write")) / 1e6

    briefs = [c for c in map(brief_cost, rows) if c is not None]
    brief_avg = sum(briefs) / len(briefs) if briefs else None
    costs = [c for c in map(cost, rows) if c is not None]
    run_cost = sum(costs) / len(costs) if costs else None
    g_calls, g_in, g_out = avg("gemini_calls"), avg("gemini_input"), avg("gemini_output")
    runs_week = plan.get("runs_per_week", 5)
    per_run = plan.get("weekly_limit_pct_per_run")
    if per_run:
        share = (f'<p class="big-share"><strong>{per_run * runs_week:,.0f}%</strong> of your weekly {e(plan.get("plan", ""))} limit goes to the '
                 f'{runs_week} weekday runs ({per_run:g}% each, measured once on claude.ai). That leaves about {max(0, 100 - per_run * runs_week):,.0f}% '
                 f'of each week for everything else; a month of runs is about {per_run * runs_week * 52 / 12:,.0f} weekly-limit percentage points.</p>')
    else:
        share = ('<p class="callout"><strong>Share of your plan: not measured yet.</strong> Anthropic doesn\'t publish Claude plan limits as token counts, '
                 'so this page can\'t work out the percentage from tokens alone. To measure it once: on claude.ai open Settings → Usage just before a '
                 'daily run (19:54 Singapore time) and again after it finishes, and put the difference in <code>plan.json</code> as '
                 '<code>weekly_limit_pct_per_run</code>. This section then shows your weekly and monthly share.</p>')
    month = lambda x: None if x is None else x * runs_week * 52 / 12
    money = ""
    if run_cost is not None:
        money = (f'<p class="big-share"><strong>${run_cost:,.2f}</strong> per run at API list prices, so about '
                 f'<strong>${month(run_cost):,.0f}</strong> a month and ${month(run_cost) * 12:,.0f} a year for weekday runs. '
                 f'A Claude plan doesn\'t bill per token; this is what the same usage would cost on the API, and the best single number '
                 f'for comparing runs and spotting when a change makes them more expensive. Most of it is cache reads '
                 f'(${(read or 0) * rates.get("cache_read", 0) / 1e6:,.2f} a run) and cache writes '
                 f'(${(cached or 0) * rates.get("cache_write", 0) / 1e6:,.2f}).</p>')
    body = "".join(f'<tr><td>{e(r["date"])}</td><td class="n">{"$" + format(cost(r), ".2f") if cost(r) is not None else "–"}</td><td class="n">{r.get("claude_calls") or "–"}</td><td class="n">{fmt(num(r["claude_cache_read"]))}</td>'
                   f'<td class="n">{fmt(num(r["claude_output"]))}</td><td class="n">{fmt(num(r["claude_cache_write"]))}</td>'
                   f'<td class="n">{"$" + format(brief_cost(r), ".2f") if brief_cost(r) is not None else "–"}</td>'
                   f'<td class="n">{r["gemini_calls"] or "–"}</td><td class="n">{fmt(num(r["gemini_input"]))} / {fmt(num(r["gemini_output"]))}</td></tr>'
                   for r in reversed(rows[-20:]))
    return f'''{money}{share}
<h3>What one daily run uses, on average ({len(rows)} run{"s" if len(rows) != 1 else ""} recorded)</h3>
<ul class="plain usage-list">
<li><strong>Claude{f": about {calls:,.0f} calls" if calls else ""}.</strong> Each call re-sends the whole conversation so far. Claude reads most of that back
from its cache: about <strong>{fmt(read, " tokens")}</strong> per run. Cached reads are much cheaper than fresh input, but they still count towards
plan limits, and they are where nearly all the volume is. Fewer steps per run is the main way to cut them.</li>
<li><strong>Claude's own writing</strong> (the worldview, the picks and its commands): about <strong>{fmt(wrote, " tokens")}</strong> per run,
plus about {fmt(cached, " tokens")} newly stored in the cache.</li>
<li><strong>Tonight&#39;s brief</strong> (the pre-open check, with a few web searches) is part of the Claude figures above:
{f"about <strong>${brief_avg:,.2f}</strong> of each run at API prices, over {len(briefs)} run{'s' if len(briefs) != 1 else ''}" if brief_avg is not None else "not measured yet; runs from 30 Oct on record it separately"}.</li>
<li><strong>Gemini</strong> runs TradingAgents: about {g_calls or 0:,.0f} calls, {fmt(g_in, " tokens")} in and {fmt(g_out, " tokens")} out per run.
That is on the free Google API key and does not count against your Claude plan.</li>
</ul>
<p class="muted">A month of weekday runs (about {runs_week * 52 / 12:,.0f}) comes to roughly {fmt(month(read), " tokens")} of Claude cache reads and
{fmt(month(wrote), " tokens")} written.</p>
<div class="tw"><table class="track"><thead><tr><th>Date</th><th>API-equiv. cost</th><th>Claude calls</th><th>Read from cache</th><th>Written</th><th>Newly cached</th>
<th>of which brief</th><th>Gemini calls</th><th>Gemini in / out</th></tr></thead><tbody>{body}</tbody></table></div>'''


def landing_page(days, loaded, watch, track, segments):
    latest = loaded[-1]
    body = f'''{hero_html(latest["date"], days, loaded, watch, track)}
<main>
<section id="today"><h2>Today at a glance</h2>{glance_html(latest)}</section>
<section id="watchlist"><h2>Watchlist</h2>{board_html(watch, track)}</section>
{f'<section id="tonight"><h2>Before tonight&#39;s open</h2>{brief_html(latest)}</section>' if latest.get("brief") else ""}
<section id="worldview"><h2>Worldview over time</h2>{thesis_grid_html(days, loaded)}</section>
<section id="segments"><h2>Segment stance over time</h2>{segment_grid_html(days, loaded, segments)}</section>
<section id="track"><h2>Track record</h2>{tracking_html(track)}{review_html()}</section>
<section id="archive"><h2>Every day</h2>{day_cards_html(loaded)}</section>
<section id="news"><h2>News archive</h2>{news_archive_html(loaded)}</section>
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
    segments = list(universe()["segments"])
    (SITE / "days").mkdir(parents=True, exist_ok=True)
    (SITE / "assets").mkdir(parents=True, exist_ok=True)
    (SITE / "assets" / "site.css").write_text(CSS)
    for i, day in enumerate(loaded):
        prev_d = days[i - 1] if i else None
        next_d = days[i + 1] if i + 1 < len(days) else None
        (SITE / "days" / f"{day['date']}.html").write_text(day_page(day, prev_d, next_d, watch, segments))
        write_json(SITE / "news" / f"{day['date']}.json", news_json(day["news"]))
    write_json(SITE / "news" / "index.json", [{"date": d["date"], "n": sum(it["kept"] for it in d["news"])} for d in reversed(loaded)])
    (SITE / "index.html").write_text(landing_page(days, loaded, watch, track, segments))
    print(f"site: landing + {len(days)} day pages, latest = {days[-1]}")


# News archive: loads per-day JSON newest first, a week at a time; filters what is loaded.
NEWS_JS = r"""
(function(){
var list=document.getElementById("nresults"),q=document.getElementById("nq"),only=document.getElementById("ncited"),more=document.getElementById("nmore");
if(!list)return;var days=[],next=0,items=[];
function esc(s){return String(s||"").replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]})}
function render(){var t=(q.value||"").trim().toLowerCase(),out=[];
for(var i=0;i<items.length&&out.length<300;i++){var it=items[i];if(!it.r)continue;if(only.checked&&!it.c)continue;
if(t&&(it.t+" "+it.k.join(" ")+" "+it.m).toLowerCase().indexOf(t)<0)continue;
out.push('<li class="news'+(it.c?' cited':'')+'"><div class="nh"><span class="nt">'+esc(it.day.slice(5))+'</span><a href="'+esc(it.l)+'" rel="noopener" target="_blank">'+esc(it.t)+'</a></div><div class="nm">'+
it.k.map(function(k){return'<span class="tk">'+esc(k)+'</span>'}).join("")+'<span class="muted">'+esc(it.s)+'</span>'+(it.c?'<span class="cite">cited in worldview</span>':'')+
' <a class="muted" href="days/'+it.day+'.html#news">day page</a></div></li>')}
list.innerHTML=out.join("")||'<li class="muted">No matching articles in the loaded days.</li>';more.hidden=next>=days.length}
function load(n){var batch=days.slice(next,next+n);next+=batch.length;
Promise.all(batch.map(function(d){return fetch("news/"+d.date+".json").then(function(r){return r.ok?r.json():[]}).then(function(a){a.forEach(function(it){it.day=d.date});return a}).catch(function(){return[]})}))
.then(function(all){all.forEach(function(a){items=items.concat(a)});render()})}
fetch("news/index.json").then(function(r){return r.json()}).then(function(d){days=d;load(7)}).catch(function(){list.innerHTML='<li class="muted">News could not be loaded.</li>'});
q.addEventListener("input",render);only.addEventListener("change",render);more.addEventListener("click",function(){load(7)});
document.querySelectorAll(".tchip").forEach(function(b){b.addEventListener("click",function(){q.value=b.dataset.q;render()})});
})();
"""


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

.ngroup{border:1px solid var(--line);background:var(--surface);margin-top:8px}.ngroup>summary{cursor:pointer;padding:9px 14px;font-weight:600}
.nlist{list-style:none;margin:0;padding:0}.ngroup .nlist{border-top:1px solid var(--line)}
.news{padding:10px 14px;border-bottom:1px solid var(--line);min-width:0}.news:last-child{border-bottom:0}.news.cited{box-shadow:inset 3px 0 0 var(--accent)}
.nh{display:flex;gap:10px;align-items:baseline}.nh a{color:var(--ink);font-weight:600;text-decoration:none;overflow-wrap:anywhere}.nh a:hover{text-decoration:underline}
.nt{font:.72rem var(--mono);color:var(--muted);flex:none;min-width:3.2em}
.nm{display:flex;flex-wrap:wrap;gap:6px 10px;align-items:center;margin-top:4px;font-size:.8rem}.nm .tk{font:500 .72rem var(--mono);color:var(--accent)}
.news p{margin:4px 0 0;font:.9rem/1.5 var(--body);color:var(--muted);max-width:75ch}
.cite{font:500 .66rem var(--mono);text-transform:uppercase;letter-spacing:.05em;color:var(--accent);border:1px solid var(--accent);padding:1px 5px}
.nfilters{display:flex;flex-wrap:wrap;gap:10px 18px;align-items:center;margin:10px 0}
.nfilters input[type=search]{flex:1 1 260px;font:inherit;padding:8px 12px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:999px}
.tchips{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px}.tchip{font:500 .75rem var(--mono);border:1px solid var(--line);background:var(--surface);color:var(--ink);padding:3px 9px;border-radius:999px;cursor:pointer}
.tchip span{color:var(--muted)}.tchip:hover{border-color:var(--accent)}#nresults{border:1px solid var(--line);background:var(--surface);max-height:640px;overflow:auto}
.pill-sm{margin-top:10px;font:600 .85rem var(--display);padding:8px 16px;border-radius:999px;border:1px solid var(--accent);background:transparent;color:var(--accent);cursor:pointer}
tr.me td{font-weight:600}tr.me td:first-child{box-shadow:inset 3px 0 0 var(--accent)}
.callout{border:1px solid var(--line);border-left:3px solid var(--accent);background:var(--surface);padding:12px 16px;font:.95rem/1.55 var(--body);max-width:75ch}
.callout code{font:.85em var(--mono)}.big-share{font:1.05rem/1.5 var(--body);max-width:75ch}.big-share strong{font:600 1.8rem var(--display);color:var(--accent)}
.usage-list{display:flex;flex-direction:column;gap:8px;max-width:75ch}
.brief{background:var(--surface);border:1px solid var(--line);border-top:3px solid var(--accent);padding:16px;display:flex;flex-direction:column;gap:12px;min-width:0}
.brief h3{margin:4px 0 6px}.brief-head{display:flex;align-items:center;justify-content:space-between;gap:8px 12px;flex-wrap:wrap}
.bl{font:600 1.15rem/1.4 var(--display);margin:0;max-width:62ch;text-wrap:pretty}
.lean{font:600 .72rem var(--mono);text-transform:uppercase;letter-spacing:.05em;padding:4px 10px;border-radius:999px;white-space:nowrap;width:max-content}
.l-wait{color:var(--uw);background:var(--uw-bg)}.l-small{color:var(--hold);background:var(--hold-bg)}.l-stands{color:var(--buy);background:var(--buy-bg)}
.bnames{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
.bname{border:1px solid var(--line);background:var(--bg);padding:12px 14px;display:flex;flex-direction:column;gap:6px;min-width:0}
.bname b{font-weight:500}.bname .cat{margin:0;font:500 .72rem var(--mono);text-transform:uppercase;letter-spacing:.03em;color:var(--accent)}
.take{margin:0;font:.95rem/1.5 var(--body)}.trust{margin:0;font:.95rem/1.55 var(--body);max-width:75ch}
.srcs ul{padding:8px 12px 10px 30px;font-size:.9rem}.srcs li{overflow-wrap:anywhere}
"""

if __name__ == "__main__":
    main()
