"""What Claude did in this repository: every Claude Code session as a pipeline — asked, agents, work, findings, decisions.

Claude Code keeps a transcript of every session on this Mac (~/.claude/projects/<repository path>/<session>.jsonl,
with the subagents' transcripts next to it). This reads them and writes one HTML page per session plus an index.

A session page is a pipeline that scrolls sideways: one column per prompt, and in each column, top to bottom,
- the prompt
- the agents: the main session, every subagent it started there (what it did, the files it changed) and agent reports
- the work: R read · W write/edit · $ command · ? a question to the product owner, with the files changed
- the findings written there (F-xx rows added to a FINDINGS.md)
- the decisions written there (D-xx rows added to a DECISIONS.md; struck through = taken)
Above it: which way-of-working files (CLAUDE.md, CRISSP.md, the backlog, …) were loaded, read, written or never read.

Only what Claude sent to its tools is shown (paths, commands, descriptions), never what came back, and obvious secrets
in a command are masked. The pages go to crissp/testsuite/results/sessions/ (not in git: they hold the prompts).

    python3 crissp/testsuite/lib/sessionview.py [--open] [--projects DIR] [--out DIR]
"""

import base64
import html
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project

ROOT = project.root()  # the project whose sessions these are (CRISSP_ROOT, or the current directory)
OUT = project.results(ROOT) / "sessions"
LOOK = Path(__file__).resolve().parents[2] / "look"  # the shared look, beside this engine
DASHBOARD = Path(__file__).resolve().parents[1] / "dashboard"  # the pages' stylesheets and scripts (F-94)
PROJECTS = Path.home() / ".claude" / "projects"

SECRET = re.compile(r"(?i)((?:token|password|passwd|secret|api[_-]?key|bearer)[\"'=: ]+)[^\s\"']+")
INJECTED = re.compile(r"<(system-reminder|browser_instruction|ide_[a-z_]+|command-[a-z]+)>.*?</\1>", re.DOTALL)
ROW = re.compile(r"(?:^|(?<=['\"]))\|\s*(~~)?([FD]-\d+)(?:~~)?\s*\|([^|\n]*)\|([^|\n]*)\|", re.MULTILINE)
REDIRECT = re.compile(r"(?:^|(?<=[\s;|&)]))>>?\s*([\w@-]*[./][\w./@-]*)")  # `> file`, `>> dir/f`; not 2>, =>, ->
READING = (
    "cat ",
    "sed -n",
    "grep ",
    "ls",
    "head ",
    "tail ",
    "find ",
    "wc ",
    "git log",
    "git status",
    "git diff",
    "git show",
    "rg ",
)
WAY_OF_WORKING = (
    "CLAUDE.md",
    "crissp/CLAUDE.md",
    "AGENTS.md",
    "crissp/AGENTS.md",
    "crissp/CRISSP.md",
    "crissp/ARCHITECTURE.md",
    "README.md",
    "crissp/backlog/README.md",
    "crissp/backlog/PLAN.md",
    "crissp/backlog/DECISIONS.md",
    "crissp/backlog/FINDINGS.md",
    "crissp/testsuite/README.md",
    "crissp/README.md",
)
# What Claude Code loads by itself at the start: the root CLAUDE.md and what it imports.
AUTO = ("CLAUDE.md", "crissp/CLAUDE.md")
# Where things lived before (2026-10-23): the way of working went from the root into a hidden .crissp/, then into a
# visible crissp/ together with the testsuite and the check, deploy and dashboard scripts. Older sessions name the old places.
MOVED = (
    (".crissp/", "crissp/"),
    ("backlog/", "crissp/backlog/"),
    ("CRISSP.md", "crissp/CRISSP.md"),
    ("ARCHITECTURE.md", "crissp/ARCHITECTURE.md"),
    ("testsuite/", "crissp/testsuite/"),
    ("check.sh", "crissp/check.sh"),
    ("check-all.sh", "crissp/check-all.sh"),
    ("deploy.sh", "crissp/deploy.sh"),
    ("test.sh", "crissp/test.sh"),
)


def moved(rel: str) -> str:
    """A repository path by its current place: the old place of a moved file becomes its new one."""
    for old, new in MOVED:
        if rel == old or (old.endswith("/") and rel.startswith(old)):
            return new + rel[len(old) :]
    return rel


ICON = {"read": "R", "change": "W", "run": "$", "ask": "?", "other": "·"}


