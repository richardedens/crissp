"""F-155: switching the frontend lint on takes no effort. crissp repair --yes and crissp init write the lint baseline of
every frontend_lint step that has none (lib/lint_start.py), and `crissp lint --baseline` writes them all again, with no
paths to type. npm and the tools are stand-ins (test_frontend_lint.Npm): no test reaches the network."""

import json
import sys
from pathlib import Path

import pytest
from test_frontend_lint import Npm

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import lint_ratchet
import lint_start
import repair

STEPS = [
    {
        "key": "frontend-lint",
        "label": "Frontend lint",
        "dir": "app/frontend",
        "run": "frontend_lint",
        "when": "app/frontend/package.json",
    },
    {"key": "admin-lint", "label": "Admin lint", "dir": "app", "run": "frontend_lint --react-compiler admin"},
    {"key": "backend-lint", "label": "Backend lint", "dir": "app/backend", "run": "ruff_check ."},
    {"key": "web-lint", "label": "Web lint", "dir": "app/web", "run": "frontend_lint", "when": "app/web/package.json"},
]


@pytest.fixture
def shop(tmp_path):
    root = tmp_path / "shop"
    (root / "crissp/testsuite").mkdir(parents=True)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps({"product": "Shop", "steps": STEPS}))
    for part in ("app/frontend", "app/admin"):
        (root / part / "src").mkdir(parents=True)
        (root / part / "package.json").write_text("{}")
        (root / part / "src/old.js").write_text("x\n")
    return root


def env(root: Path) -> dict:
    return {"CRISSP_CACHE": str(root.parent / "cache"), "CRISSP_STAGED": "/never/used"}


def test_every_frontend_lint_step_that_is_there_gets_its_baseline_once(shop, capsys):
    assert lint_start.pending(shop) == ["app/frontend", "app/admin"]  # web-lint: no app/web yet
    npm = Npm(found={"src/old.js": ["no-undef"]})
    assert lint_start.start(shop, env(shop), run=npm, which=lambda n: n) == 0
    folders = json.loads((shop / lint_ratchet.BASELINE).read_text())["folders"]
    assert {k: v["files"]["src/old.js"]["rules"] for k, v in folders.items()} == {
        "app/frontend": {"no-undef": 1},
        "app/admin": {"no-undef": 1},
    }
    admin = [
        env_
        for (tool, _, cwd), env_ in zip(npm.calls, npm.envs, strict=False)
        if tool == "eslint" and cwd.name == "admin"
    ]
    assert admin[0]["CRISSP_REACT_COMPILER"] == "1" and "CRISSP_STAGED" not in admin[0]  # as its step runs it
    assert "Frontend lint: the lint baseline of app/frontend" in capsys.readouterr().out
    assert lint_start.pending(shop) == []
    npm = Npm()
    assert lint_start.start(shop, env(shop), run=npm, which=lambda n: n) == 0
    assert npm.calls == []  # there already: nothing to do


def test_redo_writes_every_baseline_again_from_what_is_found_now(shop):
    assert lint_start.start(shop, env(shop), run=Npm(found={"src/old.js": ["no-undef"]}), which=lambda n: n) == 0
    assert lint_start.start(shop, env(shop), redo=True, run=Npm(), which=lambda n: n) == 0
    folders = json.loads((shop / lint_ratchet.BASELINE).read_text())["folders"]
    assert folders == {"app/frontend": {"files": {}}, "app/admin": {"files": {}}}


def test_a_lint_that_cannot_run_writes_no_baseline_and_says_how_to_later(shop, capsys):
    assert lint_start.start(shop, env(shop), run=Npm(), which=lambda n: None) == 1
    assert "crissp lint --baseline writes it once the lint can run" in capsys.readouterr().out
    assert lint_start.pending(shop) == ["app/frontend", "app/admin"]


def test_the_command_line(shop, capsys, monkeypatch):
    calls = []
    monkeypatch.setattr(lint_start, "start", lambda root, env, redo=False: calls.append((root, redo)) or 0)
    assert lint_start.main(["--redo"], {"CRISSP_ROOT": str(shop)}) == 0
    assert calls == [(shop, True)]
    assert lint_start.main(["--what"], {}) == 2
    assert lint_start.main([], {"CRISSP_ROOT": str(shop.parent)}) == 0  # no project, no steps
    assert "no frontend_lint step here" in capsys.readouterr().out


def test_repair_says_a_missing_baseline_and_yes_writes_it(shop, capsys, monkeypatch):
    monkeypatch.setattr(repair, "brought_in", lambda root: True)
    assert repair.fix_lint_baseline(shop).what.startswith("no lint baseline for app/frontend, app/admin →")
    repair.fix_lint_baseline(shop).do()  # main() writes it, after the other repairs
    written = []
    repair.main(["--yes"], {"CRISSP_ROOT": str(shop)}, lint=lambda root, env: written.append(root))
    assert written == [shop.resolve()] and "  lint-base  no lint baseline" in capsys.readouterr().out
    monkeypatch.setattr(repair, "brought_in", lambda root: False)
    assert repair.fix_lint_baseline(shop) is None
