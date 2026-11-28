"""F-130: what the Stages page (dashboard/stages.js) shows, rendered by node with a stand-in for the browser that
answers stages.json with the data given: the stage the work is in, the six stages in order with whose move it is, and
per stage the commands that ask Claude Code or Mistral Vibe to help with it."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "dashboard" / "stages.js"
sys.path.insert(0, str(PAGE.parents[1] / "lib"))
import stages

STAND_IN = r"""
const els = {};
const el = sel => els[sel] ??= { innerHTML: "", textContent: "" };
global.document = { hidden: false, querySelector: el, querySelectorAll: () => [], addEventListener() {} };
global.window = {};
global.setInterval = () => 0;
global.fetch = async () => ({ ok: %s, text: async () => %s });
require(%s);
setTimeout(() => console.log(JSON.stringify({view: els["#view"].innerHTML, stamp: (els["#stamp"] || {}).textContent})), 50);
"""


def render(data, ok: bool = True) -> dict:
    if not shutil.which("node"):
        pytest.skip("no node on this machine")
    done = subprocess.run(
        ["node", "-e", STAND_IN % ("true" if ok else "false", json.dumps(json.dumps(data)), json.dumps(str(PAGE)))],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def data() -> dict:
    found = [
        stages.stage(
            "discover",
            "work",
            "Not looked at yet.",
            ["Walk home: no round yet"],
            [{"label": "Start a round on “Home”", "kind": "round", "walk": "home"}],
        ),
        stages.stage("plan", "yours", "1 open decision waits for you.", [f"F-{n} <b>x</b>" for n in range(8)]),
        *(stages.stage(k, "clear", "Nothing.") for k in ("build", "verify", "review", "release")),
    ]
    return {
        "product": "Shop",
        "monogram": "S",
        "current": "plan",
        "why": "1 open decision waits for you.",
        "stages": found,
    }


def test_the_page_says_where_the_work_is_and_every_stage_with_whose_move_it_is():
    out = render(data())
    view = out["view"]
    assert out["stamp"] == "The work is in Plan · live"
    assert '<div class="big">Plan</div>' in view
    names = ["Discover", "Plan", "Build", "Verify", "Review", "Release"]
    assert [view.index(f"<h3>{n}</h3>") for n in names] == sorted(view.index(f"<h3>{n}</h3>") for n in names)
    assert view.count('class="card stage on"') == 1 and 'id="plan"' in view.split('class="card stage on"')[1][:20]
    assert (
        '<span class="badge yours">waits for you</span>' in view and '<span class="badge passed">clear</span>' in view
    )
    assert "&lt;b&gt;x&lt;/b&gt;" in view and "<b>x</b>" not in view  # what the backlog says is text, never markup
    assert "and 2 more" in view  # eight findings: six shown


def test_every_stage_asks_claude_or_vibe_and_discover_can_start_the_ux_team():
    view = render(data())["view"]
    assert 'data-copy="claude &quot;crissp: help me with Plan&quot;"' in view
    assert 'data-copy="vibe &quot;crissp: help me with Plan&quot;"' in view
    assert 'data-copy="crissp: help me with Build"' in view
    assert view.count(">Ask Claude</button>") == 6 and view.count(">Ask Vibe</button>") == 6
    assert 'data-kind="round" data-walk="home">Start a round on “Home”</button>' in view
    assert stages.PROMPTS["review"].replace("'", "&#39;") in view


def test_without_the_server_the_page_says_how_to_open_it():
    assert "crissp dashboard" in render({}, ok=False)["view"]
