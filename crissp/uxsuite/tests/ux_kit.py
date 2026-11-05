"""What the UX suite's tests share: the suite's modules on the path, a small example product in a temporary folder, and
a team that runs nothing (claude and the browser are stand-ins: no model, no browser, no network)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

UXSUITE = Path(__file__).resolve().parents[1]
REPO = UXSUITE.parents[1]
for p in (UXSUITE, Path(__file__).resolve().parent):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import ux_config  # noqa: E402
import ux_team  # noqa: E402

PERSONAS = [
    {"key": "tech", "name": "Sam", "role": "software engineer", "device": "desktop", "brief": "Notices states."},
    {"key": "phone", "name": "Mo", "role": "student on a phone", "device": "mobile", "brief": "Uses a thumb."},
    {"key": "ux", "name": "Ada", "role": "UX expert", "device": "both", "moderator": True, "brief": "Moderates."},
]
WALK = {"title": "First visit", "steps": [{"do": "goto", "path": "/"}, {"do": "click", "text": "Start"},
                                          {"do": "fill", "selector": "#name", "value": "Example"},
                                          {"do": "press", "key": "Enter"}, {"do": "wait", "ms": 10},
                                          {"do": "shot", "title": "The first screen"}]}


class FakeProc:
    """A run that is busy until the test ends it."""

    def __init__(self, cmd, **kw):
        self.cmd, self.kw, self.returncode = cmd, kw, None

    def poll(self):
        return self.returncode

    def end(self, code: int = 0) -> None:
        self.returncode = code


def make_product(root: Path, team: dict | None = None, walks: dict | None = None) -> ux_config.Suite:
    """An example product: its UX suite's config, a backlog in the framework's own format and the crissp tool."""
    here = root / "crissp" / "uxsuite"
    (here / "walks").mkdir(parents=True)
    conf = {"product": "Example Shop", "about": "A shop.", "url": "http://127.0.0.1:5173/", "personas": PERSONAS}
    (here / "team.json").write_text(json.dumps(conf if team is None else team))
    for wid, w in (walks if walks is not None else {"first-visit": WALK}).items():
        (here / "walks" / f"{wid}.json").write_text(json.dumps(w))
    shutil.copytree(REPO / "crissp" / "template" / "crissp" / "backlog", root / "crissp" / "backlog")
    (root / "crissp" / "tool").mkdir(parents=True)
    shutil.copy(REPO / "crissp" / "tool" / "server.py", root / "crissp" / "tool" / "server.py")
    return ux_config.Suite(root)


def add_shots(suite: ux_config.Suite, walk: str = "first-visit") -> None:
    """Screenshots as the browser would leave them (tiny files: no real picture, no person in it)."""
    d = suite.results / "shots" / walk
    (d / "laptop").mkdir(parents=True)
    (d / "laptop" / "01-the-first-screen.png").write_bytes(b"\x89PNG stand-in")
    (d / "shots.json").write_text(json.dumps([{"device": "laptop", "n": 1, "title": "The first screen",
                                               "file": "laptop/01-the-first-screen.png"},
                                              {"device": "phone", "n": 1, "title": "The first screen",
                                               "file": "phone/01-the-first-screen.png", "error": "Stuck at step 2"}]))


def finish(suite: ux_config.Suite, kind: str, walk: str, n: int, result: dict, mockup: bool = True) -> Path:
    """What a finished run leaves behind: its result and status done (a proposal also its mockup)."""
    vdir = ux_team.folder(suite, kind, walk) / f"{ux_team.PREFIX[kind]}{n}"
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / ux_team.RESULT[kind]).write_text(json.dumps(result))
    (vdir / "status.json").write_text(json.dumps({"phase": "done", "note": "ready"}))
    if kind == "proposal" and mockup:
        (vdir / "mockup.html").write_text("<!doctype html><p>after</p>")
    return vdir


ROUND = {"summary": "Clear enough.", "scores": {"tech": 7, "phone": 5, "ux": 6}, "consensus": ["The start is clear."],
         "disputes": [{"topic": "Colour", "positions": [{"persona": "tech", "position": "fine"}]}],
         "advice": [{"title": "Bigger buttons", "detail": "Thumb reach.", "priority": "must", "effort": "S",
                     "personas": ["phone"]}]}
PROPOSAL = {"title": "Calmer start", "summary": "One action first.", "changes": [
    {"what": "One primary button", "why": "focus", "priority": "must", "who_asked": ["phone"]}]}


@pytest.fixture
def product(tmp_path, monkeypatch):
    """An example product whose team runs stand-ins; the procs it started are in ux_team.popen.started."""
    started: list[FakeProc] = []

    def popen(cmd, **kw):
        p = FakeProc(cmd, **kw)
        started.append(p)
        return p
    popen.started = started
    monkeypatch.setattr(ux_team, "popen", popen)
    monkeypatch.setattr(ux_team, "_running", {})
    monkeypatch.delenv("UXSUITE_PARALLEL", raising=False)
    monkeypatch.delenv("CRISSP_UX_MODEL", raising=False)
    return make_product(tmp_path / "repo")
