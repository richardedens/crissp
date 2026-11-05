"""How Claude worked, measured: what each of your requests cost and why, how often work was right the first time, and
whether a new way of working does better than the one before. Plain English, numbers only from records — no estimates.

Where every number comes from:
- Tokens, round trips and history: Claude Code's own transcripts (~/.claude/projects/<repository>/). Every response of
  the API carries its usage; a response is counted once. "History" is what one round trip sent to Claude: the fresh
  input plus what was read from and written to the cache. A request costs the sum over its round trips, plus what the
  agents it started used.
- What made the history grow: the difference in history between one round trip and the next, put on the tools used in
  the first of the two (their results are what was added, with Claude's own reply). A drop means the history was
  compacted.
- First time right: the status of each backlog item (E<n>-<nn>, [todo|doing|review|done]) in every commit of
  crissp/backlog/ (backlog/ before the move into crissp/).
  An item is right the first time when it went from review to done without going back to todo or doing first.
- Tokens per item: the requests between the commit before an item's commit (`E2-01: …`) and that commit.
- Ways of working: crissp/testsuite/ways-of-working.json — each with the date it started; a request belongs to the newest one
  that had started when it was asked.

    python3 crissp/testsuite/lib/measure.py [--projects DIR] [--out DIR]     (crissp/test.sh --dashboard runs it)
"""

import html
import json
import re
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sessionview as sv  # noqa: E402  (the transcripts, the session pages, the look)

ROOT = sv.ROOT  # the project (CRISSP_ROOT, or the current directory)
BACKLOG = ("crissp/backlog", "crissp/backlog", "backlog")  # where the backlog is, and where it was before
LONG = 300_000  # a history this long is a long history
ITEM = re.compile(r"^### (E\d+-\d+) · .+?\[(todo|doing|review|done|parked)\]", re.M)
COMMIT_ITEM = re.compile(r"^((?:E\d+-\d+)|(?:F-\d+)):")


def words(n: float) -> str:
    """A number as a person says it: 12.6 million, 58 thousand, 940."""
    if n >= 1e6:
        return f"{n / 1e6:.1f} million"
    if n >= 1e3:
        return f"{round(n / 1e3)} thousand"
    return f"{round(n)}"


def history(record: dict) -> int:
    u = (record.get("message") or {}).get("usage") or {}
    return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)


def requests_of(path: Path, repo: Path) -> list[dict]:
    """Every request you made in one session, with exactly what it cost and why."""
    r_ = sv.Repo(repo, sv.session_root(path))
    agents = sv.subagents(path, r_)
    out: list[dict] = []
    seen: set[str] = set()
    for rec in sv.records(path):
        if rec.get("isSidechain"):
            continue
        text = sv.prompt(rec)
        if text and not text.startswith("<task-notification>"):
            out.append({"session": path.stem, "n": len(out) + 1, "asked": text, "at": rec.get("timestamp"),
                        "trips": [], "agents": 0, "changed": set()})
            continue
        mid = (rec.get("message") or {}).get("id")
        if not out or rec.get("type") != "assistant":
            continue
        uses = sv.tool_uses(rec)
        for b in uses:
            if b.get("name") == "Agent":
                out[-1]["agents"] += sum((agents.get(b.get("id")) or {"tokens": Counter()})["tokens"].values())
            act = sv.action(b, r_, rec.get("cwd"))
            if act["kind"] == "change":
                out[-1]["changed"] |= act["files"]
        if mid and mid not in seen:
            seen.add(mid)
            out[-1]["trips"].append({"history": history(rec), "tokens": sum(sv.usage(rec).values()),
                                     "tools": sorted({b.get("name", "") for b in uses})})
        elif mid and uses:  # a response split over records: its tools belong to the round trip already counted
            out[-1]["trips"][-1]["tools"] = sorted(set(out[-1]["trips"][-1]["tools"]) | {b.get("name", "") for b in uses})
    for q in out:
        trips = q["trips"]
        q["tokens"] = sum(t["tokens"] for t in trips) + q["agents"]
        q["start"] = trips[0]["history"] if trips else 0
        q["end"] = trips[-1]["history"] if trips else 0
        grew: Counter = Counter()
        for a, b in zip(trips, trips[1:]):
            grew[" + ".join(a["tools"]) or "Claude's reply"] += b["history"] - a["history"]
        q["grew_by"] = {k: v for k, v in grew.most_common() if v > 0}
        q["compacted"] = any(v < 0 for v in grew.values())
        q["changed"] = sorted(q["changed"])
    return out


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return done.stdout if done.returncode == 0 else ""


