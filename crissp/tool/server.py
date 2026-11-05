"""crissp: the way of working as an MCP server, so Claude asks for the few lines it needs instead of reading whole files.

Local (stdio), standard library only; registered for Claude Code in .mcp.json at the repository root. It reads and
writes the same files people read (crissp/backlog/, VERSION, the release certificate), so it never knows more or other
than the repository says, and what it writes is plain Markdown in the backlog's own format, reviewed like any change.

Tools
- brief     where the work stands: version, commit, certificate, items doing / in review / next, open decisions, the number of open
            findings. Small enough to load at the start of every session.
- backlog   exactly what is asked: one finding, decision, epic, feature or PBI by its id (F-12, D-05, E8, E8-F1,
            E8-F1-01), the features and PBIs with a status, or the open findings or decisions.
- finding   writes a new finding (the next F-number) into FINDINGS.md.
- decision  writes a new open decision (the next D-number), or records one the product owner took.
- epic      writes a new epic: its own file E<n>-<slug>.md under the next number, listed in the backlog's README.
- feature   writes a new feature into an open epic (E8-F1, the epic's next feature number, status todo).
- item      writes a new PBI (backlog item) into a feature (E8-F1-01, the feature's next number, status todo), or moves a
            PBI or a feature to another status. Never to done: only the product owner accepts, and done work moves to
            done/.
The backlog is three levels: epic (E8) → feature (E8-F1) → PBI (E8-F1-01). Items from before features (E1-01) are read
and moved as they are until they are regrouped.
- run       starts a check: check (what changed) or check-all (the full run, the product owner's to start unless they ask)
            in the background, or answers at once: check-plan, deploy-plan, ux-status (what the UX team does and
            waits for). Never a deploy: that stays in the product owner's terminal; never a UX round: those cost tokens
            and are the product owner's to ask for (crissp/ux.sh).
- status    how the checks started with run are doing: running or finished, the exit code, the last lines of the log.
- dashboard builds the Tests dashboard's data and serves it with the UX suite (crissp/test.sh --dashboard, one local
            server); answers the address of the view asked for (tests or ux).
The writers are for the main session: agents never edit the backlog (crissp/AGENTS.md).

    python3 crissp/tool/server.py            (Claude Code starts it; it speaks MCP on stdin/stdout)

It works for the project CRISSP_ROOT names, or the current directory (Claude Code starts it in the project's root).
"""

import datetime
import json
import os
import re
import subprocess
import sys
import textwrap
import time
import urllib.request
from pathlib import Path

ROOT = Path(os.environ.get("CRISSP_ROOT") or os.getcwd()).resolve()  # the project; never this file's place
ENGINE = Path(__file__).resolve().parent.parent  # the framework this tool belongs to: its guards, when a project has none
PROTOCOL = "2025-06-18"
ITEM = re.compile(r"^### (E\d+(?:-F\d+)?-\d+) · (.+?)\s+\[(todo|doing|review|done|parked)\](?:\s+\[(\w+)\])?", re.M)
FEATURE = re.compile(r"^## (E\d+-F\d+) · (.+?)\s+\[(todo|doing|review|done|parked)\]", re.M)
EPIC = re.compile(r"^# (E\d+) · (.+)$", re.M)
HEADING = re.compile(r"^#{1,3} ", re.M)
ROW = re.compile(r"^\|\s*(~~)?([FD]-\d+)(?:~~)?\s*\|(.*)\|\s*$", re.M)
STATUSES = ("todo", "doing", "review", "done", "parked")
SIZES = ("S", "M", "L")
MAIN = " For the main session only: agents never edit the backlog."
# what run may start: name → (script in crissp/, its arguments, in the background). A deploy is not here, on purpose.
RUNS = {"check-plan": ("check.sh", ["--plan"], False), "deploy-plan": ("deploy.sh", ["--plan"], False),
        "ux-status": ("ux.sh", ["--status"], False), "check": ("check.sh", [], True), "check-all": ("check-all.sh", [], True)}
