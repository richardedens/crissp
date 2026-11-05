"""An approved design becomes a PBI in the backlog, written by the crissp tool itself (crissp/tool/server.py: one writer,
the backlog's own format, the next free number), never by hand.

The PBI goes into one feature per walk ("UX · <walk title>") of the UX epic: the epic team.json names
(backlog.epic), or the open epic with the configured title (backlog.epic_title, default "UX: approved designs"), made
once when there is none. The PBI's Depends line carries the marker  UX proposal `<walk>#v<n>`: that is how the Tests
board links a UX-born item back to its design, and how a design never gets a second PBI (the suite's results are not in
git and can be lost; the backlog is). Its status starts at todo and is never set to done from here: only the product
owner accepts.
"""

from __future__ import annotations

import datetime
import importlib.util
import re
from pathlib import Path

from ux_config import Suite

MARKER = re.compile(r"UX\s+proposal\s+`([^`]+)`")


ENGINE_TOOL = Path(__file__).resolve().parent.parent / "tool" / "server.py"  # the framework's own crissp tool


def tool(suite: Suite):
    """The crissp tool, loaded from its file (it is a script, not a package): the project's own crissp/tool (a
    repository that carries the framework), else the engine's (an installed crissp: the project holds only its data)."""
    path = next((p for p in (suite.root / "crissp" / "tool" / "server.py", ENGINE_TOOL) if p.is_file()), None)
    if path is None:
        raise LookupError("crissp/tool/server.py is missing: the backlog is written by the crissp tool only")
    spec = importlib.util.spec_from_file_location("crissp_tool_for_the_uxsuite", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pbis(suite: Suite, crissp=None) -> dict[str, str]:
    """Every PBI that came from an approved design: its proposal key → its id."""
    crissp = crissp or tool(suite)
    out = {}
    for i in crissp.items(suite.root):
        m = MARKER.search(i["block"])
        if m:
            out.setdefault(m.group(1), i["id"])
    return out


def _flat(text: str) -> str:
    """One line the backlog's tables and fields take: no | (it would break a table), no line breaks."""
    return " ".join(str(text or "").replace("|", "/").split())


def _epic(suite: Suite, conf: dict, crissp) -> str:
    wanted = conf["backlog"]["epic"]
    if wanted:
        crissp.open_epic(suite.root, wanted)  # LookupError when it is not an open epic
        return wanted
    title = conf["backlog"]["epic_title"]
    for f in sorted(crissp.backlog_dir(suite.root).glob("E*.md")):  # open epics only (done/ is a folder below)
        m = crissp.EPIC.search(crissp.read(f))
        if m and m.group(2).strip() == title:
            return m.group(1)
    said = crissp.epic(suite.root, {"title": title, "why": "The designs the product owner approved in the UX suite, "
                                                           "one feature per walk, so each becomes work like any other."})
    return said.split()[0]


def _feature(suite: Suite, epic: str, walk: dict, crissp) -> str:
    title = f"UX · {_flat(walk['title'])}"
    for ft in crissp.features(suite.root):
        if ft["id"].startswith(epic + "-F") and ft["title"] == title and ft["status"] != "done":
            return ft["id"]
    said = crissp.feature(suite.root, {"epic": epic, "title": title,
                                       "why": f"What the UX team found and designed for the walk {walk['id']}, approved."})
    return said.split()[0]


def file_pbi(suite: Suite, conf: dict, walk_id: str, version: int, proposal: dict, crissp=None, remark: str = "") -> str:
    """The PBI of an approved design: the existing one when it was written before, otherwise a new one. The product
    owner's remark on the approval, when given, comes first in its What: the builder reads it before the changes."""
    crissp = crissp or tool(suite)
    key = f"{walk_id}#v{version}"
    known = pbis(suite, crissp)
    if key in known:
        return known[key]
    walk = conf["walks"][walk_id]
    feature = _feature(suite, _epic(suite, conf, crissp), walk, crissp)
    changes = [c for c in proposal.get("changes", []) if isinstance(c, dict)]
    what = "; ".join(f"{i}. [{c.get('priority', 'should')}] {c.get('what', '')}" for i, c in enumerate(changes, 1))
    folder = f"crissp/uxsuite/results/proposals/{walk_id}/v{version}"
    said = crissp.item(suite.root, {
        "feature": feature, "size": "S" if len(changes) <= 4 else "M" if len(changes) <= 10 else "L",
        "title": _flat(proposal.get("title") or f"{walk['title']}: approved design v{version}"),
        "why": _flat(proposal.get("summary") or "The UX team's design for this walk, approved by the product owner."),
        "what": _flat((f"The product owner's remark: {remark.strip()} Changes: " if remark.strip() else "")
                      + (what or "The changes in the approved mockup.")),
        "done_when": _flat(f"The built screens match the approved mockup ({folder}/mockup.html) in light and dark, follow "
                           "crissp/uxsuite/PRINCIPLES.md, and the product owner accepts them."),
        "tests": _flat(f"A test per must-change that fails without it; the walk shot again (crissp/ux.sh --shoot {walk_id}) "
                       "and a new round."),
        "depends": f"UX proposal `{key}` (approved {datetime.date.today().isoformat()})"})
    return said.split()[0]
