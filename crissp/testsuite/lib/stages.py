"""Where the work is in the six stages of the agentic SDLC (F-130): Discover, Plan, Build, Verify, Review, Release.

Read from what the repository says, never kept apart: the backlog (through the crissp tool, crissp/tool/server.py: one
parser), the release certificate (results/release.json), git, VERSION and CHANGELOG.md, and the UX suite's state
(crissp/uxsuite/api.py state(), when the project has a UX suite). Per stage:

- status   setup (not in place yet) · work (there is work for Claude and its agents) · yours (it waits for the product
           owner) · clear (nothing in it now)
- summary  one sentence; items: what is in it, one line each; actions: what the Stages page can start at once (only the
           UX team's map-less rounds, which the UX page starts as well)
- ask      the sentence that asks Claude or Mistral Vibe to help with it ("crissp: help me with Plan"); claude and vibe
           the terminal commands that start a session with it; prompt what the session then does, the crissp tool
           `stage` answers it, so every session of either agent gets the same instructions

current is the stage the work is in now, following the flow: a PBI in doing (Build), commits not verified yet (Verify),
what waits for the product owner's review (Review), a green version ready to tag (Release), a PBI to build next (Build),
findings and decisions to plan (Plan), else Discover. Nothing here starts a check, tags, pushes or publishes.

    the Stages page asks /dashboard/stages.json (lib/serve.py) · the crissp tool `stage` answers text(state(root))
"""

from __future__ import annotations

import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent
ENGINE = LIB.parents[1]  # crissp/ of the framework: its tool and its UX suite, beside this file
UX_API = ENGINE / "uxsuite" / "api.py"
sys.path.insert(0, str(LIB))
import project  # noqa: E402

PLACED = re.compile(r"^\s*(fixed|removed|closed|done)\b|\bE\d+(-F\d+)?(-\d+)?\b", re.IGNORECASE)  # a finding with its place
STATUSES = ("setup", "work", "yours", "clear")
STAGES = (("discover", "Discover"), ("plan", "Plan"), ("build", "Build"), ("verify", "Verify"), ("review", "Review"),
          ("release", "Release"))
NEVER = "Never push, tag, publish or deploy, and never move anything to done: those stay with the product owner."
PROMPTS = {
    "discover": (
        "C.R.I.S.S.P. stage Discover: find out what the product's users need. Call the crissp tool stage (stage: "
        "discover) for where it stands. When the UX suite is not set up, or its team.json still holds CRISSP: "
        "placeholders, set it up with the product owner: ask what the product is, who uses it, its language and where "
        "it runs locally, then fill in crissp/uxsuite/team.json and a first walk in crissp/uxsuite/walks/ (crissp/uxsuite/README.md says how) and show the diff. When it is, say what the "
        "team found, which needs and designs wait for a verdict on the UX page, and offer the next step: map the "
        "product (crissp ux --map), a round on a walk or a discovery round (crissp ux). Those cost tokens: start one "
        "only after the product owner's yes. Write what you notice as findings with the finding tool. " + NEVER),
    "plan": (
        "C.R.I.S.S.P. stage Plan: turn what was found into work. Call the crissp tool stage (stage: plan) and "
        "backlog (open: findings). Group the open findings and approved needs and designs into features and PBIs "
        "with the feature and item tools: each PBI says why, what, when it is done and which test proves it. Put "
        "every real choice to the product owner as a decision (options and a recommendation), never decide it "
        "yourself. Show the plan before writing more than a few items. " + NEVER),
    "build": (
        "C.R.I.S.S.P. stage Build: build the next PBI test-first. Call the crissp tool stage (stage: build): take the "
        "PBI in doing, else the first todo, and move it to doing with item. Write a test that fails without the "
        "change, see it red, build until green; new code fully covered. One commit per PBI with what was missing, how "
        "it was done and the proof; record it in crissp/testsuite/changes.json and the release notes. Hand separate "
        "parts to agents in their own worktrees. When it is built, move it to review. " + NEVER),
    "verify": (
        "C.R.I.S.S.P. stage Verify: prove what was built. Call the crissp tool stage (stage: verify). Commit first: "
        "the checks test what is committed. Start run (what: check), wait with status (wait: true), and report only "
        "what failed; fix each failure test-first and run it again. The full run (run what: check-all) only when the "
        "product owner asks. Never report red as green. " + NEVER),
    "review": (
        "C.R.I.S.S.P. stage Review: put what is built in front of the product owner. Call the crissp tool stage "
        "(stage: review) and list what waits for them: the PBIs in review with how each is proven (the test, the "
        "commit), the designs and needs waiting for a verdict on the UX page, the open decisions. Go through them "
        "one at a time with your advice and change what they send back. Only the product owner accepts: never move "
        "anything to done. Never push, tag, publish or deploy."),
    "release": (
        "C.R.I.S.S.P. stage Release: get the version ready for the product owner to release. Call the crissp tool "
        "stage (stage: release). Check that every change a user would notice is in the top entry of CHANGELOG.md for "
        "the version in VERSION, draft or tighten those release notes, and say whether the release certificate is "
        "green on this commit (run what: check-plan; a deploy plan with run what: deploy-plan). Give the product "
        "owner the commands (git tag v<VERSION>, git push origin v<VERSION>), but never tag, push or publish "
        "yourself, and never deploy."),
}


