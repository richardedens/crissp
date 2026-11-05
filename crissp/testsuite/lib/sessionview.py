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
import project  # noqa: E402

ROOT = project.root()  # the project whose sessions these are (CRISSP_ROOT, or the current directory)
OUT = project.results(ROOT) / "sessions"
LOOK = Path(__file__).resolve().parents[2] / "look"  # the shared look, beside this engine
PROJECTS = Path.home() / ".claude" / "projects"

SECRET = re.compile(r"(?i)((?:token|password|passwd|secret|api[_-]?key|bearer)[\"'=: ]+)[^\s\"']+")
INJECTED = re.compile(r"<(system-reminder|browser_instruction|ide_[a-z_]+|command-[a-z]+)>.*?</\1>", re.S)
ROW = re.compile(r"(?:^|(?<=['\"]))\|\s*(~~)?([FD]-\d+)(?:~~)?\s*\|([^|\n]*)\|([^|\n]*)\|", re.M)
REDIRECT = re.compile(r"(?:^|(?<=[\s;|&)]))>>?\s*([\w@-]*[./][\w./@-]*)")  # `> file`, `>> dir/f`; not 2>, =>, ->
READING = ("cat ", "sed -n", "grep ", "ls", "head ", "tail ", "find ", "wc ", "git log", "git status", "git diff",
           "git show", "rg ")
WAY_OF_WORKING = ("CLAUDE.md", "crissp/CLAUDE.md", "AGENTS.md", "crissp/AGENTS.md", "crissp/CRISSP.md", "crissp/ARCHITECTURE.md", "README.md",
                  "crissp/backlog/README.md", "crissp/backlog/PLAN.md", "crissp/backlog/DECISIONS.md",
                  "crissp/backlog/FINDINGS.md", "crissp/testsuite/README.md", "crissp/README.md")
# What Claude Code loads by itself at the start: the root CLAUDE.md and what it imports.
AUTO = ("CLAUDE.md", "crissp/CLAUDE.md")
# Where things lived before (2026-10-23): the way of working went from the root into a hidden .crissp/, then into a
# visible crissp/ together with the testsuite and the check, deploy and dashboard scripts. Older sessions name the old places.
MOVED = ((".crissp/", "crissp/"), ("backlog/", "crissp/backlog/"), ("CRISSP.md", "crissp/CRISSP.md"),
         ("ARCHITECTURE.md", "crissp/ARCHITECTURE.md"), ("testsuite/", "crissp/testsuite/"), ("check.sh", "crissp/check.sh"),
         ("check-all.sh", "crissp/check-all.sh"), ("deploy.sh", "crissp/deploy.sh"), ("test.sh", "crissp/test.sh"))


def moved(rel: str) -> str:
    """A repository path by its current place: the old place of a moved file becomes its new one."""
    for old, new in MOVED:
        if rel == old or (old.endswith("/") and rel.startswith(old)):
            return new + rel[len(old):]
    return rel
ICON = {"read": "R", "change": "W", "run": "$", "ask": "?", "other": "·"}


def project_dir(repo: Path, projects: Path = PROJECTS) -> Path:
    """Where Claude Code keeps this repository's transcripts: its path with every other character as '-'."""
    return projects / re.sub(r"[^A-Za-z0-9]", "-", str(repo))


def mask(text: str) -> str:
    return SECRET.sub(r"\1•••", text)


def records(path: Path):
    for line in path.read_text(errors="replace").splitlines():
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
    return [{"id": m.group(2), "text": (m.group(4) if kind == "F" else m.group(3)).strip(), "taken": bool(m.group(1))}
            for m in ROW.finditer(text) if m.group(2).startswith(kind)]


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
        into = {rel for t in REDIRECT.findall(line) if (rel := repo.rel(t if t.startswith("/") else
                                                                         str(Path(cwd or repo.root) / t)))}
        kind = "change" if into else ("read" if command.lstrip().startswith(READING) else "run")
        text = given.get("description") or (command.splitlines() or [""])[0][:120]
        act = {"kind": kind, "text": mask(text), "detail": mask(command), "files": into or repo.mentioned(command, cwd)}
    elif name == "AskUserQuestion":
        act = {"kind": "ask", "text": " · ".join(q.get("question", "") for q in given.get("questions", [])),
               "files": set()}
    else:
        act = {"kind": "other", "text": name, "files": set()}
    act["rows"] = written_rows(name, given)
    return act