VIEWS = {"tests": "--dashboard", "ux": "--ux"}  # dashboard: which page of the one local server to answer
PLAN_TIMEOUT = 120  # seconds a plan may take
DASHBOARD_WAIT = 120  # seconds to wait for the dashboard to say where it is
EXIT = re.compile(r"^\[crissp\] exit (\d+)$", re.M)

TOOLS = [
    {"name": "brief",
     "description": "Where the work on this repository stands: version, commit, release certificate, backlog items doing "
                    "/ in review / next, open decisions, the number of open findings. Call it first in a session.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "backlog",
     "description": "Exactly the backlog lines asked for, instead of reading the backlog files: one finding, decision or "
                    "item by id (F-12, D-05, E7-01), the items with a status, or the open findings or decisions.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "id": {"type": "string", "description": "F-<n>, D-<n>, E<n>, E<n>-F<m> or E<n>-F<m>-<nn>"},
         "status": {"type": "string", "enum": list(STATUSES), "description": "the features and PBIs with this status"},
         "open": {"type": "string", "enum": ["findings", "decisions"], "description": "the open findings or decisions"}}}},
    {"name": "finding",
     "description": "Write a new finding (observation) into FINDINGS.md under the next F-number; answers its id." + MAIN,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["seen", "observation", "goes_to"],
                     "properties": {
         "seen": {"type": "string", "description": "where it was seen, with the date: `deploy.sh (2026-10-23)`"},
         "observation": {"type": "string", "description": "what was seen, in plain words"},
         "goes_to": {"type": "string", "description": "where it goes: an item (E5-01), a decision, a project, the product owner"}}}},
    {"name": "decision",
     "description": "Write a new open decision for the product owner (question, options, recommendation) under the next "
                    "D-number, or record one the product owner took (id, decision): it moves to Taken." + MAIN,
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "question": {"type": "string"}, "options": {"type": "string", "description": "a) … · b) …"},
         "recommendation": {"type": "string", "description": "the option Claude recommends, and why"},
         "id": {"type": "string", "description": "D-<n>: the open decision the product owner took"},
         "decision": {"type": "string", "description": "what the product owner decided, in their words where possible"},
         "date": {"type": "string", "description": "YYYY-MM-DD; today when left out"}}}},
    {"name": "epic",
     "description": "Write a new epic (title, why): its own file E<n>-<slug>.md under the next E-number, listed in the "
                    "backlog's README; then add its features with feature." + MAIN,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["title", "why"], "properties": {
         "title": {"type": "string"},
         "why": {"type": "string", "description": "why the epic exists, in the product owner's words where possible"}}}},
    {"name": "feature",
     "description": "Write a new feature into an open epic (epic, title, why) under the epic's next feature number "
                    "(E8-F1) with status todo; then add its PBIs with item." + MAIN,
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["epic", "title", "why"], "properties": {
         "epic": {"type": "string", "description": "E<n>, an open epic"}, "title": {"type": "string"},
         "why": {"type": "string", "description": "what this feature gives the user"}}}},
    {"name": "item",
     "description": "Write a new PBI (backlog item) into a feature (feature, title, size, why, what, done_when, tests, "
                    "depends) under the feature's next number (E8-F1-01) with status todo, or move a PBI or a feature to "
                    "another status (id, status). Never to done: only the product owner accepts." + MAIN,
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "feature": {"type": "string", "description": "E<n>-F<m>, a feature of an open epic"}, "title": {"type": "string"},
         "size": {"type": "string", "enum": list(SIZES), "description": "S ≤ half a day · M 1–2 days · L 3–5 days"},
         "why": {"type": "string"}, "what": {"type": "string"},
         "done_when": {"type": "string", "description": "acceptance criteria, observable and testable"},
         "tests": {"type": "string", "description": "which tests prove it"},
         "depends": {"type": "string", "description": "other items or decisions; — when none"},
         "id": {"type": "string", "description": "E<n>-F<m>-<nn> (a PBI) or E<n>-F<m> (a feature): what to move"},
         "status": {"type": "string", "enum": [s for s in STATUSES if s != "done"]}}}},
    {"name": "run",
     "description": "Start a check of this repository: check (tests what changed since the last green state) or "
                    "check-all (the full run; the product owner's to start unless they asked) in the background, then "
                    "follow it with status; or get an answer at once: check-plan (what check would run and how long), "
                    "deploy-plan (what a deploy would rebuild and why), ux-status (what the UX team runs and what "
                    "waits). It never deploys and never starts a UX round: those stay with the product owner. Commit "
                    "first: the checks test what is committed.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["what"], "properties": {
         "what": {"type": "string", "enum": list(RUNS)}}}},
    {"name": "status",
     "description": "How the checks started with run are doing: running or finished, the exit code, the last lines of "
                    "their log, and whether a run holds the lock.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "dashboard",
     "description": "Build the Tests dashboard's data from the last runs and serve it with the UX suite on 127.0.0.1 "
                    "(crissp/test.sh --dashboard: one local server); answers the address of the view asked for: tests "
                    "(what the runs proved, the backlog board; the default) or ux (rounds, advice, designs, verdicts). "
                    "Never runs a test.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "view": {"type": "string", "enum": list(VIEWS), "description": "tests (default) or ux"}}}},
]


