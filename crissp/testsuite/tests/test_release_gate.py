"""The release gate: deploy.sh only goes ahead when a green full run tested exactly the code being deployed."""

import importlib.util
import json
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib" / "release.py"


def _module():
    spec = importlib.util.spec_from_file_location("release_under_test", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release = _module()
STEPS = ("unit", "gate", "lint", "build")  # the example product's steps: the gate follows its one gated step
CONFIG = {"product": "Shop", "steps": [
    {"key": "unit", "label": "Unit tests", "run": "covered", "gate": True, "sources": ["src"]},
    {"key": "lint", "label": "Lint", "run": "true"}, {"key": "build", "label": "Build", "run": "true", "full_only": True}]}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "app.py").write_text("print('v1')\n")
    (root / "crissp/testsuite/coverage-baseline.json").write_text("{}")
    (root / "crissp/testsuite/suites.json").write_text(json.dumps(CONFIG))
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "v1")
    return root


def _commit(root: Path, path: str, text: str) -> None:
    (root / path).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", path)


def _head(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD").strip()


def _run(root: Path, results: Path, *, failed: str = "", skip: str = "", during=None) -> None:
    """A full run as check-all.sh does it: start, run.sh's steps.json, finish."""
    release.start(root, results)
    if during:
        during()
    (results / "steps.json").write_text(json.dumps({k: "failed" if k == failed else "passed" for k in STEPS if k != skip}))
    release.finish(root, results)


def test_the_needed_steps_are_the_steps_of_the_full_run(tmp_path):
    """Every step of the project's full run is needed, the gate and the full-run-only ones too; a broken configuration
    is a step that can never have run, so nothing is certified on it."""
    root = _repo(tmp_path)
    assert release.needed(root) == list(STEPS)
    (root / "crissp/testsuite/suites.json").write_text("{")
    (need,) = release.needed(root)
    assert need.startswith("(the configuration: crissp/testsuite/suites.json is not valid JSON")


def test_a_green_full_run_of_this_exact_commit_may_be_deployed(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    assert release.check(root, results) == []
    cert = json.loads((results / "release.json").read_text())
    assert cert["commit"] == _head(root) and cert["changes"] == "" and cert["steps"]["build"] == "passed"


def test_without_a_full_run_nothing_is_deployed(tmp_path):
    reasons = release.check(_repo(tmp_path), tmp_path / "results")
    assert reasons == ["No full run found: run crissp/check-all.sh on this code."]


def test_a_red_or_missing_step_stops_the_deploy(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results, failed="lint")
    assert release.check(root, results) == ["Not green: lint."]
    _run(root, results, skip="build")  # a quick run is no full run
    assert release.check(root, results) == ["Not green: build (did not run)."]
    (results / "steps.json").unlink()
    release.start(root, results)
    release.finish(root, results)  # run.sh broke off before it wrote anything
    assert "Not green: unit (did not run)" in release.check(root, results)[0]


def test_code_committed_after_the_run_stops_the_deploy_until_check_sh_moved_the_certificate(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    tested = _head(root)
    _commit(root, "app.py", "print('v2')\n")
    reasons = release.check(root, results)
    assert len(reasons) == 1 and f"is not the tested commit {tested[:8]} (changed since: app.py)" in reasons[0]
    assert "crissp/check.sh" in reasons[0]


def test_even_a_committed_coverage_baseline_needs_check_sh_but_it_is_named(tmp_path):
    """HEAD must be exactly the certified commit; committing the raised baseline afterwards moves HEAD, and crissp/check.sh
    (which has nothing to test for it) moves the certificate along."""
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    _commit(root, "crissp/testsuite/coverage-baseline.json", '{"raised": 1}')
    assert "changed since: only the coverage baseline" in release.check(root, results)[0]
    assert release.advance({"files": ["crissp/testsuite/coverage-baseline.json"], "full": [], "passed": True}, root, results) == []
    assert release.check(root, results) == []


def test_a_tested_commit_that_is_gone_is_said_so(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    cert = json.loads((results / "release.json").read_text())
    (results / "release.json").write_text(json.dumps({**cert, "commit": "0" * 40}))
    assert "(the tested commit is not in this checkout any more)" in release.check(root, results)[0]


def test_many_changed_files_are_shortened(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    for i in range(10):
        (root / f"f{i}.py").write_text("x\n")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "many")
    assert "f7.py …)" in release.check(root, results)[0]


def test_uncommitted_changes_before_during_or_after_the_run_stop_the_deploy(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    (root / "app.py").write_text("print('half')\n")
    _run(root, results)
    assert any("uncommitted changes: commit everything" in r for r in release.check(root, results))
    _git(root, "checkout", "app.py")
    _run(root, results, during=lambda: (root / "app.py").write_text("print('edited while testing')\n"))
    reasons = release.check(root, results)
    assert any("changed while the run went on" in r for r in reasons)
    assert any("what you deploy must be exactly what was tested" in r for r in reasons)


def test_the_coverage_baseline_the_run_raises_is_not_a_code_change(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results, during=lambda: (root / "crissp/testsuite/coverage-baseline.json").write_text('{"raised": true}'))
    assert release.check(root, results) == []


def test_an_old_run_must_be_repeated(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    cert = json.loads((results / "release.json").read_text())
    (results / "release.json").write_text(json.dumps({**cert, "finished": time.time() - 8 * 24 * 3600}))
    assert release.check(root, results) == ["The last full run is older than 7 days: run crissp/check-all.sh."]
    assert release.check(root, results, max_age_hours=9 * 24) == []


def test_a_run_that_does_not_finish_leaves_the_last_certificate_for_its_own_commit_only(tmp_path):
    """Starting a full run does not throw the last green certificate away: until the new run has a result, the old one
    stands for exactly its own commit. Nothing is built on it, and newer code is refused as before."""
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    release.start(root, results)  # a new run starts on the same code, and is stopped before it finishes
    assert release.check(root, results) == []
    assert release.advance({"files": [], "full": [], "passed": True}, root, results) == [release.INTERRUPTED]
    _commit(root, "app.py", "print('v2')\n")
    assert any("app.py" in r for r in release.check(root, results))


def test_a_red_run_leaves_the_last_green_certificate_for_its_older_commit(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    green = _head(root)
    _commit(root, "app.py", "print('v2')\n")
    _run(root, results, failed="build")  # the newer code is red
    assert release.check(root, results) == ["Not green: build."]
    assert json.loads((results / "release-previous.json").read_text())["commit"] == green
    _git(root, "checkout", "-q", green)
    assert release.check(root, results) == []  # the older, green commit may still go
    _git(root, "checkout", "-q", "-")
    _run(root, results, failed="lint")  # red again: the green one before it still stands for its own commit
    assert json.loads((results / "release-previous.json").read_text())["commit"] == green
    _run(root, results)  # green: it replaces both
    assert not (results / "release-previous.json").exists() and release.check(root, results) == []


def test_a_red_run_of_the_same_commit_ends_its_green_certificate(tmp_path):
    """A red run of the very code a green one tested is newer evidence about that code: the old green goes."""
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    _run(root, results, failed="lint")
    assert release.check(root, results) == ["Not green: lint."]
    assert not (results / "release-previous.json").exists()


def test_the_previous_certificate_is_held_to_every_rule(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    green = _head(root)
    _commit(root, "app.py", "print('v2')\n")
    _run(root, results, failed="build")
    _git(root, "checkout", "-q", green)
    prev = json.loads((results / "release-previous.json").read_text())
    (results / "release-previous.json").write_text(json.dumps({**prev, "finished": time.time() - 8 * 24 * 3600}))
    assert any("build" in r for r in release.check(root, results))  # the red one's reasons are what is shown
    (results / "release-previous.json").write_text(json.dumps(prev))
    (root / "app.py").write_text("print('loose')\n")
    assert release.check(root, results)  # uncommitted changes: refused


# ------------------------------------------------------------------------------------------------ crissp/check.sh advances

def test_check_sh_advances_the_certificate_over_exactly_the_changes_it_tested(tmp_path):
    """After a green crissp/check.sh the certificate is about the new commit; a plan for other changes, a red plan or one that
    needed the full run does not move it."""
    root, results = _repo(tmp_path), tmp_path / "results"
    _run(root, results)
    _commit(root, "app.py", "print('v2')\n")
    tested = {"files": ["app.py"], "suites": ["unit"], "light": [], "full": [], "passed": True}
    assert release.advance({**tested, "files": ["other.py"]}, root, results) == [
        "The plan does not belong to the changes since the certificate: run crissp/check.sh again."]
    assert release.advance({**tested, "passed": False}, root, results) == ["The targeted tests were not green."]
    assert "touch shared ground" in release.advance({**tested, "full": ["x: shared"]}, root, results)[0]
    (root / "app.py").write_text("print('loose')\n")
    assert release.advance(tested, root, results) == ["There are uncommitted changes: commit them and run crissp/check.sh again."]
    _git(root, "checkout", "app.py")
    assert release.check(root, results)  # still red: app.py changed since the full run
    assert release.advance(tested, root, results) == []
    assert release.check(root, results) == []  # green for the new commit
    cert = json.loads((results / "release.json").read_text())
    assert cert["increments"][0]["suites"] == ["unit"] and cert["increments"][0]["to"] == cert["commit"]


def test_check_sh_cannot_build_on_a_missing_red_or_invalid_full_run(tmp_path):
    root, results = _repo(tmp_path), tmp_path / "results"
    ran = {"files": [], "full": [], "passed": True}
    assert release.advance(ran, root, results) == ["No full run to build on: run crissp/check-all.sh first."]
    _run(root, results, failed="build")
    assert release.advance(ran, root, results) == ["The last full run was not green (build): run crissp/check-all.sh."]
    _run(root, results, skip="build")
    assert release.advance(ran, root, results) == ["The last full run was not green (build): run crissp/check-all.sh."]
    (root / "app.py").write_text("print('half')\n")
    _run(root, results)
    assert release.advance(ran, root, results)[0].startswith("The last full run was not valid")


# ------------------------------------------------------------------------------------------------ the command line

def test_the_command_line(tmp_path, monkeypatch, capsys):
    root, results = _repo(tmp_path), tmp_path / "results"
    real = _module()
    monkeypatch.setenv("CRISSP_ROOT", str(root))  # the project: as the scripts export it
    results = root / "crissp" / "testsuite" / "results"
    assert real.main(["release.py", "check"]) == 1
    assert "No full run found" in capsys.readouterr().out
    assert real.main(["release.py", "start"]) == 0
    (results / "steps.json").write_text(json.dumps(dict.fromkeys(STEPS, "passed")))
    assert real.main(["release.py", "finish"]) == 0
    assert real.main(["release.py", "check", "--max-age-hours", "1"]) == 0
    assert capsys.readouterr().out == "Release gate: green for this commit.\n"
    ran = tmp_path / "ran.json"
    ran.write_text(json.dumps({"files": [], "full": [], "passed": False}))
    assert real.main(["release.py", "advance", str(ran)]) == 1
    assert capsys.readouterr().out.endswith("Certificate not moved.\n")
    ran.write_text(json.dumps({"files": [], "full": [], "passed": True}))
    assert real.main(["release.py", "advance", str(ran)]) == 0
    assert real.main(["release.py", "advance"]) == 2 and real.main(["release.py"]) == 2


def test_run_as_a_script_it_exits_with_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["release.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB), run_name="__main__")
    assert stopped.value.code == 2