def usage(record: dict) -> Counter:
    """The tokens of one API response: fresh input, output, cache reads and cache writes."""
    u = (record.get("message") or {}).get("usage") or {}
    return Counter({"input": u.get("input_tokens", 0), "output": u.get("output_tokens", 0),
                    "cache_read": u.get("cache_read_input_tokens", 0),
                    "cache_write": u.get("cache_creation_input_tokens", 0)})


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
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"] if isinstance(content, list) else []


def subagents(path: Path, repo: Repo) -> dict[str, dict]:
    """Each subagent of the session, by the id of the tool call that started it: what it was and what it did."""
    out = {}
    for meta in sorted((path.with_suffix("") / "subagents").glob("*.meta.json")):
        try:
            info = json.loads(meta.read_text())
        except json.JSONDecodeError:
            info = {}
        transcript = meta.with_name(meta.name.removesuffix(".meta.json") + ".jsonl")
        own = list(records(transcript)) if transcript.is_file() else []
        acts = [action(b, repo, r.get("cwd")) for r in own for b in tool_uses(r) if b.get("id") != info.get("toolUseId")]
        out[info.get("toolUseId") or meta.name] = {
            "name": info.get("description") or meta.name.removesuffix(".meta.json"),
            "type": info.get("agentType", "agent"), "kinds": Counter(a["kind"] for a in acts),
            "changed": sorted({f for a in acts if a["kind"] == "change" for f in a["files"]}), "acts": acts,
            "done": info.get("finished", False), "tokens": tokens(own, skip=info.get("toolUseId"))}
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
            turns.append({"ts": ts, "prompt": "(before the first prompt)", "acts": [], "agents": [], "reports": [],
                          "F": [], "D": [], "tokens": Counter()})
        return turns[-1]

    for r in records(path):
        if r.get("isSidechain"):
            continue
        text = prompt(r)
        if text and text.startswith("<task-notification>"):
            summary = re.search(r"<summary>(.*?)</summary>", text, re.S)
            turn(r.get("timestamp"))["reports"].append(mask(summary.group(1).strip() if summary else "an agent reported"))
        elif text:
            turns.append({"ts": r.get("timestamp"), "prompt": text, "acts": [], "agents": [], "reports": [],
                          "F": [], "D": [], "tokens": Counter()})
        mid = (r.get("message") or {}).get("id")
        if r.get("type") == "assistant" and mid and mid not in counted:
            counted.add(mid)
            turn(r.get("timestamp"))["tokens"].update(usage(r))
        for b in tool_uses(r):
            t = turn(r.get("timestamp"))
            if b.get("name") == "Agent":
                given = b.get("input") or {}
                t["agents"].append(agents.get(b.get("id")) or {"name": given.get("description", "agent"),
                                   "type": given.get("subagent_type", "agent"), "kinds": Counter(), "changed": [],
                                   "acts": [], "done": False, "tokens": Counter()})
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
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%a %d %b %H:%M")
    except (AttributeError, ValueError):
        return ""


def summary(path: Path, repo_root: Path) -> dict:
    repo = Repo(repo_root, session_root(path))
    turns = parse(path, repo)
    acts = [a for t in turns for a in t["acts"]]
    stamps = [t["ts"] for t in turns if t["ts"]]
    return {"id": path.stem, "turns": turns, "first": min(stamps, default=None), "last": max(stamps, default=None),
            "kinds": Counter(a["kind"] for a in acts),
            "read": Counter(f for a in acts if a["kind"] == "read" for f in a["files"]),
            "changed": Counter(f for a in acts if a["kind"] == "change" for f in a["files"]),
            "agents": sum(len(t["agents"]) for t in turns), "F": sum(len(t["F"]) for t in turns),
            "D": sum(len(t["D"]) for t in turns),
            "tokens": sum((t["tokens"] + sum((a["tokens"] for a in t["agents"]), Counter()) for t in turns), Counter()),
            "total": sum(t["total"] for t in turns)}