def commits(root: Path) -> list[dict]:
    """Every commit, oldest first: sha, time, subject."""
    rows = [line.split("\t", 2) for line in git(root, "log", "--reverse", "--format=%H\t%cI\t%s").splitlines()]
    return [{"sha": r[0], "at": r[1], "subject": r[2]} for r in rows if len(r) == 3]


def item_history(root: Path) -> dict[str, list[str]]:
    """Each backlog item's status in every commit that changed backlog/, in order (a repeated status counted once)."""
    seen: dict[str, list[str]] = {}
    for sha in git(root, "log", "--reverse", "--format=%H", "--", *BACKLOG).split():
        files = [f for f in git(root, "ls-tree", "-r", "--name-only", sha, *BACKLOG).split() if f.endswith(".md")]
        for f in files:
            for item, status in ITEM.findall(git(root, "show", f"{sha}:{f}")):
                states = seen.setdefault(item, [])
                if not states or states[-1] != status:
                    states.append(status)
    return seen


def first_time_right(states: list[str]) -> bool | None:
    """True: review → done without going back first. False: sent back from review. None: not accepted yet."""
    if "done" not in states or "review" not in states[: states.index("done")]:
        return None
    first = states.index("review")
    return "done" == next(s for s in states[first + 1:] if s != "review")


def item_costs(root: Path, requests: list[dict]) -> dict[str, int]:
    """The tokens of the requests between an item's commit and the commit before it."""
    out: Counter = Counter()
    before = ""
    for c in commits(root):
        m = COMMIT_ITEM.match(c["subject"])
        if m:
            out[m.group(1)] += sum(q["tokens"] for q in requests if q["at"] and before < q["at"] <= c["at"])
        before = c["at"]
    return dict(out)


def ways(root: Path) -> list[dict]:
    """The ways of working, oldest first; without the file there is one: how we worked so far."""
    try:
        listed = json.loads((root / "crissp" / "testsuite" / "ways-of-working.json").read_text())
    except (OSError, json.JSONDecodeError):
        listed = []
    return sorted(listed, key=lambda w: w["since"]) or [{"name": "How we worked so far", "since": "", "what": ""}]


def way_of(at: str | None, listed: list[dict]) -> str:
    return next((w["name"] for w in reversed(listed) if (at or "") >= w["since"]), listed[0]["name"])


def compare(requests: list[dict], items: dict[str, list[str]], costs: dict[str, int], listed: list[dict]) -> list[dict]:
    """Per way of working: what a request costs, how long a history it carries, and how often work is right first time."""
    out = []
    for w in listed:
        mine = [q for q in requests if way_of(q["at"], listed) == w["name"] and q["trips"]]
        verdicts = [first_time_right(s) for s in items.values()]  # items are not dated yet: shown under every way
        judged = [v for v in verdicts if v is not None]
        out.append({**w, "requests": len(mine), "tokens": sum(q["tokens"] for q in mine),
                    "median": statistics.median([q["tokens"] for q in mine]) if mine else 0,
                    "start": statistics.median([q["start"] for q in mine]) if mine else 0,
                    "trips": statistics.median([len(q["trips"]) for q in mine]) if mine else 0,
                    "long": sum(q["start"] > LONG for q in mine), "accepted": len(judged), "right": sum(judged),
                    "per_item": statistics.median(list(costs.values())) if costs else 0})
    return out


