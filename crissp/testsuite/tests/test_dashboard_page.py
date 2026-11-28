"""F-70, F-71, F-73: what the Tests dashboard's page (dashboard/app.js) shows for a run, rendered by node with a stand-in
for the browser: every element the page asks for keeps the HTML it is given, so a test reads what a person would see."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]
APP = ENGINE / "testsuite" / "dashboard" / "app.js"

STAND_IN = r"""
const els = {};
const el = sel => els[sel] ??= { innerHTML: "", textContent: "", value: "", title: "", hidden: false, dataset: {}, open: false,
  classList: { toggle() {} }, set onclick(f) {}, set oninput(f) {}, set onchange(f) {}, scrollIntoView() {} };
global.document = { documentElement: { dataset: {} }, hidden: false, querySelector: el, querySelectorAll: () => [],
  getElementById: id => el("#" + id), addEventListener() {} };
global.window = { SUITE: %s, addEventListener() {} };
global.location = { hash: %s };
global.setInterval = () => 0; global.fetch = () => new Promise(() => {}); global.requestAnimationFrame = f => f();
require(%s);
console.log(JSON.stringify(Object.fromEntries(Object.entries(els).map(([k, v]) => [k, v.innerHTML]))));
"""


def step(key, label, status, log=""):
    return {"key": key, "label": label, "status": status, "seconds": 1, "log": log}


def run_data(**more):
    data = {"generatedAt": "2026-11-28 08:00:00", "root": "/p/shop", "product": "Shop", "monogram": "S",
            "steps": [step("backend", "CRISSP: the backend's tests (pytest under coverage)", "passed"),
                      step("backend-lint", "CRISSP: the backend's lint (ruff)", "failed"),
                      step("secrets", "CRISSP: secrets in the git history (gitleaks)", "failed")],
            "suites": {"backend": {"label": "CRISSP: the backend's tests (pytest under coverage)", "tests": 2, "passed": 1,
                                   "failed": 1, "skipped": 0, "time": 0.2},
                       "deploy": {"label": "Deploy template", "tests": 0, "passed": 0, "failed": 0, "skipped": 0, "time": 0}},
            "unitSuites": ["backend", "deploy"], "coverageKeys": [], "coverage": {}, "changes": [], "gaps": [], "gate": None,
            "threats": {"boundaries": []}, "capabilities": [], "journeys": [], "screenshots": [], "backlog": None,
            "lint": [{"key": "backend-lint", "label": "CRISSP: the backend's lint (ruff)", "status": "failed", "problems": 3,
                      "seconds": 0}],
            "security": [{"key": "audit", "label": "CRISSP: CVEs (trivy)", "status": "passed", "blocking": 0, "seconds": 1},
                         {"key": "secrets", "label": "CRISSP: secrets in the git history (gitleaks)", "status": "failed",
                          "blocking": 1, "seconds": 1}],
            "tests": [{"id": "test_a::test_fine", "name": "test_fine", "module": "test_a", "suite": "backend",
                       "status": "passed", "doc": "fine", "file": "tests/test_a.py", "abs": "/p/tests/test_a.py", "line": 1,
                       "time": 0.1},
                      {"id": "test_a::test_broken", "name": "test_broken", "module": "test_a", "suite": "backend",
                       "status": "failed", "doc": "broken", "detail": "AssertionError: " + "x" * 400,
                       "file": "tests/test_a.py", "abs": "/p/tests/test_a.py", "line": 9, "time": 0.1}]}
    data.update(more)
    return data


def render(data: dict, hash_: str = "") -> dict:
    if not shutil.which("node"):
        pytest.skip("no node on this machine")
    done = subprocess.run(["node", "-e", STAND_IN % (json.dumps(data), json.dumps(hash_), json.dumps(str(APP)))],
                          capture_output=True, text=True, timeout=30, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def test_the_overview_opens_with_the_verdict_and_what_stops_the_release():
    """F-70: the answer first. A red run says it is not ready and links each failed step to its own log."""
    view = render(run_data())["#view"]
    assert view.index("Not ready to release") < view.index("Lint")
    assert "2 of 3 steps failed" in view
    assert 'href="#steps?step=backend-lint"' in view and 'href="#steps?step=secrets"' in view
    assert ">The backend&#39;s lint<" in view  # a name, without the template's "CRISSP: " and the tool in brackets


def test_a_green_run_says_it_is_ready():
    view = render(run_data(steps=[step("backend", "Backend", "passed")], lint=[], security=[]))["#view"]
    assert "Green: ready to release" in view and "All 1 step of the last run passed." in view
    assert "No run yet" in render(run_data(steps=[], lint=[], security=[]))["#view"]


def test_security_has_its_own_tile_and_no_suite_of_zero_tests_is_listed():
    """F-73: the scans are a tile with what each found; the suites table only lists suites that ran tests."""
    view = render(run_data())["#view"]
    assert "Security" in view and "1 finding" in view and "nothing found" in view
    assert "Deploy template" not in view


def test_failing_tests_come_first_and_a_long_failure_wraps():
    """F-71: the Tests tab listed failures among 700 passing tests, and one long failure made the table 150,000 px wide."""
    rows = render(run_data(), "#tests")["#rows"]
    assert rows.index("broken") < rows.index("fine")
    assert '<pre class="log wrap">' in rows
    css = (ENGINE / "testsuite" / "dashboard" / "style.css").read_text(encoding="utf-8")
    assert "pre.log.wrap { overflow-wrap: anywhere;" in css


def test_the_changes_without_a_passing_test_can_be_listed_on_their_own():
    change = {"title": "T", "problem": "p", "fix": "f", "sources": [], "proof": [], "screenshots": [], "area": "a",
              "version": "1"}
    data = run_data(changes=[{**change, "id": "ok", "verdict": "passed"}, {**change, "id": "open", "verdict": "missing"}])
    assert "1 change without a passing test" in render(data)["#view"]
    listed = render(data, "#changes?open=1")["#view"]
    assert 'id="c-open"' in listed and 'id="c-ok"' not in listed


def test_a_failed_step_s_log_is_open_and_a_passed_one_folded():
    view = render(run_data(), "#steps?step=backend")["#view"]
    assert 'id="step-backend-lint" open' in view and 'id="step-backend" >' in view