def amount(n: int) -> str:
    """1234 → 1.2k, 3400000 → 3.4M."""
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


STYLE = """
:root{--font:'Figtree',-apple-system,'SF Pro Text',system-ui,sans-serif;--mono:'JetBrains Mono',ui-monospace,Menlo,monospace;
--bg:#0a0b10;--ink:#eceef5;--ink-2:#c9cbd6;--muted:#9a9cab;--faint:#696c7c;--line:rgba(181,138,255,.13);
--line-strong:rgba(181,138,255,.28);--hair:rgba(255,255,255,.06);--glass:rgba(19,19,28,.56);--glass-strong:rgba(16,16,24,.86);
--accent:#b58aff;--accent-2:#7b2ff7;--teal:#3dd6c6;--blue:#6ea8ff;--ok:#7ee2a8;--warn:#ffb454;--bad:#ff6b6b;--pink:#f062c0;
--shadow:0 30px 80px -40px rgba(0,0,0,.75),0 2px 6px -2px rgba(0,0,0,.35);--radius:16px;color-scheme:dark}
[data-theme=light]:root{--bg:#f3f2f8;--ink:#17151f;--ink-2:#34313f;--muted:#5f5c6d;--faint:#8b8898;
--line:rgba(91,63,208,.14);--line-strong:rgba(91,63,208,.3);--hair:rgba(23,21,31,.06);--glass:rgba(255,255,255,.66);
--glass-strong:rgba(255,255,255,.94);--accent:#6c3cf0;--accent-2:#5a24e0;--teal:#0f9f92;--blue:#2f6fe0;--ok:#16a06a;
--warn:#c47a00;--bad:#d93a4a;--pink:#cd148e;--shadow:0 30px 70px -40px rgba(40,20,90,.35),0 2px 6px -2px rgba(40,20,90,.12);
color-scheme:light}
*{box-sizing:border-box}html,body{margin:0;min-height:100%;background:var(--bg);color:var(--ink);
font:14px/1.5 var(--font);-webkit-font-smoothing:antialiased}::selection{background:rgba(181,138,255,.35)}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}
.water{position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden}
.water canvas{position:absolute;inset:0;width:100%;height:100%;opacity:.8}
[data-theme=light] .water canvas{opacity:.16;filter:saturate(1.4) hue-rotate(-8deg)}
.water i{position:absolute;inset:0;background:radial-gradient(1200px 700px at 78% -10%,rgba(123,47,247,.18),transparent 60%),
radial-gradient(900px 600px at -10% 110%,rgba(61,214,198,.08),transparent 60%),linear-gradient(180deg,rgba(10,11,16,.2),rgba(10,11,16,.6) 85%)}
[data-theme=light] .water i{background:radial-gradient(1200px 700px at 78% -10%,rgba(124,77,255,.14),transparent 60%),
linear-gradient(180deg,rgba(243,242,248,.3),rgba(243,242,248,.8) 85%)}
main{position:relative;z-index:1;padding:28px 16px 40px}.intro{max-width:1180px}
.glass,.stat,.card,.node{background:var(--glass);border:1px solid var(--line);border-radius:var(--radius);
box-shadow:var(--shadow),inset 0 1px var(--hair);backdrop-filter:blur(22px) saturate(140%);-webkit-backdrop-filter:blur(22px) saturate(140%)}
.eyebrow{font-size:10.5px;font-weight:600;letter-spacing:2.2px;text-transform:uppercase;color:var(--muted)}
h1{font:700 30px/1.1 var(--font);letter-spacing:-.9px;margin:6px 0}h1 i{font-style:normal;color:var(--accent)}
h2{font-size:10.5px;font-weight:600;letter-spacing:2.2px;text-transform:uppercase;color:var(--muted);margin:0 0 10px}
.muted{color:var(--muted)}code{font:12px var(--mono);overflow-wrap:anywhere;color:var(--ink-2)}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin:18px 0}
.stat{padding:12px 14px;border-radius:14px;color:var(--muted);font-size:12px}
.stat b{display:block;font:700 24px/1.1 var(--font);letter-spacing:-.6px;color:var(--ink)}
.stat.hero{grid-column:span 2;background:linear-gradient(135deg,rgba(123,47,247,.28),rgba(61,214,198,.12)),var(--glass);
border-color:var(--line-strong)}.stat.hero b{font-size:32px;background:linear-gradient(90deg,var(--accent),var(--teal));
-webkit-background-clip:text;background-clip:text;color:transparent}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,330px),1fr));gap:12px;margin-bottom:24px}
.card{padding:16px}ul{list-style:none;margin:0;padding:0}
.card li{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)}
.card li:last-child{border:0}li.auto span{color:var(--ok)}li.read span{color:var(--blue)}li.never span{color:var(--bad);font-weight:600}
.pipe{display:flex;overflow-x:auto;align-items:flex-start;padding:6px 0 24px;scroll-snap-type:x proximity;
scrollbar-color:var(--line-strong) transparent}
.col{flex:0 0 350px;position:relative;padding:0 12px;scroll-snap-align:start}
.col::before{content:"";position:absolute;top:30px;left:0;right:0;height:2px;
background:linear-gradient(90deg,var(--accent-2),var(--teal),var(--accent-2));background-size:300% 100%;
animation:flow 9s linear infinite;opacity:.75}
.col:first-child::before{left:50%}.col:last-child::before{right:50%}
@keyframes flow{to{background-position:300% 0}}
.node{position:relative;z-index:1;padding:10px 12px;border-radius:14px;min-width:0;overflow-wrap:anywhere;
transition:border-color .2s,transform .2s,box-shadow .2s}
.node:hover{border-color:var(--line-strong);transform:translateY(-1px);box-shadow:var(--shadow),0 0 0 1px var(--line-strong),
0 0 28px -8px rgba(181,138,255,.45)}
.node.prompt{border-top:2px solid var(--accent)}.n{display:inline-grid;place-items:center;min-width:24px;height:24px;
padding:0 6px;border-radius:12px;margin-right:8px;font:700 12px var(--font);color:#fff;
background:linear-gradient(135deg,var(--accent),var(--accent-2));box-shadow:0 0 16px -2px rgba(123,47,247,.7)}
.when{color:var(--muted);font-size:12px}.ptext{margin:8px 0 0;white-space:pre-wrap;display:-webkit-box;-webkit-line-clamp:5;
-webkit-box-orient:vertical;overflow:hidden;color:var(--ink-2)}details.full>summary{cursor:pointer;color:var(--muted);font-size:12px;margin-top:6px}
details.full[open] .ptext{-webkit-line-clamp:unset}
.tank{display:flex;align-items:center;gap:8px;margin-top:10px;font:600 11px var(--mono);color:var(--muted)}
.tank span{flex:1;height:8px;border-radius:5px;background:rgba(181,138,255,.1);overflow:hidden;position:relative}
.tank i{position:absolute;inset:0 auto 0 0;border-radius:5px;background:linear-gradient(90deg,var(--teal),var(--accent),var(--teal));
background-size:200% 100%;animation:flow 4s linear infinite;box-shadow:0 0 12px rgba(61,214,198,.5)}
.tree,.tree ul{list-style:none;margin:0;padding:0 0 0 22px}.tree{margin-left:14px}
.tree li{position:relative;padding:12px 0 0}
.tree li::before{content:"";position:absolute;left:-15px;top:0;bottom:0;width:2px;
background:linear-gradient(180deg,var(--line-strong),var(--line))}
.tree li:last-child::before{bottom:auto;height:30px}
.tree li::after{content:"";position:absolute;left:-15px;top:30px;width:15px;height:2px;background:var(--line-strong)}
.node.main{box-shadow:var(--shadow),inset 3px 0 var(--blue)}.node.sub{box-shadow:var(--shadow),inset 3px 0 var(--accent)}
.node.F{box-shadow:var(--shadow),inset 3px 0 var(--warn)}.node.D{box-shadow:var(--shadow),inset 3px 0 var(--teal)}
.node.rep{border-style:dashed;box-shadow:none}
.kind{display:block;margin-bottom:2px;font-size:10px;font-weight:600;letter-spacing:1.8px;text-transform:uppercase;color:var(--muted)}
.sub .kind,.rep .kind{color:var(--accent)}.main .kind{color:var(--blue)}.F .kind{color:var(--warn)}.D .kind{color:var(--teal)}
.node>details>summary{cursor:pointer;list-style:none}.node>details>summary::-webkit-details-marker{display:none}
.node>details>summary b::before{content:"▸ ";color:var(--muted)}.node>details[open]>summary b::before{content:"▾ "}
.cost{float:right;font:600 11px var(--mono);color:var(--teal)}
.status{float:right;margin-left:8px;font-size:11px;color:var(--ok)}.status.busy{color:var(--warn)}
.chip{display:inline-block;margin:6px 4px 0 0;padding:1px 7px;border-radius:9px;font:11px var(--mono);
border:1px solid currentColor;background:rgba(255,255,255,.02)}
.read{color:var(--blue)}.change{color:var(--warn)}.run{color:var(--ink-2)}.ask{color:var(--teal)}.other{color:var(--faint)}
.small{font-size:12px;margin:6px 0 0}.row{margin:6px 0 0;font-size:13px;color:var(--ink-2)}
.row .id{font:700 12px var(--mono);margin-right:6px}.F .id{color:var(--warn)}.D .id{color:var(--teal)}
.row.taken .id{text-decoration:line-through}
.acts>summary{cursor:pointer;color:var(--muted);font-size:12px;margin-top:6px}ol{list-style:none;padding:0;margin:6px 0 0}
ol li{padding:4px 0;border-top:1px solid var(--line);font-size:12px;overflow-wrap:anywhere}ol summary{cursor:pointer;list-style:none}
.ico{display:inline-block;width:16px;font:700 11px var(--mono)}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px var(--mono);background:rgba(0,0,0,.25);color:var(--ink-2);
padding:8px;border-radius:8px;margin:4px 0;max-height:240px;overflow:auto}
table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:10px 12px;border-bottom:1px solid var(--line)}
th{font-size:10.5px;font-weight:600;letter-spacing:1.6px;text-transform:uppercase;color:var(--muted)}
tr:last-child td{border:0}tfoot td{font-weight:700;border-top:1px solid var(--line-strong)}
td.num{font-family:var(--mono);text-align:right}.wrap{overflow-x:auto;border-radius:var(--radius)}
.top{position:sticky;top:0;z-index:5;display:flex;align-items:center;gap:24px;padding:12px 24px;flex-wrap:wrap;
background:color-mix(in srgb,var(--bg) 70%,transparent);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);
border-bottom:1px solid var(--line)}.brand{display:flex;gap:12px;align-items:center}
.logo{display:grid;place-items:center;width:34px;height:34px;border-radius:9px;background:var(--accent-2);color:#fff;font-weight:800}
.top h1{margin:0;font:600 16px var(--font);letter-spacing:0}.brand p{margin:0;color:var(--muted);font-size:12px}
.top nav{display:flex;gap:4px;flex:1;flex-wrap:wrap}.top nav a{color:var(--muted);padding:7px 12px;border-radius:8px;
font:500 13px var(--font)}.top nav a:hover{color:var(--ink);text-decoration:none}
.top nav a.on{background:var(--glass-strong);color:var(--ink)}
.ghost{border:1px solid var(--line);background:none;color:var(--ink);border-radius:8px;padding:6px 10px;cursor:pointer;font:13px var(--font)}
@media (prefers-reduced-motion:reduce){.col::before,.tank i{animation:none}.node{transition:none}}"""