def tool(root: Path):
    """The crissp tool, loaded from its file: the project's own crissp/tool (a repository that carries the framework),
    else the engine's (an installed crissp)."""
    path = next(p for p in (root / "crissp" / "tool" / "server.py", ENGINE / "tool" / "server.py") if p.is_file())
    spec = importlib.util.spec_from_file_location("crissp_tool_for_the_stages", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ux_state(root: Path) -> dict | None:
    """The UX suite's state (what its page shows), or None when the project has none set up or the engine has no UX
    suite. A broken configuration is {"error": …}, as the UX page says it."""
    if not (root / "crissp" / "uxsuite" / "team.json").is_file() or not UX_API.is_file():
        return None
    spec = importlib.util.spec_from_file_location("crissp_uxsuite_for_the_stages", UX_API)
    api = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(api)
    found = api.state(api.ux_config.Suite(root))
    if "error" not in found:  # what crissp init left for the product owner to fill in ("CRISSP: …")
        team = json.loads((root / "crissp" / "uxsuite" / "team.json").read_text())
        found["placeholders"] = [k for k, v in team.items()
                                 if not k.startswith("_") and isinstance(v, str) and v.startswith("CRISSP:")]
    return found


def _git(root: Path, *args: str) -> str:
    done = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    return done.stdout.strip() if done.returncode == 0 else ""


def _plural(n: int, word: str) -> str:
    return f"{n} {word}{'' if n == 1 else 's'}"


def stage(key: str, status: str, summary: str, items: list[str] | None = None, actions: list[dict] | None = None) -> dict:
    name = dict(STAGES)[key]
    ask = f"crissp: help me with {name}"
    return {"key": key, "name": name, "status": status, "summary": summary, "items": items or [],
            "actions": actions or [], "ask": ask, "claude": f'claude "{ask}"', "vibe": f'vibe "{ask}"',
            "prompt": PROMPTS[key]}


def _designs(ux: dict | None) -> list[dict]:
    return [d for w in (ux or {}).get("walks") or [] for d in w.get("proposals") or []]


def _title(d: dict) -> str:
    return f"Design {d.get('key')} “{(d.get('result') or {}).get('title', '')}”"


def discover(ux: dict | None) -> dict:
    if ux is None:
        return stage("discover", "setup", "No UX suite yet: crissp/uxsuite/team.json (who the team is, where the product "
                      "runs) and a walk in crissp/uxsuite/walks/ set it up.")
    if ux.get("error"):
        return stage("discover", "setup", f"The UX suite's configuration is wrong: {ux['error']}")
    if ux.get("placeholders"):
        return stage("discover", "setup", "The UX suite is not filled in yet: team.json still says what belongs in "
                     + ", ".join(ux["placeholders"]) + ".")
    items, actions, status = [], [], "clear"
    walks = ux.get("walks") or []
    if "map" in ux:  # the map and the discovery round, once the UX suite has them
        m = ux["map"]
        if m is None:
            items.append("The product is not mapped yet: crissp ux --map")
            status = "work"
        else:
            screens = m.get("screens") or []
            unwalked = sum("no walk looks at it" in (s.get("gaps") or []) for s in screens)
            items.append(f"{_plural(len(screens), 'screen')} mapped: {unwalked} no walk looks at, {m.get('gaps', 0)} no link reaches")
            actions.append({"label": "Start a discovery round", "kind": "discovery", "walk": "product"})
    for w in walks:
        if not w.get("rounds"):
            items.append(f"Walk {w['id']} “{w.get('title', '')}”: no round yet")
            actions.append({"label": f"Start a round on “{w.get('title', w['id'])}”", "kind": "round", "walk": w["id"]})
            status = "work"
    running = (ux.get("team") or {}).get("running") or []
    if running:
        items.append("The UX team works on " + ", ".join(running))
        status = "work"
    needs = sum(n.get("verdict") is None for d in ux.get("discovery") or [] for n in d.get("needs") or [])
    if needs:
        items.append(f"{_plural(needs, 'need')} from the discovery round {'waits' if needs == 1 else 'wait'} for your verdict on the UX page")
        status = "yours"
    summary = {"clear": f"The UX team has walked all {_plural(len(walks), 'walk')}; a new round finds what changed.",
               "work": "There is something the UX team has not looked at yet.",
               "yours": "What the UX team found waits for your verdict."}[status]
    return stage("discover", status, summary, items, actions)


def _short(text: str, width: int = 110) -> str:
    return text if len(text) <= width else text[:width].rstrip() + "…"


def plan(crissp, root: Path, ux: dict | None) -> dict:
    findings = [f"{r['id']} {_short(r['cells'][1] if len(r['cells']) > 1 else '')} → {r['cells'][-1]}".replace("  ", " ")
                for r in crissp.open_findings(root) if not PLACED.search(r["cells"][-1])]
    decisions = [f"{r['id']} {r['cells'][0]} (your decision)" for r in crissp.open_decisions(root)]
    approved = [f"{_title(d)} is approved and has no PBI yet" for d in _designs(ux)
                if (d.get("verdict") or {}).get("verdict") == "approve" and not d.get("pbi")]
    items = findings + decisions + approved
    status = "yours" if decisions else "work" if items else "clear"
    summary = {"yours": f"{_plural(len(decisions), 'open decision')} {'waits' if len(decisions) == 1 else 'wait'} for you",
               "work": "Findings and approved designs to turn into PBIs",
               "clear": "Nothing to plan: every finding has its place"}[status]
    if status == "yours" and findings + approved:
        summary += f"; {_plural(len(findings + approved), 'thing')} to turn into PBIs"
    return stage("plan", status, summary + ".", items)


def build(items: list[dict]) -> dict:
    doing = [i for i in items if i["status"] == "doing"]
    todo = [i for i in items if i["status"] == "todo"]
    lines = [f"{i['id']} {i['title']} (doing)" for i in doing] + [f"Next: {i['id']} {i['title']}" for i in todo[:3]]
    if doing:
        return stage("build", "work", f"{_plural(len(doing), 'PBI')} being built, {len(todo)} to do.", lines)
    if todo:
        return stage("build", "work", f"Nothing being built; {len(todo)} to do, the first is next.", lines)
    return stage("build", "clear", "Nothing to build: no PBI in doing or todo.")


def _cert(root: Path) -> dict | None:
    try:
        return json.loads((root / "crissp" / "testsuite" / "results" / "release.json").read_text())
    except (OSError, json.JSONDecodeError):
        return None


def verify(root: Path, head: str) -> tuple[dict, bool]:
    """The stage, and whether HEAD is green."""
    if not head:
        return stage("verify", "setup", "No commits yet: the checks test what is committed."), False
    items = []
    if _git(root, "status", "--porcelain", "--untracked-files=no"):
        items.append("Uncommitted changes: commit first, the checks test what is committed.")
    cert = _cert(root)
    if not cert:
        return stage("verify", "work", "No green run yet: the full run (crissp/check-all.sh) is yours to start.", items), False
    red = [k for k, v in (cert.get("steps") or {}).items() if v != "passed"]
    if red:
        items.append("Red in the last full run: " + ", ".join(red) + ".")
    commit = str(cert.get("commit", ""))
    if commit == head and not red:
        return stage("verify", "work" if items else "clear", f"Green on {head[:7]}, this commit.", items), not items
    since = _git(root, "rev-list", "--count", f"{commit}..HEAD")
    summary = (f"{_plural(int(since), 'commit')} since the last green state: crissp/check.sh tests what changed."
               if since.isdigit() and not red else "Not green on this commit: crissp/check.sh tests what changed.")
    return stage("verify", "work", summary, items), False


def review(items: list[dict], ux: dict | None) -> dict:
    lines = [f"{i['id']} {i['title']} (in review)" for i in items if i["status"] == "review"]
    lines += [f"{_title(d)} waits for your verdict on the UX page" for d in _designs(ux)
              if (d.get("status") or {}).get("phase") == "done" and d.get("result") and not d.get("verdict")]
    if lines:
        return stage("review", "yours", f"{_plural(len(lines), 'thing')} {'waits' if len(lines) == 1 else 'wait'} for your review.", lines)
    return stage("review", "clear", "Nothing waits for your review.")


def release(root: Path, head: str, green: bool) -> dict:
    version = (root / "VERSION").read_text().strip() if (root / "VERSION").is_file() else ""
    if not head or not version:
        return stage("release", "setup", "No commits or no VERSION yet: a release is a tag v<VERSION> you push.")
    tag = f"v{version}"
    if _git(root, "tag", "--list", tag):
        since = int(_git(root, "rev-list", "--count", f"{tag}..HEAD") or 0)
        if since:
            return stage("release", "work", f"{version} is tagged; {_plural(since, 'commit')} since: the next version "
                          "needs its number in VERSION and its notes.")
        return stage("release", "clear", f"{version} is released ({tag}); nothing new since.")
    notes = (root / "CHANGELOG.md").read_text() if (root / "CHANGELOG.md").is_file() else ""
    top = re.search(r"^## (\S+)", notes, re.MULTILINE)
    items = [] if top and top.group(1) == version else [f"CHANGELOG.md has no entry for {version} yet"]
    if not green:
        items.append("Not green on this commit yet (Verify)")
    if items:
        return stage("release", "work", f"{version} is not ready to release yet.", items)
    return stage("release", "yours", f"{version} is green and has its release notes: yours to tag (git tag {tag}, "
                  "then push it).")


def state(root: Path, crissp=None, ux: dict | str | None = "read") -> dict:
    """The six stages of the project at root, and where the work is now."""
    crissp = crissp or tool(root)
    ux = ux_state(root) if ux == "read" else ux
    items = crissp.items(root)
    head = _git(root, "rev-parse", "HEAD")
    checked, green = verify(root, head)
    found = {"discover": discover(ux), "plan": plan(crissp, root, ux), "build": build(items), "verify": checked,
             "review": review(items, ux), "release": release(root, head, green)}
    doing = [i["id"] for i in items if i["status"] == "doing"]
    if doing:
        current, why = "build", f"{', '.join(doing)} is being built."
    elif found["verify"]["status"] == "work":
        current, why = "verify", found["verify"]["summary"]
    elif found["review"]["status"] == "yours":
        current, why = "review", found["review"]["summary"]
    elif found["release"]["status"] == "yours":
        current, why = "release", found["release"]["summary"]
    elif found["build"]["status"] == "work":
        current, why = "build", found["build"]["summary"]
    elif found["plan"]["status"] != "clear":
        current, why = "plan", found["plan"]["summary"]
    else:
        current, why = "discover", found["discover"]["summary"]
    try:
        conf = project.load(root)
    except project.ConfigError:
        conf = {"product": root.name, "monogram": root.name[:1].upper()}
    return {"product": conf["product"], "monogram": conf["monogram"], "current": current, "why": why, "stages": [found[k] for k, _ in STAGES]}


def text(state: dict, key: str | None = None) -> str:
    """For the crissp tool `stage`: where the work is and every stage in a few lines, or one stage with its prompt."""
    if key is not None:
        one = next((s for s in state["stages"] if s["key"] == key), None)
        if one is None:
            raise ValueError("stage is one of " + ", ".join(k for k, _ in STAGES))
        return "\n".join([f"{one['name']} · {one['status']}: {one['summary']}", *(f"- {i}" for i in one["items"]),
                          "", one["prompt"]])
    name = dict(STAGES)[state["current"]]
    lines = [f"The work is in {name}: {state['why']}", ""]
    for s in state["stages"]:
        lines.append(f"{'→' if s['key'] == state['current'] else ' '} {s['name']} · {s['status']}: {s['summary']}")
        lines += [f"  - {i}" for i in s["items"][:5]]
    lines += ["", "To help with a stage: call stage with stage: <" + "|".join(k for k, _ in STAGES) + ">, then do what it "
              "says. The product owner can ask for one with: crissp: help me with <stage>."]
    return "\n".join(lines)