# The pages are the dashboard's own: its stylesheet, its water, its cards, rings, badges and tables (dashboard/), so
# the Claude pages look and read exactly like the rest of the test suite.
EXTRA = """
.sub-tabs{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:0 0 26px}
.sub-tabs a{padding:9px 18px;border-radius:10px;border:1px solid var(--line);color:var(--muted);font:600 14px var(--font)}
.sub-tabs a.on{background:var(--panel2);color:var(--text);border-color:var(--panel2)}.sub-tabs a:hover{text-decoration:none;color:var(--text)}
nav a.tab{color:var(--muted);padding:7px 12px;border-radius:8px;font:500 13px var(--font)}nav a.tab:hover{text-decoration:none;color:var(--text)}
nav a.tab.on{background:var(--panel2);color:var(--text)}
.lead{font-size:16px;line-height:1.7;max-width:70ch;margin:0 0 6px}.how{color:var(--muted);font-size:14px;line-height:1.6;max-width:75ch;margin:0 0 14px}
.recs{display:grid;gap:14px;margin:0;padding:0;list-style:none}.recs .card{display:flex;gap:16px;align-items:flex-start}
.recs .n{flex:none;display:grid;place-items:center;width:38px;height:38px;border-radius:50%;background:var(--accent);color:#fff;font-weight:700}
.recs h3{font-size:16px;margin:6px 0 4px}.recs p{margin:0;color:var(--muted);font-size:14px;line-height:1.6}
.bars{display:grid;gap:16px}.bars .lbl{font-size:14px;margin:0 0 6px}.bars .row{display:flex;align-items:center;gap:12px}
.bars .bar{flex:1;height:12px}.bars .v{font-weight:700;font-size:14px;white-space:nowrap;min-width:92px;text-align:right}
.chart{width:100%;height:auto;display:block}.chart text{font:500 13px var(--font);fill:var(--muted)}
.key{display:flex;gap:18px;flex-wrap:wrap;font-size:13px;color:var(--muted);margin:0 0 12px}
.key span{display:inline-flex;gap:6px;align-items:center}.key i{width:12px;height:12px;border-radius:3px}
.asked{max-width:520px;overflow-wrap:anywhere}td.num,th.num{text-align:right;white-space:nowrap}
.pipe{display:flex;overflow-x:auto;align-items:flex-start;padding:6px 0 24px}.col{flex:0 0 320px;padding:0 10px}
.node{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:10px 12px;overflow-wrap:anywhere;font-size:13px}
.node.prompt{border-top:2px solid var(--accent)}.ptext{white-space:pre-wrap;margin:6px 0 0;display:-webkit-box;-webkit-line-clamp:4;
-webkit-box-orient:vertical;overflow:hidden}.tree,.tree ul{list-style:none;margin:0;padding:0 0 0 18px}.tree li{padding:8px 0 0}
.kind{display:block;font-size:11px;color:var(--muted)}.chip{display:inline-block;margin:4px 4px 0 0;padding:0 6px;border-radius:8px;
border:1px solid var(--line);font-size:11px}.tank,.cost,.status,.when{font-size:12px;color:var(--muted)}.tank span{display:none}
.node ol{list-style:none;padding:0;margin:6px 0 0}.node ol li{padding:3px 0;border-top:1px solid var(--line);font-size:12px}
.node pre{white-space:pre-wrap;font-size:11px;max-height:200px;overflow:auto}.n.pill{font-weight:700;margin-right:6px}
.row.taken .id{text-decoration:line-through}.small{font-size:12px}"""

TABS_JS = """(()=>{const tabs=[...document.querySelectorAll('section.stab')],links=[...document.querySelectorAll('.sub-tabs a')];
const show=()=>{const id=(location.hash||'#dashboard').slice(1);if(!tabs.some(t=>t.id==='tab-'+id))return;
tabs.forEach(t=>t.hidden=t.id!=='tab-'+id);links.forEach(a=>a.classList.toggle('on',a.hash==='#'+id));};
addEventListener('hashchange',show);show();})();"""


def shell(title: str, sub: str, body: str, script: str = "") -> str:
    """A page of the test suite: the dashboard's stylesheet and water, its top bar, the Claude sessions tab open."""
    return (f'<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,'
            f'initial-scale=1"><title>{html.escape(title)}</title><script>{sv.THEME}</script>'
            f'<link rel=stylesheet href="../../look/look.css"><link rel=stylesheet href="../../dashboard/style.css">'
            f'<style>{EXTRA}</style><body>{sv.top_bar(sub)}<main>{body}</main>'
            f'<script src="../../look/water.js"></script><script>{sv.TOGGLE}{script}</script></body></html>')