def backlog_dir(root: Path) -> Path:
    return root / "crissp" / "backlog"


def read(path: Path) -> str:
    try:
        return path.read_text()
    except OSError:
        return ""


def epic_files(root: Path) -> list[Path]:
    return sorted(backlog_dir(root).glob("E*.md")) + sorted((backlog_dir(root) / "done").glob("E*.md"))


def until(text: str, start: int, end: re.Pattern) -> str:
    """From start to the next heading the pattern names (or the end of the file)."""
    eol = text.find("\n", start)
    nxt = end.search(text, eol + 1) if eol != -1 else None
    return text[start: nxt.start() if nxt else len(text)].strip()


def items(root: Path) -> list[dict]:
    """Every PBI of every epic, open and done: id, title, status, size, the file and its whole block."""
    out = []
    for f in epic_files(root):
        text = read(f)
        for m in ITEM.finditer(text):
            out.append({"id": m.group(1), "title": m.group(2).strip(), "status": m.group(3), "size": m.group(4) or "",
                        "file": str(f.relative_to(root)), "block": until(text, m.start(), HEADING)})
    return out


def features(root: Path) -> list[dict]:
    """Every feature of every epic, open and done: id, title, status, the file and its own lines (without its PBIs)."""
    out = []
    for f in epic_files(root):
        text = read(f)
        for m in FEATURE.finditer(text):
            out.append({"id": m.group(1), "title": m.group(2).strip(), "status": m.group(3),
                        "file": str(f.relative_to(root)), "block": until(text, m.start(), HEADING)})
    return out


def rows(root: Path, name: str) -> list[dict]:
    """The F-/D- rows of FINDINGS.md or DECISIONS.md, open first, then done: id, taken (struck), the cells, where."""
    out = []
    for f in (backlog_dir(root) / name, backlog_dir(root) / "done" / name):
        for m in ROW.finditer(read(f)):
            cells = [c.strip() for c in m.group(3).split("|")]
            out.append({"id": m.group(2), "taken": bool(m.group(1)), "cells": cells, "done": f.parent.name == "done",
                        "file": str(f.relative_to(root))})
    return out


def git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def open_findings(root: Path) -> list[dict]:
    return [r for r in rows(root, "FINDINGS.md") if not r["done"]]