# The water of the shared look (crissp/look/water.js, plain WebGL), built into these pages so they also work alone.
WATER_JS = LOOK / "water.js"


def water() -> str:
    return WATER_JS.read_text() if WATER_JS.is_file() else ""


# The shared look's type, Figtree (OFL-1.1, crissp/look/LICENSE-figtree.txt), inside the page: it loads nothing.
FONT = LOOK / "figtree-latin-variable.woff2"
# The shared theme (crissp/look/look.js): dark by default, light when chosen, remembered under the same key.
THEME = "try{const t=localStorage.getItem('crissp.theme');if(t)document.documentElement.dataset.theme=t}catch(e){}"
TOGGLE = ("document.getElementById('theme').onclick=()=>{const r=document.documentElement;"
          "r.dataset.theme=r.dataset.theme==='light'?'dark':'light';try{localStorage.setItem('crissp.theme',r.dataset.theme)}"
          "catch(e){}};")
TABS = (("overview", "Overview"), ("changes", "Changes"), ("tests", "Tests"), ("coverage", "Coverage"),
        ("journeys", "Journeys"), ("e2e", "E2E"), ("steps", "Runs & logs"), ("gaps", "Known gaps"))


def product() -> tuple[str, str]:
    """The product's name and monogram, as the dashboard has them (crissp/testsuite/suites.json)."""
    try:
        conf = json.loads((ROOT / "crissp" / "testsuite" / "suites.json").read_text())
    except (OSError, json.JSONDecodeError):
        conf = {}
    name = conf.get("product", ROOT.name)
    return name, conf.get("monogram", name[:1].upper())


