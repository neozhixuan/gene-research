"""Stage 7: render the static site into site/ from the files under data/.

site/index.html is the latest day; site/days/<date>.html keeps every day.
Pure code: Vercel serves the folder as-is, nothing is built there.
"""

import csv
import html
import re

from markdown_it import MarkdownIt

import watchlist
from common import ACTIONS, DATA, SITE, clean_report, read_json

md = MarkdownIt("commonmark", {"html": False}).enable("table")
e = html.escape


def render_md(text):
    text = re.sub(r"^\s*(Bull|Bear|Aggressive|Conservative|Neutral) Analyst:\s*", "", clean_report(text))
    return md.render(text.strip()).replace("<table>", '<div class="tw"><table>').replace("</table>", "</table></div>")


def chip(rating, cls="chip"):
    r = rating or "n/a"
    return f'<span class="{cls} r-{e(r.lower())}">{e(r)}</span>'


def pct(x, signed=True):
    return "–" if x is None else (f"{x * 100:+.1f}%" if signed else f"{x * 100:.0f}%")


def tone(x):
    return "" if x is None else ("pos" if x > 0 else "neg" if x < 0 else "")


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
  <p class="segs">{" · ".join(e(s) for s in t["segments"])}</p>
</li>''' for t in theses)
    segs = "".join(f'<div class="seg st-{e(v["stance"])}"><span class="sg">{e(k.replace("_", " "))}</span><span class="sv">{e(v["stance"])}</span><p>{e(v.get("note", ""))}</p></div>'
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
    return f'''<article class="pick">
  <header><h3>{e(t)}</h3>{badge}<span class="muted">{e(row.get("name") or "")} · {e(r["segment"].replace("_", " "))}</span></header>
  {facts}
  {about}
  {chain}
  {f'<div class="agents"><p class="lbl">Every agent&#39;s output</p>{agents}</div>' if agents else ""}
</article>'''


def watchlist_html(watch, track):
    if not watch:
        return "<p class='muted'>Empty. Every new pick joins the watchlist.</p>"
    rows = []
    for t, w in sorted(watch.items(), key=lambda tw: (tw[1]["status"] != "active", tw[0])):
        # tracking.json is newest first, so the last row for a ticker is the day it was added
        f = next((p for p in reversed((track or {}).get("picks", [])) if p["ticker"] == t), {})
        last = watchlist.last_rating(w)
        act = ACTIONS.get(last, ("–", "–"))
        status = "active" if w["status"] == "active" else f'dropped {e(w["dropped"])}: {e(w["dropped_reason"])}'
        rows.append(f'<tr class="{"" if w["status"] == "active" else "off"}"><td class="tk">{e(t)}</td><td>{e(w["segment"].replace("_", " "))}</td><td>{e(w["added"])}</td>'
                    f'<td class="hist">{history_html(w)}</td><td class="n {tone(f.get("return"))}">{pct(f.get("return"))}</td>'
                    f'<td class="n {tone(f.get("vs_qqq"))}">{pct(f.get("vs_qqq"))}</td><td>{e(act[0])}</td><td>{e(act[1])}</td><td>{status}</td></tr>')
    return f'''<p class="muted">Every pick stays under watch. One name is re-checked each day (confident ones first, every {watchlist.RECHECK_AFTER_DAYS}+ days). A name is dropped after two negative ratings in a row or three Holds in a row; at most {watchlist.MAX_ACTIVE} stay active.</p>
<div class="tw"><table class="track"><thead><tr><th>Ticker</th><th>Segment</th><th>Added</th><th>Ratings, oldest first</th><th>Since added</th><th>vs QQQ</th><th>If you don&#39;t own it</th><th>If you own it</th><th>Status</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>'''


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