def recommendations(qs: list[dict], items: dict[str, list[str]], listed: list[dict]) -> list[tuple[str, str]]:
    """What to change, each with the measured fact behind it (nothing is recommended without one)."""
    timed = [q for q in qs if q["trips"]]
    out = []
    long = [q for q in timed if q["start"] > LONG]
    if long:
        cost = sum(q["tokens"] for q in long)
        out.append(("Start a new session for each feature or question.",
                    f"{len(long)} of {len(timed)} requests carried a history longer than {words(LONG)} tokens into "
                    f"Claude; together they used {words(cost)} tokens. Most of that history was about earlier work."))
    many = [q for q in timed if len(q["trips"]) > 25]
    if many:
        out.append(("Agree the plan first, then let Claude batch its steps.",
                    f"{len(many)} requests took more than 25 round trips (the most: {max(len(q['trips']) for q in many)}). "
                    "Every round trip sends the whole history again."))
    grew: Counter = Counter()
    for q in timed:
        for k, v in q["grew_by"].items():
            for tool in k.split(" + "):
                grew[tool] += v // len(k.split(" + "))
    if grew:
        tool, amount_ = grew.most_common(1)[0]
        if "chrome" in tool:
            advice = "Take browser screenshots small, and only when they decide something."
        elif tool in ("Bash", "Read", "Grep"):
            advice = "Let a subagent search and read, and bring back only its conclusion; cut long command output."
        else:
            advice = f"Look at what {tool} returns: it adds the most to the history."
        out.append((advice, f"{tool} added the most to the history: {words(amount_)} tokens over all requests."))
    if not any(first_time_right(s) is not None for s in items.values()):
        out.append(("Commit each item on its own and move it to review, so first time right can be measured.",
                    "No backlog item has gone from review to done in git yet."))
    if len(listed) == 1 and timed:
        out.append(("Write the next way of working down with its start date in crissp/testsuite/ways-of-working.json.",
                    "Only one way of working is recorded: without a second there is nothing to compare."))
    return out



def ring(p: float, label: str, color: str) -> str:
    """The dashboard's ring: filled to p percent, its label in the middle."""
    return f'<div class=ring style="--p:{max(0, min(100, round(p)))};--c:var({color})" data-label="{html.escape(label)}"></div>'


def kpi(ring_: str, label: str, value: str, sub: str) -> str:
    """One fact as the dashboard shows it: a ring, what it is, the number, and one line saying what it means."""
    return (f'<div class="card kpi row">{ring_}<div><div class=l>{html.escape(label)}</div><div class=v>{value}</div>'
            f'<div class=s>{html.escape(sub)}</div></div></div>')


def plain(label: str, value: str, sub: str) -> str:
    return f'<div class="card kpi"><div class=l>{html.escape(label)}</div><div class=v>{value}</div><div class=s>{html.escape(sub)}</div></div>'


def pct(a: float, b: float) -> float:
    return 100 * a / b if b else 0


def key() -> str:
    return ('<div class=key><span><i style="background:var(--green)"></i>short history: fine</span>'
            '<span><i style="background:var(--amber)"></i>long history: costs more</span></div>')


def glance(timed: list[dict], items: dict[str, list[str]], sessions: int) -> str:
    """The headline facts as rings: the share on a long history, the tokens it took, and first time right."""
    total = sum(q["tokens"] for q in timed)
    long = [q for q in timed if q["start"] > LONG]
    lt = sum(q["tokens"] for q in long)
    accepted = [v for v in (first_time_right(s) for s in items.values()) if v is not None]
    right = (kpi(ring(pct(sum(accepted), len(accepted)), f"{round(pct(sum(accepted), len(accepted)))}%", "--green"),
                 "Right the first time", f'{sum(accepted)}<small class=muted> / {len(accepted)}</small>',
                 "items accepted the first time they came to review") if accepted else
             kpi(ring(0, "—", "--muted"), "Right the first time", "—",
                 "not measured yet: no item has gone from review to done in git"))
    return ('<div class="grid kpis">'
            + plain("Tokens used", words(total), f"by {len(timed)} requests in {sessions} session(s)")
            + kpi(ring(pct(len(long), len(timed)), f"{round(pct(len(long), len(timed)))}%", "--amber"),
                  "Requests on a long history", f'{len(long)}<small class=muted> / {len(timed)}</small>',
                  f"started with more than {words(LONG)} tokens of history")
            + kpi(ring(pct(lt, total), f"{round(pct(lt, total))}%", "--amber"), "Tokens spent on long histories",
                  words(lt), f"of the {words(total)} tokens")
            + right + "</div>")