def top_bar(title: str) -> str:
    """The shared top bar: the brand, the sections (Tests · UX · Sessions, this one open) and the dashboard's tabs."""
    name, mono = product()
    tabs = "".join(f'<a href="../../dashboard/#{k}">{t}</a>' for k, t in TABS)
    return (f'<header class=top><div class=brand><span class=logo>{html.escape(mono)}</span><div><h1>{html.escape(name)} '
            f'· Sessions</h1><p>{html.escape(title)}</p></div></div><nav class=sections aria-label=Sections>'
            f'<a href="../../dashboard/">Tests</a><a href="../../ux/">UX</a><a class=on aria-current=page href="index.html">'
            f'Sessions</a></nav><nav class=tabs>{tabs}</nav><button id=theme class=ghost title="Light / dark" '
            f'aria-label="Light or dark">◐</button></header>')


def font_face() -> str:
    data = base64.b64encode(FONT.read_bytes()).decode() if FONT.is_file() else ""
    return (f'@font-face{{font-family:"Figtree";font-style:normal;font-display:swap;font-weight:300 900;'
            f'src:url(data:font/woff2;base64,{data}) format("woff2")}}' if data else "")


def page(title: str, body: str) -> str:
    """A page in the shared look under its top bar: dark by default (light when chosen, remembered), water underneath."""
    return (f"<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content=\"width=device-width,"
            f"initial-scale=1\"><title>{html.escape(title)}</title><script>{THEME}</script><style>{font_face()}{STYLE}"
            f"</style><div class=water aria-hidden=true><canvas></canvas><i></i></div>{top_bar(title)}<main>{body}</main>"
            f"<script>{TOGGLE}{water()}</script></html>")