def project_dir(repo: Path, projects: Path = PROJECTS) -> Path:
    """Where Claude Code keeps this repository's transcripts: its path with every other character as '-'."""
    return projects / re.sub(r"[^A-Za-z0-9]", "-", str(repo))


def mask(text: str) -> str:
    return SECRET.sub(r"\1•••", text)


def records(path: Path):
    for line in path.read_text(errors="replace", encoding="utf-8").splitlines():
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


class Repo:
    """The repository, and the folder the session ran in when that was another name for it (a renamed folder)."""

    def __init__(self, root: Path, session_root: str | None = None):
        self.root = root
        self.roots = [root] + ([Path(session_root)] if session_root and Path(session_root) != root else [])

    def rel(self, path: str) -> str | None:
        """The path relative to the repository, or None when it is outside it."""
        for base in self.roots:
            try:
                return moved(str(Path(path).relative_to(base)))
            except ValueError:
                continue
        return None

    def mentioned(self, command: str, cwd: str | None) -> set[str]:
        """The repository files a shell command names: a rough view of what it read or touched."""
        found = set()
        for token in re.findall(r"[\w./@-]+", command):
            if "/" in token or "." in token:
                rel = self.rel(token if token.startswith("/") else str(Path(cwd or self.root) / token))
                if rel and (self.root / rel).is_file():
                    found.add(rel)
        return found


def prompt(record: dict) -> str | None:
    """What the person typed (or an agent's report), without what the harness added; None for anything else."""
    content = (record.get("message") or {}).get("content")
    if record.get("type") != "user" or record.get("isMeta") or record.get("isCompactSummary"):
        return None
    if isinstance(content, list):
        if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
            return None
        content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    return INJECTED.sub("", content).strip() or None


def rows(text: str, kind: str) -> list[dict]:
    """The F-xx or D-xx table rows in a piece of text: id, the observation or question, and whether it is struck."""
    return [
        {"id": m.group(2), "text": (m.group(4) if kind == "F" else m.group(3)).strip(), "taken": bool(m.group(1))}
        for m in ROW.finditer(text)
        if m.group(2).startswith(kind)
    ]


def written_rows(name: str, given: dict) -> dict[str, list[dict]]:
    """The finding and decision rows a tool call adds to a FINDINGS.md or DECISIONS.md."""
    out = {}
    for kind, file in (("F", "FINDINGS.md"), ("D", "DECISIONS.md")):
        if name == "Bash":
            text, before = (given.get("command", ""), "") if file in given.get("command", "") else ("", "")
        elif given.get("file_path", "").endswith(file):
            text, before = given.get("content") or given.get("new_string") or "", given.get("old_string") or ""
        else:
            continue
        had = {r["id"] for r in rows(before, kind)}
        new = [r for r in rows(text, kind) if r["id"] not in had]
        if new:
            out[kind] = new
    return out


def action(block: dict, repo: Repo, cwd: str | None) -> dict:
    name, given = block.get("name", ""), block.get("input") or {}
    if name in ("Read", "Edit", "Write", "NotebookEdit"):
        rel = repo.rel(given.get("file_path", "")) or given.get("file_path", "")
        act = {"kind": "read" if name == "Read" else "change", "text": rel, "files": {rel}}
    elif name == "Bash":
        command = given.get("command", "")
        line = command.split("<<", 1)[0]  # the command itself, not the body of a heredoc
        into = {
            rel
            for t in REDIRECT.findall(line)
            if (rel := repo.rel(t if t.startswith("/") else str(Path(cwd or repo.root) / t)))
        }
        kind = "change" if into else ("read" if command.lstrip().startswith(READING) else "run")
        text = given.get("description") or (command.splitlines() or [""])[0][:120]
        act = {"kind": kind, "text": mask(text), "detail": mask(command), "files": into or repo.mentioned(command, cwd)}
    elif name == "AskUserQuestion":
        act = {
            "kind": "ask",
            "text": " · ".join(q.get("question", "") for q in given.get("questions", [])),
            "files": set(),
        }
    else:
        act = {"kind": "other", "text": name, "files": set()}
    act["rows"] = written_rows(name, given)
    return act


def usage(record: dict) -> Counter:
    """The tokens of one API response: fresh input, output, cache reads and cache writes."""
    u = (record.get("message") or {}).get("usage") or {}
    return Counter(
        {
            "input": u.get("input_tokens", 0),
            "output": u.get("output_tokens", 0),
            "cache_read": u.get("cache_read_input_tokens", 0),
            "cache_write": u.get("cache_creation_input_tokens", 0),
        }
    )