def bars(qs: list[dict], limit: int = 8) -> str:
    """The most expensive requests as bars: a longer bar used more tokens; amber when it carried a long history."""
    top = sorted([q for q in qs if q["trips"]], key=lambda q: q["tokens"], reverse=True)[:limit]
    if not top:
        return '<div class=card><p class=muted>No requests yet.</p></div>'
    most = top[0]["tokens"]
    rows = "".join(
        f'<div title="{html.escape(words(q["tokens"]))} tokens · {len(q["trips"])} round trips"><p class=lbl><b>#{q["n"]}</b> '
        f'{html.escape(q["asked"][:110])}</p><div class=row><div class=bar style="--c:var({"--amber" if q["start"] > LONG else "--green"})">'
        f'<i style="width:{max(1, round(100 * q["tokens"] / most))}%"></i></div><span class=v>{words(q["tokens"])}</span></div></div>'
        for q in top)
    return f'<div class="card bars">{rows}</div>'


def history_chart(qs: list[dict]) -> str:
    """How much history each request started with, request by request, with the line where a history counts as long."""
    timed = [q for q in qs if q["trips"]]
    if not timed:
        return ""
    top = max(max(q["start"] for q in timed), LONG) * 1.1
    w, h, pad = 1000, 240, 10
    step = (w - pad) / len(timed)
    cols = "".join(
        f'<rect x="{pad + i * step + 1:.1f}" y="{h - 24 - (h - 44) * q["start"] / top:.1f}" width="{max(1.0, step - 2):.1f}" '
        f'height="{max(1.0, (h - 44) * q["start"] / top):.1f}" rx=2 fill="var({"--amber" if q["start"] > LONG else "--green"})">'
        f'<title>#{q["n"]}: started with {words(q["start"])} tokens of history</title></rect>' for i, q in enumerate(timed))
    y = h - 24 - (h - 44) * LONG / top
    legend = key().replace("</div>", f'<span><i style="border-top:2px dashed var(--text);height:0;border-radius:0"></i>'
                                      f"dashed line: where a long history starts ({words(LONG)})</span></div>")
    return (f'<div class=card>{legend}<svg class=chart viewBox="0 0 {w} {h}" role=img aria-label="history at the start of '
            f'each request">{cols}<line x1={pad} x2={w} y1="{y:.1f}" y2="{y:.1f}" stroke="var(--text)" stroke-dasharray="6 6" '
            f'stroke-opacity=.6/>'
            f'<text x={pad} y={h - 4}>first request</text><text x={w} y={h - 4} text-anchor=end>last request</text></svg></div>')


def recs_list(recs: list[tuple[str, str]]) -> str:
    if not recs:
        return "<div class=card><p class=muted>Nothing to recommend: no measurement points at a problem.</p></div>"
    return "<ol class=recs>" + "".join(
        f'<li class=card><span class=n>{i}</span><div><h3>{html.escape(a)}</h3><p><b>Because:</b> {html.escape(f)}</p></div></li>'
        for i, (a, f) in enumerate(recs, 1)) + "</ol>"


def source(path: Path) -> str:
    """Where a session's numbers come from: its transcript, how big it is and when it last changed."""
    from datetime import datetime
    st = path.stat()
    when = datetime.fromtimestamp(st.st_mtime).strftime("%A %d %B, %H:%M")
    return (f"<p class=how>Measured from Claude Code's record of this session: <code>{html.escape(str(path))}</code> · "
            f"{st.st_size / 1e6:.1f} MB · last written {when}.</p>")


def table(qs: list[dict]) -> str:
    """Every request in the dashboard's table: what you asked and what it cost."""
    rows = "".join(
        f'<tr><td class=num>{q["n"]}</td><td class=asked>{html.escape(q["asked"][:180])}'
        + (' <span class="badge missing">long history</span>' if q["start"] > LONG else "")
        + (' <span class="badge area">compacted</span>' if q["compacted"] else "")
        + f'</td><td class=num>{words(q["tokens"])}</td><td class=num>{len(q["trips"])}</td><td class=num>{words(q["start"])}</td>'
        f'<td class=muted>{html.escape(next(iter(q["grew_by"]), "—"))}</td><td class=num>{len(q["changed"])}</td></tr>' for q in qs)
    return ('<div class=card><table><thead><tr><th class=num>#</th><th>You asked</th><th class=num>Tokens</th>'
            '<th class=num>Round trips</th><th class=num>History at start</th><th>Grew most from</th><th class=num>Files</th>'
            f"</tr></thead><tbody>{rows}</tbody></table></div>")