def way_of_working(s: dict, repo: Path) -> str:
    out = []
    for f in WAY_OF_WORKING:
        if not (repo / f).is_file():
            continue
        read, written = s["read"][f], s["changed"][f]
        parts = (["loaded at start"] if f in AUTO else []) + ([f"read {read}×"] if read else []) \
            + ([f"written {written}×"] if written else [])
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
        items.append(f'<li><details><summary>{line}</summary><pre>{e(a["detail"])}</pre></details></li>'
                     if a.get("detail") else f"<li>{line}</li>")
    return f"<ol>{''.join(items)}</ol>"


def file_list(names: list[str], limit: int = 10) -> str:
    if not names:
        return ""
    more = f"<li class=muted>… {len(names) - limit} more</li>" if len(names) > limit else ""
    return f'<ul class=small>{"".join(f"<li><code>{html.escape(f)}</code></li>" for f in names[:limit])}{more}</ul>'


def branch(css: str, kind: str, title: str, body: str = "", children: str = "", open_: bool = False) -> str:
    """One node of the tree; with a body it unfolds (like a subagent in the VS Code panel)."""
    inner = (f'<details{" open" if open_ else ""}><summary><span class=kind>{kind}</span><b>{title}</b></summary>{body}'
             f"</details>" if body else f"<span class=kind>{kind}</span><b>{title}</b>")
    return f'<li><div class="node {css}">{inner}</div>{f"<ul>{children}</ul>" if children else ""}</li>'