def usage_html():
    path = DATA / "usage.csv"
    rows = list(csv.DictReader(open(path))) if path.exists() else []
    if not rows:
        return "<p class='muted'>No runs recorded yet.</p>"
    num = lambda v: float(v) if v not in ("", None) else 0.0
    k = lambda v: f"{num(v) / 1000:,.0f}k" if v not in ("", None) else "–"

    def total(days):
        rs = rows[-days:]
        return {f: sum(num(r[f]) for r in rs) for f in ("claude_output", "claude_cache_read", "claude_cost_usd", "gemini_calls")}, len(rs)

    cards = ""
    for label, days in (("Last 5 runs", 5), ("Last 20 runs", 20)):
        t, n = total(days)
        cards += (f'<div><span class="lbl">{label} ({n})</span><strong>${t["claude_cost_usd"]:,.2f}</strong>'
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


def review_html(date):
    """The latest monthly review written on or before this day, if any."""
    reviews = sorted(p for p in (DATA / "reviews").glob("*.md") if p.stem <= date[:7])
    if not reviews:
        return ""
    return f'<h3>Monthly review {e(reviews[-1].stem)}</h3><div class="prose">{render_md(reviews[-1].read_text())}</div>'


HOW_TO_READ = """<details class="howto"><summary>How to read a verdict</summary><div class="prose">
<p>Each stock goes through a team of AI agents. Analysts write reports, a bull and a bear debate them, the <strong>research manager</strong> judges the debate,
the <strong>trader</strong> proposes a trade, three risk analysts argue over it, and the <strong>portfolio manager</strong> has the final say. It can overrule the trader.</p>
<p>The final rating translates to an action depending on whether you already own the stock:</p>
<div class="tw"><table><thead><tr><th>Rating</th><th>If you don&#39;t own it</th><th>If you own it</th></tr></thead><tbody>
""" + "".join(f"<tr><td>{k}</td><td>{a}</td><td>{b}</td></tr>" for k, (a, b) in ACTIONS.items()) + """</tbody></table></div>
<p>The agents assume a $10,000 cash account with no positions. Nothing is traded automatically; you decide.</p></div></details>"""


def page(date, days, depth):
    d = DATA / date
    w = read_json(DATA / "worldview" / f"{date}.json")
    picks = read_json(d / "picks.json", {}).get("picks", [])
    shortlist = read_json(d / "shortlist.json", {}).get("shortlist", [])
    by_ticker = {p["ticker"]: p for p in picks}
    runs = read_json(d / "runs.json") or [{"ticker": p["ticker"], "segment": p["segment"], "kind": "new"} for p in picks]
    watch = watchlist.load()
    track = read_json(DATA / "tracking.json")
    picks_html = "".join(run_html(r, read_json(d / "agents" / f"{r['ticker']}.json"), by_ticker.get(r["ticker"], {}), shortlist, watch)
                         for r in runs) or "<p class='muted'>No picks.</p>"
    up = "../" if depth else ""
    archive = "".join(f'<a href="{up}days/{x}.html"{" aria-current=page" if x == date else ""}>{x}</a>' for x in reversed(days))
    body = f'''<header class="top"><div class="eyebrow">Gene Research · {e(date)}</div>
<h1>{e(w["headline"] if w else "Daily AI-bottleneck research")}</h1></header>
<section><h2>Worldview</h2>{worldview_html(w)}</section>
<section><h2>Today&#39;s analysis</h2>{HOW_TO_READ}<div class="picks">{picks_html}</div></section>
<section><h2>Watchlist</h2>{watchlist_html(watch, track)}</section>
<section><h2>Track record</h2>{tracking_html(track)}{review_html(date)}</section>
<section><h2>Usage</h2>{usage_html()}</section>
<section><h2>Archive</h2><nav class="archive">{archive}</nav></section>
<footer>An automated research experiment: news and prices from Yahoo Finance, worldview and picks by Claude, verification by TradingAgents on Gemini. Model output can be wrong. Not financial advice.</footer>'''
    return TEMPLATE.replace("{{TITLE}}", f"Gene Research {date}").replace("{{BODY}}", body)


def main():
    days = sorted(p.stem for p in (DATA / "worldview").glob("*.json"))
    if not days:
        raise SystemExit("no worldviews yet")
    (SITE / "days").mkdir(parents=True, exist_ok=True)
    for date in days:
        (SITE / "days" / f"{date}.html").write_text(page(date, days, 1))
    (SITE / "index.html").write_text(page(days[-1], days, 0))
    print(f"site: {len(days)} day pages, index = {days[-1]}")


TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans+Condensed:wght@500;600;700&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>
:root{--bg:#f4f6f7;--surface:#fff;--ink:#172026;--muted:#5a6872;--line:#d8dee2;--accent:#1f5f8b;--pos:#17734a;--neg:#a8302b;
--buy:#17734a;--buy-bg:#e1f2e9;--ow:#3d7d2a;--ow-bg:#e8f2df;--hold:#7a6410;--hold-bg:#f6efd2;--uw:#a4520f;--uw-bg:#f9e8d8;--sell:#a8302b;--sell-bg:#f8e1df;
--display:"IBM Plex Sans Condensed","Arial Narrow",system-ui,sans-serif;--body:"Source Serif 4",Georgia,serif;--mono:"IBM Plex Mono",ui-monospace,Menlo,monospace;color-scheme:light}
@media (prefers-color-scheme:dark){:root{--bg:#10161a;--surface:#172026;--ink:#e3e9ec;--muted:#94a3ad;--line:#2b3840;--accent:#7cb7de;--pos:#6fd3a0;--neg:#f08a84;
--buy:#6fd3a0;--buy-bg:#163a2a;--ow:#a3d483;--ow-bg:#24361a;--hold:#e3c95e;--hold-bg:#3a3214;--uw:#f0a466;--uw-bg:#40280f;--sell:#f08a84;--sell-bg:#421a18;color-scheme:dark}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 var(--display)}
main{max-width:980px;margin:0 auto;padding:32px max(16px,env(safe-area-inset-right)) 64px max(16px,env(safe-area-inset-left));display:flex;flex-direction:column;gap:36px}
h1,h2,h3{margin:0;text-wrap:balance}h1{font-size:2rem;line-height:1.15;max-width:30ch}h2{font-size:1.4rem;border-bottom:2px solid var(--ink);padding-bottom:6px;margin-bottom:14px}h3{font-size:1.08rem;margin:18px 0 8px}
section{display:flex;flex-direction:column}.eyebrow,.lbl{font:0.72rem var(--mono);text-transform:uppercase;letter-spacing:.07em;color:var(--accent)}.lbl{color:var(--muted)}
.muted{color:var(--muted)}.regime{font:1.05rem/1.6 var(--body);max-width:68ch;margin:0}
.theses{list-style:none;margin:0;padding:0;display:flex;flex-direction:column;gap:8px}.thesis{background:var(--surface);border:1px solid var(--line);padding:10px 14px}
.th-top{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px}.th-top strong{flex:1 1 240px;font-size:1rem}
.stance,.chg,.chip{font:500 .7rem var(--mono);text-transform:uppercase;letter-spacing:.04em;padding:2px 7px;border-radius:2px;white-space:nowrap}
.s-bullish{color:var(--pos);background:var(--buy-bg)}.s-bearish{color:var(--neg);background:var(--sell-bg)}.s-neutral{color:var(--hold);background:var(--hold-bg)}
.chg{border:1px solid var(--line);color:var(--muted)}.c-new,.c-stronger{color:var(--accent);border-color:var(--accent)}.c-weaker,.c-retired{color:var(--uw);border-color:var(--uw)}
.conf{width:70px;height:6px;background:var(--line);display:inline-block}.conf span{display:block;height:100%;background:var(--accent)}.cn{font:.75rem var(--mono);color:var(--muted)}
.note{margin:6px 0 2px;font:.95rem/1.5 var(--body)}.segs{margin:0;font:.72rem var(--mono);color:var(--muted)}
.segrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}.seg{background:var(--surface);border:1px solid var(--line);padding:9px 12px;border-top:3px solid var(--line)}
.seg p{margin:4px 0 0;font-size:.85rem;color:var(--muted)}.sg{font-weight:600;text-transform:capitalize}.sv{float:right;font:.7rem var(--mono);text-transform:uppercase}
.st-overweight{border-top-color:var(--pos)}.st-overweight .sv{color:var(--pos)}.st-underweight{border-top-color:var(--neg)}.st-underweight .sv{color:var(--neg)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:20px}@media(max-width:640px){.two{grid-template-columns:1fr}}.plain{margin:0;padding-left:18px;font:.95rem/1.5 var(--body)}
.picks{display:flex;flex-direction:column;gap:16px}.pick{background:var(--surface);border:1px solid var(--line);padding:16px;display:flex;flex-direction:column;gap:10px;min-width:0}
.pick header{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.pick h3{font:600 1.8rem var(--mono);margin:0}.pick p{margin:0;font:.98rem/1.55 var(--body);max-width:70ch}
.facts{display:flex;flex-wrap:wrap;gap:6px 22px;margin:0}.facts div{display:flex;flex-direction:column}.facts dt{font:.68rem var(--mono);text-transform:uppercase;color:var(--muted)}.facts dd{margin:0;font-variant-numeric:tabular-nums}
.chain{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding:10px 0;border-block:1px solid var(--line)}.chain div{display:flex;flex-direction:column;gap:4px}.arr{color:var(--muted)}.chip.big{font-size:.9rem}
.r-buy{color:var(--buy);background:var(--buy-bg)}.r-overweight{color:var(--ow);background:var(--ow-bg)}.r-hold{color:var(--hold);background:var(--hold-bg)}.r-underweight{color:var(--uw);background:var(--uw-bg)}.r-sell{color:var(--sell);background:var(--sell-bg)}.r-n\\/a{color:var(--muted);border:1px solid var(--line)}
.agents{display:flex;flex-direction:column;gap:4px}details{border:1px solid var(--line)}summary{cursor:pointer;padding:7px 12px;font-weight:600}details[open] summary{border-bottom:1px solid var(--line)}
.prose{font:.98rem/1.6 var(--body);padding:4px 16px 12px;max-width:70ch;overflow-wrap:anywhere}.prose h1,.prose h2,.prose h3,.prose h4{font:600 1rem var(--display);border:0;margin:14px 0 4px}
.tw{overflow-x:auto}table{border-collapse:collapse;font-variant-numeric:tabular-nums}th,td{padding:5px 10px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{border-bottom-color:var(--ink)}
.n{text-align:right}.tk{font-family:var(--mono);font-weight:500}.pos{color:var(--pos)}.neg{color:var(--neg)}
.score{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}.score div{background:var(--surface);border:1px solid var(--line);padding:8px 12px;display:flex;flex-direction:column;min-width:150px}.score strong{font-size:1.4rem}
.archive{display:flex;flex-wrap:wrap;gap:6px}.archive a{font:.85rem var(--mono);color:var(--accent);border:1px solid var(--line);padding:3px 8px;text-decoration:none}.archive a[aria-current]{background:var(--ink);color:var(--bg)}
.kind{font:500 .68rem var(--mono);text-transform:uppercase;letter-spacing:.06em;padding:2px 6px;border:1px solid var(--line);color:var(--muted)}.kind.new{color:var(--accent);border-color:var(--accent)}
.action{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:0}.action div{background:var(--bg);padding:8px 10px;border:1px solid var(--line)}.action dt{font:.68rem var(--mono);text-transform:uppercase;color:var(--muted)}.action dd{margin:2px 0 0;font-weight:600}
@media(max-width:520px){.action{grid-template-columns:1fr}}.models{font:.75rem var(--mono)!important;color:var(--muted)}
.howto{margin-bottom:14px;background:var(--surface)}.howto .prose{max-width:none}tr.off td{color:var(--muted)}td.hist{white-space:normal}
footer{font:.88rem/1.5 var(--body);color:var(--muted);max-width:70ch}a:focus-visible,summary:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
</style></head><body><main>{{BODY}}</main></body></html>"""

if __name__ == "__main__":
    main()