def headline(timed: list[dict], sessions: int) -> str:
    if not timed:
        return "<p class=lead>No requests found for this repository yet.</p>"
    return (f"<p class=lead>You asked Claude <b>{len(timed)}</b> things in {sessions} session(s). Together they used "
            f"<b>{words(sum(q['tokens'] for q in timed))}</b> tokens.</p><p class=how>How a request costs: each step Claude "
            "takes, it is sent the whole conversation so far (the history) again. So a request costs its steps × the size "
            "of its history.</p>")


def proof(requests: list[dict], items: dict[str, list[str]], costs: dict[str, int], listed: list[dict]) -> str:
    ws = compare(requests, items, costs, listed)
    rows = "".join(
        f'<tr><td><b>{html.escape(w["name"])}</b><div class="muted small">{html.escape(w["what"])}</div></td>'
        f'<td>{html.escape(w["since"][:10]) or "the start"}</td><td class=num>{w["requests"]}</td><td class=num>{words(w["median"])}</td>'
        f'<td class=num>{words(w["start"])}</td><td class=num>{w["trips"]:g}</td><td class=num>{w["long"]}</td>'
        f'<td class=num>{f"{w['right']} of {w['accepted']}" if w["accepted"] else "—"}</td></tr>' for w in ws)
    one = (" Only one way of working is recorded so far: it is the baseline the next one is measured against."
           if len(listed) == 1 else "")
    return (f"<p class=how>A new way of working is better when its requests cost less <b>and</b> more of its items are "
            f"right the first time. The ways are in <code>crissp/testsuite/ways-of-working.json</code>.{one}</p>"
            '<div class=card><table><thead><tr><th>Way of working</th><th>Since</th><th class=num>Requests</th>'
            '<th class=num>Tokens per request</th><th class=num>History at start</th><th class=num>Round trips</th>'
            f'<th class=num>On a long history</th><th class=num>Right first time</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<p class=how>Per request: the median, the middle value.</p>')


def report(requests: list[dict], items: dict[str, list[str]], costs: dict[str, int], listed: list[dict],
           sessions: list[dict], paths: dict[str, Path]) -> str:
    e = html.escape
    timed = [q for q in requests if q["trips"]]
    rows = "".join(
        f'<tr><td><a href="{e(s["id"])}.html">{sv.when(s["first"]) or e(s["id"][:8])}'
        f'</a></td><td class=num>{len(mine)}</td><td class=num>{words(sum(q["tokens"] for q in mine))}</td><td class=num>'
        f'{sum(q["start"] > LONG for q in mine)}</td><td class=muted>{e(paths[s["id"]].name)}</td></tr>'
        for s in sessions for mine in [[q for q in requests if q["session"] == s["id"] and q["trips"]]])
    body = (f"{headline(timed, len(sessions))}{glance(timed, items, len(sessions))}"
            f"<h2>What to change</h2>{recs_list(recommendations(requests, items, listed))}"
            f"<h2>The most expensive requests</h2><p class=how>A longer bar used more tokens.</p>{key()}{bars(timed)}"
            f"<h2>Is a new way of working better?</h2>{proof(requests, items, costs, listed)}"
            "<h2>Sessions</h2><p class=how>Click a session for its dashboard, its timeline and its recommendations.</p>"
            '<div class=card><table><thead><tr><th>Started</th><th class=num>Requests</th><th class=num>Tokens</th>'
            f'<th class=num>On a long history</th><th>Measured from</th></tr></thead><tbody>{rows}</tbody></table></div>')
    return shell("How Claude worked", "Claude sessions · how Claude worked", body)