def tank(n: int, most: int) -> str:
    """A step's tokens as a level against the heaviest step of the session."""
    return (f'<div class=tank title="tokens: the main session and its agents"><span><i style="width:'
            f'{max(2, round(100 * n / most)) if most else 0}%"></i></span>{amount(n)}</div>')


def cost(c: Counter) -> str:
    return f'<span class=cost>{amount(sum(c.values()))}</span>' if sum(c.values()) else ""


def column(i: int, t: dict, most: int = 0) -> str:
    e = html.escape
    text = (f'<details class=full><summary>prompt</summary><p class=ptext>{e(t["prompt"])}</p></details>'
            if len(t["prompt"]) > 300 else f'<p class=ptext>{e(t["prompt"])}</p>')
    head = (f'<div class="node prompt"><span class=n>{i}</span><span class=when>{when(t["ts"])}</span>{text}'
            f'{tank(t.get("total", 0), most)}</div>')

    def rows_of(kind):
        return "".join(f'<p class="row{" taken" if x["taken"] else ""}"><span class=id>{e(x["id"])}</span>'
                       f'{e(x["text"][:220])}</p>' for x in t[kind])
    kids = ""
    if t["F"]:
        kids += branch("F", "findings", f'{len(t["F"])} written', rows_of("F"), open_=True)
    if t["D"]:
        kids += branch("D", "decisions", f'{len(t["D"])} written', rows_of("D"), open_=True)
    tree = ""
    if t["acts"] or kids:
        kinds = Counter(a["kind"] for a in t["acts"])
        changed = sorted({f for a in t["acts"] if a["kind"] == "change" for f in a["files"]})
        tree += branch("main", "Claude · main session", f'{len(t["acts"])} actions{cost(t.get("tokens", Counter()))}',
                       chips(kinds) + file_list(changed) + actions(t["acts"]), kids)
    for a in t["agents"]:
        status = '<span class=status>done</span>' if a["done"] else '<span class="status busy">not finished</span>'
        tree += branch("sub", f'agent · {e(a["type"])}', e(a["name"]) + cost(a.get("tokens", Counter())),
                       status + chips(a["kinds"]) + file_list(a["changed"]) + actions(a["acts"]))
    tree += "".join(branch("rep", "agent reported", e(r)) for r in t["reports"])
    return f'<div class=col>{head}{f"<ul class=tree>{tree}</ul>" if tree else ""}</div>'