def open_decisions(root: Path) -> list[dict]:
    return [r for r in rows(root, "DECISIONS.md") if not r["taken"] and not r["done"]]


def brief(root: Path) -> str:
    version = read(root / "VERSION").strip() or "no VERSION"
    commit = git(root, "rev-parse", "--short", "HEAD") or "no commits yet"
    cert = read(root / "crissp" / "testsuite" / "results" / "release.json")
    try:
        c = json.loads(cert) if cert else None
    except json.JSONDecodeError:
        c = None
    certificate = f"green full run on {str(c.get('commit', ''))[:8]}" if c else "none"
    all_items = items(root)
    by = {s: [i for i in all_items if i["status"] == s] for s in STATUSES}
    line = lambda xs: ", ".join(f'{i["id"]} {i["title"]}' for i in xs) or "none"  # noqa: E731
    return "\n".join([
        f"{root.name} {version} · commit {commit} · release certificate: {certificate}",
        f"Doing: {line(by['doing'])}",
        f"In review (waiting for the product owner): {line(by['review'])}",
        f"Next (first todo): {line(by['todo'][:3])}",
        "Open decisions: " + ("; ".join(f'{r["id"]} {r["cells"][0][:90]}' for r in open_decisions(root)) or "none"),
        f"Open findings: {len(open_findings(root))} (the backlog tool with open=findings lists them)",
        "Ask the backlog tool for any F-/D-/E- id instead of reading the backlog files.",
    ])


def backlog(root: Path, args: dict) -> str:
    if args.get("id"):
        wanted = args["id"].strip().upper()
        for i in items(root):
            if i["id"] == wanted:
                return f'{i["file"]}\n{i["block"]}'
        pbis = lambda prefix: [f'{i["id"]} · {i["title"]} [{i["status"]}] [{i["size"]}]'  # noqa: E731
                               for i in items(root) if i["id"].startswith(prefix + "-")]
        for ft in features(root):
            if ft["id"] == wanted:
                return "\n".join([ft["file"], ft["block"], "PBIs:", *(pbis(wanted) or ["none yet"])])
        for f in epic_files(root):
            m = EPIC.search(read(f))
            if m and m.group(1) == wanted:
                own = [f'{ft["id"]} · {ft["title"]} [{ft["status"]}]' for ft in features(root) if ft["id"].startswith(wanted + "-")]
                return "\n".join([str(f.relative_to(root)), until(read(f), m.start(), re.compile(r"^#{2,3} ", re.M)),
                                  "Features:", *(own or ["none yet"])])
        for r in rows(root, "FINDINGS.md") + rows(root, "DECISIONS.md"):
            if r["id"] == wanted:
                return f'{r["file"]}{" (taken)" if r["taken"] else ""}\n{r["id"]} | ' + " | ".join(r["cells"])
        raise LookupError(f"{wanted} is not in the backlog")
    if args.get("status"):
        lines = [f'{ft["id"]} · {ft["title"]} [{ft["status"]}] (feature)' for ft in features(root) if ft["status"] == args["status"]]
        lines += [f'{i["id"]} · {i["title"]} [{i["status"]}] [{i["size"]}]' for i in items(root) if i["status"] == args["status"]]
        return "\n".join(lines) or f'no items {args["status"]}'
    if args.get("open") == "findings":
        return "\n".join(f'{r["id"]} → {r["cells"][-1]} · {r["cells"][1][:110]}' for r in open_findings(root)) or "no open findings"
    if args.get("open") == "decisions":
        return "\n".join(f'{r["id"]} {r["cells"][0]} · recommendation: {r["cells"][-1]}' for r in open_decisions(root)) \
            or "no open decisions"
    raise ValueError("give an id, a status, or open=findings|decisions")


