"""F-101: what the Activity page (dashboard/activity.js) shows for Claude's and Vibe's sessions, rendered by node with
a stand-in for the browser that answers activity.json with the data given."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).resolve().parents[1] / "dashboard" / "activity.js"

STAND_IN = r"""
const els = {};
const el = sel => els[sel] ??= { innerHTML: "", textContent: "" };
global.document = { hidden: false, querySelector: el, querySelectorAll: () => [], addEventListener() {} };
global.window = {};
global.setInterval = () => 0;
global.fetch = async () => ({ ok: true, text: async () => %s });
require(%s);
setTimeout(() => console.log(JSON.stringify(els["#view"].innerHTML)), 50);
"""


def render(data: dict) -> str:
    if not shutil.which("node"):
        pytest.skip("no node on this machine")
    done = subprocess.run(
        ["node", "-e", STAND_IN % (json.dumps(json.dumps(data)), json.dumps(str(PAGE)))],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def one(source: str, **more) -> dict:
    return {
        "id": f"{source}-1",
        "source": source,
        "title": f"{source} work",
        "history": 343_000,
        "long": True,
        "prompt": "do it",
        "busy": True,
        "updated": 1,
        "main": None,
        "agents": [],
        "earlier": 0,
        **more,
    }


def test_vibe_sessions_show_beside_claudes_with_their_own_advice():
    view = render({"sessions": [one("vibe"), one("claude", earlier=2)], "now": 1, "product": "P", "monogram": "P"})
    vibe, claude = view.split('<article class="card session">')[1:]
    assert "Mistral Vibe" in vibe and "Claude Code" in claude
    assert "/results/sessions/" not in vibe and "/results/sessions/claude-1.html" in claude  # Vibe has no session page
    assert "new session in the desktop app" in vibe and "/clear" in claude
    assert "343k tokens" in vibe


def test_no_session_at_all_names_both():
    view = render({"sessions": [], "now": 1, "product": "P", "monogram": "P"})
    assert "No Claude or Vibe session" in view


def test_the_context_budget_warnings_show():
    """F-104: what a session spends its context on, said where its history is."""
    view = render(
        {
            "sessions": [one("vibe", long=False, budget=["12 images in the main thread"])],
            "now": 1,
            "product": "P",
            "monogram": "P",
        }
    )
    assert "12 images in the main thread" in view and "context budget" in view