def tokens(records_, skip: str | None = None) -> Counter:
    """The tokens of a transcript's responses, each counted once (a response is split over several records)."""
    total, seen = Counter(), set()
    for r in records_:
        mid = (r.get("message") or {}).get("id")
        if r.get("type") != "assistant" or not mid or mid in seen or any(b.get("id") == skip for b in tool_uses(r)):
            continue
        seen.add(mid)
        total.update(usage(r))
    return total


def tool_uses(record: dict) -> list[dict]:
    content = (record.get("message") or {}).get("content") if record.get("type") == "assistant" else None
    return (
        [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(content, list) else []
    )


def subagents(path: Path, repo: Repo) -> dict[str, dict]:
    """Each subagent of the session, by the id of the tool call that started it: what it was and what it did."""
    out = {}
    for meta in sorted((path.with_suffix("") / "subagents").glob("*.meta.json")):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            info = {}
        transcript = meta.with_name(meta.name.removesuffix(".meta.json") + ".jsonl")
        own = list(records(transcript)) if transcript.is_file() else []
        acts = [
            action(b, repo, r.get("cwd")) for r in own for b in tool_uses(r) if b.get("id") != info.get("toolUseId")
        ]
        out[info.get("toolUseId") or meta.name] = {
            "name": info.get("description") or meta.name.removesuffix(".meta.json"),
            "type": info.get("agentType", "agent"),
            "kinds": Counter(a["kind"] for a in acts),
            "changed": sorted({f for a in acts if a["kind"] == "change" for f in a["files"]}),
            "acts": acts,
            "done": info.get("finished", False),
            "tokens": tokens(own, skip=info.get("toolUseId")),
        }
    return out


def session_root(path: Path) -> str | None:
    return next((r["cwd"] for r in records(path) if r.get("cwd")), None)


def parse(path: Path, repo: Repo) -> list[dict]:
    """The session as columns: one per prompt, with the agents, the work, the findings and the decisions that followed."""
    agents = subagents(path, repo)
    turns: list[dict] = []
    seen: set[str] = set()
    counted: set[str] = set()

    def turn(ts):
        if not turns:
            turns.append(
                {
                    "ts": ts,
                    "prompt": "(before the first prompt)",
                    "acts": [],
                    "agents": [],
                    "reports": [],
                    "F": [],
                    "D": [],
                    "tokens": Counter(),
                }
            )
        return turns[-1]

    for r in records(path):
        if r.get("isSidechain"):
            continue
        text = prompt(r)
        if text and text.startswith("<task-notification>"):
            summary = re.search(r"<summary>(.*?)</summary>", text, re.DOTALL)
            turn(r.get("timestamp"))["reports"].append(
                mask(summary.group(1).strip() if summary else "an agent reported")
            )
        elif text:
            turns.append(
                {
                    "ts": r.get("timestamp"),
                    "prompt": text,
                    "acts": [],
                    "agents": [],
                    "reports": [],
                    "F": [],
                    "D": [],
                    "tokens": Counter(),
                }
            )
        mid = (r.get("message") or {}).get("id")
        if r.get("type") == "assistant" and mid and mid not in counted:
            counted.add(mid)
            turn(r.get("timestamp"))["tokens"].update(usage(r))
        for b in tool_uses(r):
            t = turn(r.get("timestamp"))
            if b.get("name") == "Agent":
                given = b.get("input") or {}
                t["agents"].append(
                    agents.get(b.get("id"))
                    or {
                        "name": given.get("description", "agent"),
                        "type": given.get("subagent_type", "agent"),
                        "kinds": Counter(),
                        "changed": [],
                        "acts": [],
                        "done": False,
                        "tokens": Counter(),
                    }
                )
                continue
            act = action(b, repo, r.get("cwd"))
            t["acts"].append(act)
            for kind, new in act["rows"].items():
                t[kind] += [x for x in new if x["id"] not in seen]
                seen.update(x["id"] for x in new)
    for t in turns:  # what a step cost: the main session's responses plus every agent it started
        t["total"] = sum(t["tokens"].values()) + sum(sum(a["tokens"].values()) for a in t["agents"])
    return turns


def when(ts: str | None) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%a %d %b %H:%M")
    except (TypeError, ValueError):  # no time, or not one
        return ""


def summary(path: Path, repo_root: Path) -> dict:
    repo = Repo(repo_root, session_root(path))
    turns = parse(path, repo)
    acts = [a for t in turns for a in t["acts"]]
    stamps = [t["ts"] for t in turns if t["ts"]]
    return {
        "id": path.stem,
        "turns": turns,
        "first": min(stamps, default=None),
        "last": max(stamps, default=None),
        "kinds": Counter(a["kind"] for a in acts),
        "read": Counter(f for a in acts if a["kind"] == "read" for f in a["files"]),
        "changed": Counter(f for a in acts if a["kind"] == "change" for f in a["files"]),
        "agents": sum(len(t["agents"]) for t in turns),
        "F": sum(len(t["F"]) for t in turns),
        "D": sum(len(t["D"]) for t in turns),
        "tokens": sum((t["tokens"] + sum((a["tokens"] for a in t["agents"]), Counter()) for t in turns), Counter()),
        "total": sum(t["total"] for t in turns),
    }


def amount(n: int) -> str:
    """1234 → 1.2k, 3400000 → 3.4M."""
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


STYLE = (DASHBOARD / "sessions.css").read_text(encoding="utf-8")  # F-94: a file linters read

# The water of the shared look (crissp/look/water.js, plain WebGL), built into these pages so they also work alone.
WATER_JS = LOOK / "water.js"


def water() -> str:
    return WATER_JS.read_text(encoding="utf-8") if WATER_JS.is_file() else ""


# The shared look's type, Figtree (OFL-1.1, crissp/look/LICENSE-figtree.txt), inside the page: it loads nothing.
FONT = LOOK / "figtree-latin-variable.woff2"


def product() -> tuple[str, str]:
    """The product's name and monogram, as the dashboard has them (crissp/testsuite/suites.json)."""
    try:
        conf = json.loads((ROOT / "crissp" / "testsuite" / "suites.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        conf = {}
    name = conf.get("product", ROOT.name)
    return name, conf.get("monogram", name[:1].upper())


def top_bar(title: str) -> str:
    """The shared top bar (E3-F1-01): the brand, and the sections nav that the shared look fills (Sessions open)."""
    name, mono = product()
    return (
        f"<header class=top><div class=brand><span class=logo>{html.escape(mono)}</span><div><h1>{html.escape(name)} "
        f"· Sessions</h1><p>{html.escape(title)}</p></div></div>"
        f'<nav class="sections" aria-label="Sections" data-current="sessions"></nav><button id=theme class=ghost '
        f'title="Light / dark" aria-label="Light or dark">◐</button></header>'
    )


def font_face() -> str:
    data = base64.b64encode(FONT.read_bytes()).decode() if FONT.is_file() else ""
    return (
        f'@font-face{{font-family:"Figtree";font-style:normal;font-display:swap;font-weight:300 900;'
        f'src:url(data:font/woff2;base64,{data}) format("woff2")}}'
        if data
        else ""
    )


def page(title: str, body: str) -> str:
    """A page in the shared look under its top bar: dark by default (light when chosen, remembered), water underneath."""
    return (
        f'<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content="width=device-width,'
        f'initial-scale=1"><title>{html.escape(title)}</title><script src=../../look/look.js></script><style>{font_face()}{STYLE}'
        f"</style><div class=water aria-hidden=true><canvas></canvas><i></i></div>{top_bar(title)}<main>{body}</main>"
        f"<script>{water()}</script></html>"
    )


def way_of_working(s: dict, repo: Path) -> str:
    out = []
    for f in WAY_OF_WORKING:
        if not (repo / f).is_file():
            continue
        read, written = s["read"][f], s["changed"][f]
        parts = (
            (["loaded at start"] if f in AUTO else [])
            + ([f"read {read}×"] if read else [])
            + ([f"written {written}×"] if written else [])
        )
        state = "auto" if f in AUTO else ("read" if read else "never")
        if state == "never":
            parts.insert(0, "never read")
        out.append(f'<li class="{state}"><code>{html.escape(f)}</code><span>{", ".join(parts)}</span></li>')
    return "".join(out)


def files(counts: Counter, limit: int = 25) -> str:
    if not counts:
        return "<p class=muted>none</p>"
    items = "".join(f"<li><code>{html.escape(f)}</code><span>{n}</span></li>" for f, n in counts.most_common(limit))
    more = f"<li class=muted>… and {len(counts) - limit} more</li>" if len(counts) > limit else ""
    return f"<ul>{items}{more}</ul>"


def chips(kinds: Counter) -> str:
    return "".join(f'<span class="chip {x}">{ICON[x]} {kinds[x]}</span>' for x in ICON if kinds[x])


def actions(acts: list[dict]) -> str:
    e, items = html.escape, []
    for a in acts:
        line = f'<span class="ico {a["kind"]}">{ICON[a["kind"]]}</span>{e(a["text"])}'
        items.append(
            f"<li><details><summary>{line}</summary><pre>{e(a['detail'])}</pre></details></li>"
            if a.get("detail")
            else f"<li>{line}</li>"
        )
    return f"<ol>{''.join(items)}</ol>"


def file_list(names: list[str], limit: int = 10) -> str:
    if not names:
        return ""
    more = f"<li class=muted>… {len(names) - limit} more</li>" if len(names) > limit else ""
    return f"<ul class=small>{''.join(f'<li><code>{html.escape(f)}</code></li>' for f in names[:limit])}{more}</ul>"


def branch(css: str, kind: str, title: str, body: str = "", children: str = "", open_: bool = False) -> str:
    """One node of the tree; with a body it unfolds (like a subagent in the VS Code panel)."""
    inner = (
        f"<details{' open' if open_ else ''}><summary><span class=kind>{kind}</span><b>{title}</b></summary>{body}"
        f"</details>"
        if body
        else f"<span class=kind>{kind}</span><b>{title}</b>"
    )
    return f'<li><div class="node {css}">{inner}</div>{f"<ul>{children}</ul>" if children else ""}</li>'


def tank(n: int, most: int) -> str:
    """A step's tokens as a level against the heaviest step of the session."""
    return (
        f'<div class=tank title="tokens: the main session and its agents"><span><i style="width:'
        f'{max(2, round(100 * n / most)) if most else 0}%"></i></span>{amount(n)}</div>'
    )


def cost(c: Counter) -> str:
    return f"<span class=cost>{amount(sum(c.values()))}</span>" if sum(c.values()) else ""


def column(i: int, t: dict, most: int = 0) -> str:
    e = html.escape
    text = (
        f"<details class=full><summary>prompt</summary><p class=ptext>{e(t['prompt'])}</p></details>"
        if len(t["prompt"]) > 300
        else f"<p class=ptext>{e(t['prompt'])}</p>"
    )
    head = (
        f'<div class="node prompt"><span class=n>{i}</span><span class=when>{when(t["ts"])}</span>{text}'
        f"{tank(t.get('total', 0), most)}</div>"
    )

    def rows_of(kind):
        return "".join(
            f'<p class="row{" taken" if x["taken"] else ""}"><span class=id>{e(x["id"])}</span>{e(x["text"][:220])}</p>'
            for x in t[kind]
        )

    kids = ""
    if t["F"]:
        kids += branch("F", "findings", f"{len(t['F'])} written", rows_of("F"), open_=True)
    if t["D"]:
        kids += branch("D", "decisions", f"{len(t['D'])} written", rows_of("D"), open_=True)
    tree = ""
    if t["acts"] or kids:
        kinds = Counter(a["kind"] for a in t["acts"])
        changed = sorted({f for a in t["acts"] if a["kind"] == "change" for f in a["files"]})
        tree += branch(
            "main",
            "Claude · main session",
            f"{len(t['acts'])} actions{cost(t.get('tokens', Counter()))}",
            chips(kinds) + file_list(changed) + actions(t["acts"]),
            kids,
        )
    for a in t["agents"]:
        status = "<span class=status>done</span>" if a["done"] else '<span class="status busy">not finished</span>'
        tree += branch(
            "sub",
            f"agent · {e(a['type'])}",
            e(a["name"]) + cost(a.get("tokens", Counter())),
            status + chips(a["kinds"]) + file_list(a["changed"]) + actions(a["acts"]),
        )
    tree += "".join(branch("rep", "agent reported", e(r)) for r in t["reports"])
    return f"<div class=col>{head}{f'<ul class=tree>{tree}</ul>' if tree else ''}</div>"


def render(s: dict, repo: Path, above: str = "") -> str:
    e, k = html.escape, s["kinds"]
    tk = s["tokens"]
    stats = (
        f'<div class="stat hero"><b>{amount(s["total"])}</b>tokens in total · {amount(tk["output"])} output · '
        f"{amount(tk['input'] + tk['cache_write'])} fresh input · {amount(tk['cache_read'])} from cache</div>"
    ) + "".join(
        f"<div class=stat><b>{n}</b>{label}</div>"
        for n, label in [
            (len(s["turns"]), "prompts"),
            (s["agents"], "subagents"),
            (k["read"], "reads"),
            (k["change"], "file edits"),
            (k["run"], "commands run"),
            (s["F"], "findings"),
            (s["D"], "decisions"),
        ]
    )
    most = max((t["total"] for t in s["turns"]), default=0)
    body = above + (
        f'<div class=intro><p><a href="index.html">← all sessions</a></p><span class=eyebrow>'
        f"{e(product()[0])} · what Claude did</span><h1>Session <i>{e(s['id'][:8])}</i></h1>"
        f"<p class=muted>{when(s['first'])} → {when(s['last'])} · <code>{e(repo.name)}</code></p>"
        f"<div class=stats>{stats}</div><div class=grid>"
        f"<div class=card><h2>Way of working: what Claude read</h2><ul>{way_of_working(s, repo)}</ul></div>"
        f"<div class=card><h2>Files changed</h2>{files(s['changed'])}</div>"
        f"<div class=card><h2>Files read</h2>{files(s['read'])}</div></div>"
        f"<h2>Timeline: one prompt per column, scroll sideways →</h2><p class=muted>Under each prompt: the main "
        f"session with its findings and decisions, and every agent it started. Open a node for its steps (R read · "
        f"W write/edit · $ command · ? question to you), a step for its command.</p></div><div class=pipe>"
        + "".join(column(i, t, most) for i, t in enumerate(s["turns"], 1))
        + "</div>"
    )
    return page(f"Session {s['id'][:8]}", body)


def render_index(sessions: list[dict], repo: Path) -> str:
    e = html.escape
    rows_ = "".join(
        f'<tr><td><a href="{e(s["id"])}.html">{when(s["first"]) or e(s["id"][:8])}</a></td><td>{when(s["last"])}</td>'
        f"<td>{len(s['turns'])}</td><td>{s['agents']}</td><td>{s['kinds']['change']}</td><td>{s['kinds']['run']}</td>"
        f"<td>{s['F']}</td><td>{s['D']}</td><td class=num>{amount(s['total'])}</td>"
        f"<td>{e((s['turns'] or [{'prompt': ''}])[0]['prompt'][:90])}</td></tr>"
        for s in sessions
    )
    total = sum(s["total"] for s in sessions)
    head = f"<span class=eyebrow>{e(product()[0])} · what Claude did</span><h1>Claude <i>sessions</i></h1>"
    body = (
        f"{head}<p class=muted>Every Claude Code session in <code>{e(str(repo))}</code>, newest first.</p>"
        f'<div class=stats><div class="stat hero"><b>{amount(total)}</b>tokens over {len(sessions)} sessions</div>'
        f"</div><div class='wrap glass'><table><tr><th>Started</th><th>Last prompt</th><th>Prompts</th><th>Agents</th>"
        f"<th>Edits</th><th>Commands</th><th>Findings</th><th>Decisions</th><th>Tokens</th><th>First prompt</th></tr>"
        f"{rows_}<tfoot><tr><td colspan=8>All sessions</td><td class=num>{amount(total)}</td><td></td></tr></tfoot>"
        f"</table></div>"
        if sessions
        else f"{head}<p class=muted>No sessions found for this repository.</p>"
    )
    return page("Claude sessions", body)


def sessions(repo: Path, projects: Path) -> list[dict]:
    """Every session of the repository, newest first."""
    found = sorted(project_dir(repo, projects).glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [summary(p, repo) for p in found]


def build(repo: Path, projects: Path, out: Path, found: list[dict] | None = None) -> Path:
    """Write a page per session and the index; return the index."""
    out.mkdir(parents=True, exist_ok=True)
    found = sessions(repo, projects) if found is None else found
    for s in found:
        (out / f"{s['id']}.html").write_text(render(s, repo), encoding="utf-8")
    index = out / "index.html"
    index.write_text(render_index(found, repo), encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps({"sessions": len(found), "tokens": amount(sum(s["total"] for s in found))}), encoding="utf-8"
    )
    return index


def main(argv: list[str], run=subprocess.run) -> int:
    named, flags, rest = {}, set(), list(argv)
    while rest:
        a = rest.pop(0)
        if a in ("--projects", "--out") and rest:
            named[a] = Path(rest.pop(0))
        elif a == "--open":
            flags.add(a)
        else:
            print(
                "usage: python3 crissp/testsuite/lib/sessionview.py [--open] [--projects DIR] [--out DIR]",
                file=sys.stderr,
            )
            return 2
    index = build(ROOT, named.get("--projects", PROJECTS), named.get("--out", OUT))
    print(index)
    if "--open" in flags:
        run(["open", str(index)], check=False)
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script; main() is tested
    sys.exit(main(sys.argv[1:]))