def write(path: Path, text: str) -> None:
    """All or nothing: a half-written backlog file is worse than none."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def cell(args: dict, key: str) -> str:
    value = " ".join(str(args.get(key) or "").split())
    if not value:
        raise ValueError(f"{key} is missing")
    if "|" in value:
        raise ValueError(f"{key} cannot hold a | (it would break the table)")
    return value


def next_id(prefix: str, ids: list[str]) -> str:
    numbers = [int(i.rsplit("-", 1)[1]) for i in ids]
    return f"{prefix}-{max(numbers, default=0) + 1:02d}"


def add_row(text: str, row: str, heading: str | None = None) -> str:
    """The row after the last line of the first table (after the heading, when one is given)."""
    lines = text.splitlines()
    start = next((n for n, line in enumerate(lines) if line.strip() == heading), None) if heading else 0
    if start is None:
        raise LookupError(f"no section {heading!r}")
    first = next((n for n in range(start, len(lines)) if lines[n].startswith("|")), None)
    if first is None:
        raise LookupError("no table to write into")
    last = first
    while last + 1 < len(lines) and lines[last + 1].startswith("|"):
        last += 1
    return "\n".join(lines[: last + 1] + [row] + lines[last + 1:]) + "\n"


def finding(root: Path, args: dict) -> str:
    seen, observation, goes_to = cell(args, "seen"), cell(args, "observation"), cell(args, "goes_to")
    path = backlog_dir(root) / "FINDINGS.md"
    if not path.is_file():
        raise LookupError(f"{path.relative_to(root)} is missing")
    new = next_id("F", [r["id"] for r in rows(root, "FINDINGS.md")])
    write(path, add_row(path.read_text(), f"| {new} | {seen} | {observation} | {goes_to} |"))
    return f"{new} written to {path.relative_to(root)}"


def decision(root: Path, args: dict) -> str:
    path = backlog_dir(root) / "DECISIONS.md"
    if not path.is_file():
        raise LookupError(f"{path.relative_to(root)} is missing")
    text = path.read_text()
    if args.get("id"):
        wanted = args["id"].strip().upper()
        taken = cell(args, "decision")
        date = str(args.get("date") or datetime.date.today().isoformat()).strip()
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
            raise ValueError(f"date {date!r} is not YYYY-MM-DD")
        row = next((r for r in rows(root, "DECISIONS.md") if r["id"] == wanted), None)
        if row is None:
            raise LookupError(f"{wanted} is not in the backlog")
        if row["taken"] or row["done"]:
            raise ValueError(f"{wanted} is already taken")
        lines = [line for line in text.splitlines() if not re.match(rf"^\|\s*{re.escape(wanted)}\s*\|", line)]
        text = "\n".join(lines) + "\n"
        if "## Taken" not in text:
            text = text.rstrip("\n") + "\n\n## Taken\n\n| # | Decision | Date |\n|---|---|---|\n"
        write(path, add_row(text, f"| ~~{wanted}~~ | {taken} | {date} |", "## Taken"))
        return f"{wanted} taken, in {path.relative_to(root)}"
    question, options, recommendation = cell(args, "question"), cell(args, "options"), cell(args, "recommendation")
    new = next_id("D", [r["id"] for r in rows(root, "DECISIONS.md")])
    heading = "## Open — need the product owner" if "## Open — need the product owner" in text else None
    write(path, add_row(text, f"| {new} | {question} | {options} | {recommendation} |", heading))
    return f"{new} written to {path.relative_to(root)}"


def field(label: str, value: str) -> str:
    return textwrap.fill(value, width=120, initial_indent=f"{label:<11}", subsequent_indent=" " * 11)


def slug(title: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", title.lower()).split()
    out = ""
    for w in words:
        if len(out) + len(w) + 1 > 40:
            break
        out = f"{out}-{w}" if out else w
    return out or "epic"


def epic(root: Path, args: dict) -> str:
    title, why = cell(args, "title"), cell(args, "why")
    if not backlog_dir(root).is_dir():
        raise LookupError(f"{backlog_dir(root).relative_to(root)} is missing")
    numbers = [int(m.group(1)) for f in epic_files(root) if (m := re.match(r"E(\d+)-", f.name))]
    new = f"E{max(numbers, default=0) + 1}"
    path = backlog_dir(root) / f"{new}-{slug(title)}.md"
    write(path, f"# {new} · {title}\n\n" + textwrap.fill(f"Why: {why}", width=120) + "\n")
    readme = backlog_dir(root) / "README.md"
    listed = [n for n, line in enumerate(read(readme).splitlines()) if line.startswith("| [E")]
    if listed:  # the README lists every epic: the new one goes under the last
        lines = readme.read_text().splitlines()
        lines.insert(listed[-1] + 1, f"| [{path.name}]({path.name}) | {title} |")
        write(readme, "\n".join(lines) + "\n")
    return f"{new} written to {path.relative_to(root)}" + (", listed in the README" if listed else "")


def open_epic(root: Path, epic_id: str) -> Path:
    files = sorted(backlog_dir(root).glob(f"{epic_id}-*.md"))
    if not files:
        raise LookupError(f"{epic_id} is not an open epic")
    return files[0]


def feature(root: Path, args: dict) -> str:
    epic_id = str(args.get("epic") or "").strip().upper()
    if not re.fullmatch(r"E\d+", epic_id):
        raise ValueError("give the epic (E<n>) the feature belongs to")
    path = open_epic(root, epic_id)
    title, why = cell(args, "title"), cell(args, "why")
    numbers = [int(ft["id"].rsplit("F", 1)[1]) for ft in features(root) if ft["id"].startswith(epic_id + "-F")]
    new = f"{epic_id}-F{max(numbers, default=0) + 1}"
    block = "\n".join([f"{f'## {new} · {title}':<88} [todo]", field("Why", why)])
    write(path, path.read_text().rstrip("\n") + "\n\n" + block + "\n")
    return f"{new} written to {path.relative_to(root)}"


def move(root: Path, wanted: str, status: str) -> str:
    if status == "done":
        raise ValueError("only the product owner accepts: done work moves to done/ when they approve")
    if status not in STATUSES:
        raise ValueError(f"status must be one of {', '.join(s for s in STATUSES if s != 'done')}")
    found = next((x for x in items(root) + features(root) if x["id"] == wanted), None)
    if found is None:
        raise LookupError(f"{wanted} is not in the backlog")
    if found["status"] == "done" or "/done/" in found["file"]:
        raise ValueError(f"{wanted} is done; it does not move back")
    path = root / found["file"]
    header = re.compile(rf"^(#{{2,3}} {re.escape(wanted)} · .+?\s+\[)(\w+)(\])", re.M)
    write(path, header.sub(lambda m: m.group(1) + status + m.group(3), path.read_text(), count=1))
    return f"{wanted} [{found['status']}] → [{status}], in {found['file']}"


def item(root: Path, args: dict) -> str:
    if args.get("id"):
        return move(root, args["id"].strip().upper(), args.get("status") or "")
    feature_id = str(args.get("feature") or "").strip().upper()
    if not re.fullmatch(r"E\d+-F\d+", feature_id):
        raise ValueError("a PBI belongs to a feature: give feature (E<n>-F<m>; create one with feature), "
                         "or an id and a status to move one")
    path = open_epic(root, feature_id.split("-")[0])
    text = path.read_text()
    heading = re.search(rf"^## {re.escape(feature_id)} · ", text, re.M)
    if heading is None:
        raise LookupError(f"{feature_id} is not a feature of {path.relative_to(root)}")
    size = str(args.get("size") or "").strip().upper()
    if size not in SIZES:
        raise ValueError("size must be S, M or L (an XL item is split before it starts)")
    title = cell(args, "title")
    body = [field("Why", cell(args, "why")), field("What", cell(args, "what")),
            field("Done when", cell(args, "done_when")), field("Tests", cell(args, "tests")),
            field("Depends", " ".join(str(args.get("depends") or "—").split()))]
    new = next_id(feature_id, [i["id"] for i in items(root) if i["id"].startswith(feature_id + "-")])
    block = "\n".join([f"{f'### {new} · {title}':<88} [todo] [{size}]", *body])
    nxt = re.compile(r"^#{1,2} ", re.M).search(text, heading.end())  # the feature ends where the next feature starts
    at = nxt.start() if nxt else len(text)
    write(path, text[:at].rstrip("\n") + "\n\n" + block + "\n" + ("\n" + text[at:] if nxt else ""))
    return f"{new} written to {path.relative_to(root)}"


def results(root: Path) -> Path:
    return root / "crissp" / "testsuite" / "results"


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def script(root: Path, name: str) -> Path:
    """The project's own crissp/<name> (a repository that carries the framework), else the engine's (an installed
    crissp: the project holds only its data)."""
    for path in (root / "crissp" / name, ENGINE / name):
        if path.is_file():
            return path
    raise LookupError(f"crissp/{name} is missing")


def background(root: Path, key: str, argv: list[str]) -> int:
    """Start argv detached from this server (it outlives the session), its output and its exit code in the log."""
    out = results(root) / "mcp"
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{key}.log", "w") as log:
        proc = subprocess.Popen(["/bin/sh", "-c", '"$0" "$@"; echo "[crissp] exit $?"', *argv], cwd=root, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
    runs = json.loads(read(out / "runs.json") or "{}")
    runs[key] = {"pid": proc.pid, "started": datetime.datetime.now().strftime("%H:%M:%S"), "log": f"crissp/testsuite/results/mcp/{key}.log"}
    write(out / "runs.json", json.dumps(runs, indent=2) + "\n")
    return proc.pid


def held(root: Path) -> str:
    """Who holds the run lock (one run at a time), or nothing."""
    lock = results(root) / ".run.lock"
    pid = read(lock / "pid").strip()
    if pid.isdigit() and alive(int(pid)):
        return f"{read(lock / 'what').strip() or 'a run'} (pid {pid}, since {read(lock / 'since').strip() or '?'})"
    return ""


def run(root: Path, args: dict) -> str:
    what = args.get("what") or ""
    if what not in RUNS:
        raise ValueError(f"what must be one of {', '.join(RUNS)} (a deploy stays in the product owner's terminal)")
    name, argv, detached = RUNS[what]
    path = script(root, name)
    if not detached:
        try:
            done = subprocess.run([str(path), *argv], cwd=root, capture_output=True, text=True, timeout=PLAN_TIMEOUT,
                                  stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            raise ValueError(f"{what} took longer than {PLAN_TIMEOUT}s; run crissp/{name} {' '.join(argv)} in a terminal") from None
        return f"crissp/{name} {' '.join(argv)} (exit {done.returncode})\n" + (done.stdout + done.stderr).strip()
    busy = held(root)
    if busy:
        raise ValueError(f"a run is in progress: {busy}. One run at a time; status follows it.")
    pid = background(root, what, [str(path), *argv])
    return f"{what} started (pid {pid}): crissp/{name}. Follow it with status; log: crissp/testsuite/results/mcp/{what}.log"


def status(root: Path) -> str:
    runs = json.loads(read(results(root) / "mcp" / "runs.json") or "{}")
    lines = [f"Lock: {held(root) or 'free'}"]
    for key, r in runs.items():
        log = read(root / r["log"])
        ended = EXIT.findall(log)
        state = (f"finished, exit {ended[-1]}" + (" (green)" if ended[-1] == "0" else "")) if ended else \
            "running" if alive(r["pid"]) else "stopped without an exit code"
        tail = [line for line in EXIT.sub("", log).rstrip().splitlines()][-12:]
        lines += ["", f"{key} · started {r['started']} · {state} · {r['log']}", *("  " + t for t in tail)]
    return "\n".join(lines) if runs else lines[0] + "\nNothing started with run yet."


def served(url: str) -> bool:
    """The address answers with the dashboard itself, not with an error page or another program."""
    try:
        with urllib.request.urlopen(url, timeout=2) as answer:
            return 'id="sessions"' in answer.read(65536).decode(errors="replace")
    except OSError:
        return False


def dashboard(root: Path, args: dict | None = None) -> str:
    view = (args or {}).get("view") or "tests"
    if view not in VIEWS:
        raise ValueError(f"view must be one of {', '.join(VIEWS)}")
    path = script(root, "test.sh")
    background(root, "dashboard", [str(path), VIEWS[view]])
    log = results(root) / "mcp" / "dashboard.log"
    deadline = time.monotonic() + DASHBOARD_WAIT
    while time.monotonic() < deadline:
        text = read(log)
        found = re.search(r"Dashboard: (\S+)", text)
        # what the script says is checked: it says so before the server is up (the Tests page answers for both views)
        if found and served(re.sub(r"/ux/$", "/dashboard/", found.group(1))):
            return f"Dashboard: {found.group(1)} (data rebuilt from the last runs)"
        if EXIT.search(text):
            raise ValueError("the dashboard did not start:\n" + EXIT.sub("", text).strip()[-1500:])
        time.sleep(0.2)
    raise ValueError(f"the dashboard said nothing in {DASHBOARD_WAIT}s; see crissp/testsuite/results/mcp/dashboard.log")


def call(root: Path, name: str, args: dict) -> dict:
    """A tool's answer as MCP content; a wrong question is an answer that says so (isError), never a crash."""
    try:
        if name == "brief":
            text = brief(root)
        elif name == "backlog":
            text = backlog(root, args)
        elif name == "finding":
            text = finding(root, args)
        elif name == "decision":
            text = decision(root, args)
        elif name == "epic":
            text = epic(root, args)
        elif name == "feature":
            text = feature(root, args)
        elif name == "item":
            text = item(root, args)
        elif name == "run":
            text = run(root, args)
        elif name == "status":
            text = status(root)
        elif name == "dashboard":
            text = dashboard(root, args)
        else:
            raise ValueError(f"unknown tool {name}")
    except (LookupError, ValueError) as err:
        return {"content": [{"type": "text", "text": str(err)}], "isError": True}
    return {"content": [{"type": "text", "text": text}]}