def details(s: dict, qs: list[dict], path: Path, items: dict[str, list[str]], listed: list[dict], root: Path) -> str:
    """One session in three tabs: its dashboard, its timeline with the numbers, and what to change."""
    e = html.escape
    timed = [q for q in qs if q["trips"]]
    files = "".join(
        f'<tr><td><code>{e(f)}</code></td><td>' + (
            '<span class="badge passed">loaded at the start</span>' if f in sv.AUTO else
            f'<span class="badge passed">read {s["read"][f]}×</span>' if s["read"][f] else
            '<span class="badge missing">never read</span>') + "</td></tr>"
        for f in sv.WAY_OF_WORKING if (root / f).is_file())
    more = ('<div class="grid kpis" style="margin-top:14px">'
            + plain("Round trips", str(sum(len(q["trips"]) for q in timed)), "steps Claude took, each sent the whole history")
            + plain("Files changed", str(len({f for q in qs for f in q["changed"]})), "by Claude in this session")
            + plain("Agents started", str(s["agents"]), "helpers that worked next to the session")
            + plain("Findings and decisions", f'{s["F"]} · {s["D"]}', "written to the backlog") + "</div>")
    dashboard = (f"{source(path)}{headline(timed, 1)}{glance(timed, items, 1)}{more}"
                 f"<h2>The most expensive requests</h2><p class=how>A longer bar used more tokens.</p>{key()}{bars(timed, 5)}"
                 "<h2>Did Claude read the way of working?</h2><p class=how>Green: read in this session. Amber: never read."
                 f"</p><div class=card><table><tbody>{files}</tbody></table></div>")
    most = max((t["total"] for t in s["turns"]), default=0)
    timeline = ("<h2>The history, request by request</h2><p class=how>Each column is one request, from first to last. "
                "A taller column carried more history into Claude; above the dashed line it is a long history.</p>"
                f"{history_chart(qs)}<h2>Every request</h2>{table(qs)}<h2>Every step</h2><p class=how>For digging: one "
                "column per request, scroll sideways, open a block to see its steps.</p><div class=pipe>"
                + "".join(sv.column(i, t, most) for i, t in enumerate(s["turns"], 1)) + "</div>")
    body = (f'<p><a href="index.html">← All sessions</a></p><h2 style="margin-top:6px">Session of '
            f'{sv.when(s["first"]) or e(s["id"][:8])}</h2><nav class=sub-tabs><a href="#dashboard">Dashboard</a>'
            '<a href="#timeline">Timeline and numbers</a><a href="#advice">Recommendations</a></nav>'
            f"<section class=stab id=tab-dashboard>{dashboard}</section><section class=stab id=tab-timeline>{timeline}</section>"
            f"<section class=stab id=tab-advice><h2>What to change</h2>{recs_list(recommendations(qs, items, listed))}</section>")
    return shell(f"Session {s['id'][:8]}", f"Claude sessions · session of {sv.when(s['first'])}", body, TABS_JS)


def build(root: Path, projects: Path, out: Path) -> Path:
    """The report (the index), a details page per session, and the summary the dashboard's header links."""
    out.mkdir(parents=True, exist_ok=True)
    folder = sv.project_dir(root, projects)
    sessions = sv.sessions(root, projects)
    paths = {s["id"]: folder / f"{s['id']}.jsonl" for s in sessions}
    per = {s["id"]: requests_of(paths[s["id"]], root) for s in sessions}
    requests = [q for s in sessions for q in per[s["id"]]]
    items, listed = item_history(root), ways(root)
    for s in sessions:
        (out / f"{s['id']}.html").write_text(details(s, per[s["id"]], paths[s["id"]], items, listed, root))
    (out / "summary.json").write_text(json.dumps({"sessions": len(sessions),
                                                  "tokens": sv.amount(sum(s["total"] for s in sessions))}))
    index = out / "index.html"
    index.write_text(report(requests, items, item_costs(root, requests), listed, sessions, paths))
    return index


def main(argv: list[str]) -> int:
    named, rest = {}, list(argv)
    while rest:
        a = rest.pop(0)
        if a in ("--projects", "--out") and rest:
            named[a] = Path(rest.pop(0))
        else:
            print("usage: python3 crissp/testsuite/lib/measure.py [--projects DIR] [--out DIR]", file=sys.stderr)
            return 2
    print(build(ROOT, named.get("--projects", sv.PROJECTS), named.get("--out", sv.OUT)))
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script by crissp/test.sh; main() is tested
    sys.exit(main(sys.argv[1:]))