def render(s: dict, repo: Path, above: str = "") -> str:
    e, k = html.escape, s["kinds"]
    tk = s["tokens"]
    stats = (f'<div class="stat hero"><b>{amount(s["total"])}</b>tokens in total · {amount(tk["output"])} output · '
             f'{amount(tk["input"] + tk["cache_write"])} fresh input · {amount(tk["cache_read"])} from cache</div>') + \
        "".join(f"<div class=stat><b>{n}</b>{label}</div>" for n, label in [
        (len(s["turns"]), "prompts"), (s["agents"], "subagents"), (k["read"], "reads"), (k["change"], "file edits"),
        (k["run"], "commands run"), (s["F"], "findings"), (s["D"], "decisions")])
    most = max((t["total"] for t in s["turns"]), default=0)
    body = above + (f'<div class=intro><p><a href="index.html">← all sessions</a></p><span class=eyebrow>'
            f'{e(product()[0])} · what Claude did</span><h1>Session <i>{e(s["id"][:8])}</i></h1>'
            f'<p class=muted>{when(s["first"])} → {when(s["last"])} · <code>{e(repo.name)}</code></p>'
            f'<div class=stats>{stats}</div><div class=grid>'
            f'<div class=card><h2>Way of working: what Claude read</h2><ul>{way_of_working(s, repo)}</ul></div>'
            f'<div class=card><h2>Files changed</h2>{files(s["changed"])}</div>'
            f'<div class=card><h2>Files read</h2>{files(s["read"])}</div></div>'
            f'<h2>Timeline: one prompt per column, scroll sideways →</h2><p class=muted>Under each prompt: the main '
            f'session with its findings and decisions, and every agent it started. Open a node for its steps (R read · '
            f'W write/edit · $ command · ? question to you), a step for its command.</p></div><div class=pipe>'
            + "".join(column(i, t, most) for i, t in enumerate(s["turns"], 1)) + "</div>")
    return page(f"Session {s['id'][:8]}", body)


def render_index(sessions: list[dict], repo: Path) -> str:
    e = html.escape
    rows_ = "".join(
        f'<tr><td><a href="{e(s["id"])}.html">{when(s["first"]) or e(s["id"][:8])}</a></td><td>{when(s["last"])}</td>'
        f'<td>{len(s["turns"])}</td><td>{s["agents"]}</td><td>{s["kinds"]["change"]}</td><td>{s["kinds"]["run"]}</td>'
        f'<td>{s["F"]}</td><td>{s["D"]}</td><td class=num>{amount(s["total"])}</td>'
        f'<td>{e((s["turns"] or [{"prompt": ""}])[0]["prompt"][:90])}</td></tr>'
        for s in sessions)
    total = sum(s["total"] for s in sessions)
    head = f"<span class=eyebrow>{e(product()[0])} · what Claude did</span><h1>Claude <i>sessions</i></h1>"
    body = (f"{head}<p class=muted>Every Claude Code session in <code>{e(str(repo))}</code>, newest first.</p>"
            f'<div class=stats><div class="stat hero"><b>{amount(total)}</b>tokens over {len(sessions)} sessions</div>'
            f"</div><div class='wrap glass'><table><tr><th>Started</th><th>Last prompt</th><th>Prompts</th><th>Agents</th>"
            f"<th>Edits</th><th>Commands</th><th>Findings</th><th>Decisions</th><th>Tokens</th><th>First prompt</th></tr>"
            f"{rows_}<tfoot><tr><td colspan=8>All sessions</td><td class=num>{amount(total)}</td><td></td></tr></tfoot>"
            f"</table></div>" if sessions else f"{head}<p class=muted>No sessions found for this repository.</p>")
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
        (out / f"{s['id']}.html").write_text(render(s, repo))
    index = out / "index.html"
    index.write_text(render_index(found, repo))
    (out / "summary.json").write_text(json.dumps({"sessions": len(found), "tokens": amount(sum(s["total"] for s in found))}))
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
            print("usage: python3 crissp/testsuite/lib/sessionview.py [--open] [--projects DIR] [--out DIR]", file=sys.stderr)
            return 2
    index = build(ROOT, named.get("--projects", PROJECTS), named.get("--out", OUT))
    print(index)
    if "--open" in flags:
        run(["open", str(index)], check=False)
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script; main() is tested
    sys.exit(main(sys.argv[1:]))