def handle(root: Path, msg: dict) -> dict | None:
    """One JSON-RPC message in, its answer out (None for a notification)."""
    method, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None
    if method == "initialize":
        result = {"protocolVersion": (msg.get("params") or {}).get("protocolVersion", PROTOCOL),
                  "capabilities": {"tools": {}}, "serverInfo": {"name": "crissp", "version": "0.1.0"},
                  "instructions": "The way of working of this repository. Call brief at the start; ask backlog for "
                                  "F-/D-/E- ids instead of reading crissp/backlog files; write findings, decisions, "
                                  "epics, features and PBIs with finding, decision, epic, feature and item instead of "
                                  "editing them; start the checks with run, follow them with status, show the "
                                  "dashboard with dashboard. Deploying stays in the product owner's terminal."}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        params = msg.get("params") or {}
        result = call(root, params.get("name", ""), params.get("arguments") or {})
    elif method == "ping":
        result = {}
    else:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"no method {method}"}}
    return {"jsonrpc": "2.0", "id": mid, "result": result}


def serve(root: Path, stdin=sys.stdin, stdout=sys.stdout) -> int:
    """Read one JSON message per line, answer each request on its own line, until stdin closes."""
    for line in stdin:
        if not line.strip():
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            answer = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}
        else:
            answer = handle(root, msg)
        if answer is not None:
            stdout.write(json.dumps(answer) + "\n")
            stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(serve(ROOT))
