"""The coverage gate guards every other test: it has to be right itself."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

GATE = Path(__file__).resolve().parents[1] / "lib" / "gate.py"


def _module():
    spec = importlib.util.spec_from_file_location("gate_under_test", GATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate(tmp_path, monkeypatch):
    """The gate on a throwaway product with two gated suites (a backend "shop" and a "worker"): it keeps them apart and
    checks only those that ran. Coverage ran at the product's top, so it names files shop/a.py, worker/a.py."""
    module = _module()
    results = tmp_path / "results"
    sources = {"backend": [tmp_path / "shop"], "worker": [tmp_path / "worker"]}
    for (package,) in sources.values():
        package.mkdir(parents=True)
    monkeypatch.setattr(module, "RESULTS", results)
    monkeypatch.setattr(module, "BASELINE", tmp_path / "baseline.json")
    monkeypatch.setattr(module, "SOURCES", sources)
    monkeypatch.setattr(module, "DIRS", {"backend": tmp_path, "worker": tmp_path})
    monkeypatch.setattr(module, "OMIT", {"backend": ["*/tests/*"]})
    monkeypatch.setattr(module, "ROOT", tmp_path)
    return module


def _write(gate, key: str, files: dict[str, tuple[int, int, int, int]]) -> None:
    out = {"files": {}, "totals": {"covered_lines": 0, "num_statements": 0, "covered_branches": 0, "num_branches": 0}}
    for name, (cl, nl, cb, nb) in files.items():
        out["files"][name] = {"summary": {"covered_lines": cl, "num_statements": nl, "covered_branches": cb, "num_branches": nb}}
        for k, v in (("covered_lines", cl), ("num_statements", nl), ("covered_branches", cb), ("num_branches", nb)):
            out["totals"][k] += v
    gate.RESULTS.mkdir(exist_ok=True)
    (gate.RESULTS / f"coverage-{key}.json").write_text(json.dumps(out))


def measured(gate, backend_files, worker_files=None):
    """coverage.py-style JSON: files = {name: (covered_lines, lines, covered_branches, branches)}."""
    _write(gate, "backend", backend_files)
    _write(gate, "worker", worker_files or {"worker/a.py": (10, 10, 2, 2)})


def baseline(gate, key="backend"):
    return json.loads(gate.BASELINE.read_text())["suites"][key]


def problems(gate) -> list[str]:
    return json.loads((gate.RESULTS / "gate.json").read_text())["problems"]


REPO = GATE.parents[3]


def test_the_gate_holds_the_suites_the_product_gates(tmp_path):
    """configure(): the gated steps of suites.json, each with its sources, its folder and what it leaves out."""
    real = _module()
    real.configure(REPO)
    assert real.SOURCES == {"tools": [REPO / "crissp/testsuite/lib", REPO / "crissp/tool", REPO / "crissp/uxsuite"]}
    assert real.DIRS == {"tools": REPO / "crissp/testsuite"} and real.OMIT == {"tools": ["*/tests/*"]}
    assert real.BASELINE == REPO / "crissp/testsuite/coverage-baseline.json" and real.RESULTS == REPO / "crissp/testsuite/results"
    assert all(p.is_dir() for p in real.SOURCES["tools"])


def test_a_file_is_named_by_its_path_in_the_product_however_coverage_named_it(gate, tmp_path):
    gate.DIRS["backend"] = tmp_path / "app"
    assert gate.named("backend", "../shop/a.py") == "shop/a.py"  # relative to where coverage ran
    assert gate.named("backend", str(tmp_path / "shop/a.py")) == "shop/a.py"  # absolute
    assert gate.named("backend", "/elsewhere/x.py") == "/elsewhere/x.py"  # outside the product: as named
    (tmp_path / "shop/tests").mkdir()
    (tmp_path / "shop/tests/test_a.py").write_text("x = 1  # pragma: no cover\n")  # left out: not held, not checked
    (tmp_path / "shop/a.py").write_text("x = 1\n")
    (tmp_path / "single.py").write_text("y = 2\n")
    gate.SOURCES["backend"].append(tmp_path / "single.py")  # a source may be one file
    assert gate.files_of("backend") == [tmp_path / "shop/a.py", tmp_path / "single.py"]
    assert gate.pragmas(["backend"]) == ([], [])


def test_the_real_baseline_names_only_the_gated_suites_and_a_commit_when_it_has_one():
    """The baseline in git: per suite its totals and files, by their path in the project; a commit once a green run in a
    repository with commits made it. None before this repository's first full run."""
    path = GATE.parents[1] / "coverage-baseline.json"
    if not path.exists():
        pytest.skip("no baseline yet: the first full run sets it")
    data = json.loads(path.read_text())
    assert set(data) <= {"suites", "accepted", "commit"} and set(data["suites"]) <= {"tools"}
    assert all(name.startswith("crissp/") for name in data["suites"].get("tools", {}).get("files", {}))
    assert "commit" not in data or len(data["commit"]) == 40


def test_a_fresh_baseline_without_the_suite_is_set_by_the_first_run(gate, capsys):
    """Where the product starts: the committed baseline names no suite and no commit yet. The first green run sets it (even at
    low coverage: there is nothing to drop from) and records its commit; from then on the ratchet holds."""
    gate.BASELINE.write_text(json.dumps({"accepted": [], "suites": {}}))
    git(gate, "init", "-q")
    commit(gate, {"a.py": lines(4)})
    covered(gate, {"a.py": {"executed": [1], "missing": [2, 3, 4]}})
    assert gate.check(suites=["backend"]) == 0
    out = capsys.readouterr().out
    assert "diff coverage: skipped: no baseline commit recorded yet" in out and out.rstrip().endswith("coverage gate: green")
    data = json.loads(gate.BASELINE.read_text())
    assert data["suites"]["backend"]["files"]["shop/a.py"]["line"] == 25.0 and "worker" not in data["suites"]
    assert "commit" not in data  # only backend ran: the commit waits for a run of every suite
    assert gate.check() == 0 and json.loads(gate.BASELINE.read_text())["commit"] == head(gate)
    covered(gate, {"a.py": {"executed": [], "missing": [1, 2, 3, 4]}})
    assert gate.check() == 1 and "backend: shop/a.py line coverage dropped 25.0% → 0.0%" in problems(gate)


def test_the_first_run_sets_the_baseline_and_higher_raises_it(gate, capsys):
    measured(gate, {"shop/a.py": (8, 10, 1, 2)})
    assert gate.check() == 0 and baseline(gate)["files"]["shop/a.py"] == {"line": 80.0, "branch": 50.0}
    measured(gate, {"shop/a.py": (9, 10, 2, 2)})
    assert gate.check() == 0 and baseline(gate)["files"]["shop/a.py"] == {"line": 90.0, "branch": 100.0}
    out = capsys.readouterr().out
    assert "↑ coverage went up in 1 file(s); baseline raised" in out and out.rstrip().endswith("coverage gate: green")
    assert (gate.RESULTS / "gate.log").read_text().endswith("coverage gate: green\n")


def test_a_drop_is_red_and_does_not_move_the_baseline(gate, capsys):
    measured(gate, {"shop/a.py": (9, 10, 2, 2)})
    gate.check()
    measured(gate, {"shop/a.py": (8, 10, 2, 2)})
    assert gate.check() == 1
    assert baseline(gate)["files"]["shop/a.py"]["line"] == 90.0
    assert "backend: shop/a.py line coverage dropped 90.0% → 80.0%" in problems(gate)
    assert "backend: total line coverage dropped 90.0% → 80.0%" in problems(gate)
    out = capsys.readouterr().out
    assert "✗ backend: shop/a.py line coverage dropped" in out and "coverage gate: RED" in out


def test_a_file_at_100_stays_at_100(gate):
    measured(gate, {"shop/a.py": (10, 10, 2, 2)})
    gate.check()
    measured(gate, {"shop/a.py": (10, 10, 1, 2)})
    assert gate.check() == 1


def test_new_code_must_be_fully_tested(gate):
    measured(gate, {"shop/a.py": (5, 10, 0, 0)})
    gate.check()
    measured(gate, {"shop/a.py": (5, 10, 0, 0), "shop/new.py": (9, 10, 0, 0)})
    assert gate.check() == 1
    assert any(p.startswith("backend: new file shop/new.py is at 90.0% lines") for p in problems(gate))
    measured(gate, {"shop/a.py": (5, 10, 0, 0), "shop/new.py": (10, 10, 4, 4)})
    assert gate.check() == 0 and "shop/new.py" in baseline(gate)["files"]


def test_a_removed_file_leaves_the_baseline(gate):
    measured(gate, {"shop/a.py": (5, 10, 0, 0), "shop/old.py": (1, 10, 0, 0)})
    gate.check()
    measured(gate, {"shop/a.py": (5, 10, 0, 0)})
    assert gate.check() == 0 and "shop/old.py" not in baseline(gate)["files"]


def test_a_suite_without_a_measurement_is_red(gate):
    _write(gate, "backend", {"shop/a.py": (10, 10, 2, 2)})
    assert gate.check() == 1
    assert "worker: no coverage measured (did the tests run?)" in problems(gate)


def test_an_exception_needs_a_reason(gate):
    measured(gate, {"shop/a.py": (10, 10, 0, 0)})
    code = gate.SOURCES["worker"][0] / "x.py"
    code.write_text("if debug:  # pragma: no cover\n    pass\n")
    assert gate.check() == 1
    assert problems(gate) == ["worker/x.py:1: '# pragma: no cover' without a reason (write: # pragma: no cover — why)"]
    code.write_text("if debug:  # pragma: no cover — only on a developer's machine\n    pass\n")
    assert gate.check() == 0
    listed = json.loads((gate.RESULTS / "gate.json").read_text())["exceptions"]
    assert listed[0]["reason"] == "only on a developer's machine"


def test_an_explicit_acceptance_lowers_the_baseline_with_its_reason(gate, capsys):
    measured(gate, {"shop/a.py": (9, 10, 0, 0)})
    gate.check()
    measured(gate, {"shop/a.py": (8, 10, 0, 0)})
    assert gate.check() == 1
    assert gate.check("tested lines removed with the old importer") == 0
    data = json.loads(gate.BASELINE.read_text())
    assert data["suites"]["backend"]["files"]["shop/a.py"]["line"] == 80.0
    assert data["accepted"][-1]["reason"] == "tested lines removed with the old importer"
    assert "coverage gate: accepted: tested lines removed with the old importer" in capsys.readouterr().out


def test_a_run_of_some_suites_leaves_the_others_as_they_were(gate):
    """crissp/check.sh runs only the suites a change touches: the gate then checks those, and keeps the others' baseline."""
    measured(gate, {"shop/a.py": (9, 10, 0, 0)}, {"worker/a.py": (5, 10, 0, 0)})
    gate.check()
    (gate.RESULTS / "coverage-backend.json").unlink()  # the backend did not run this time
    _write(gate, "worker", {"worker/a.py": (6, 10, 0, 0)})
    assert gate.check(suites=["worker"]) == 0
    assert baseline(gate)["files"]["shop/a.py"]["line"] == 90.0 and baseline(gate, "worker")["line"] == 60.0
    assert json.loads((gate.RESULTS / "gate.json").read_text())["suites"] == ["worker"]
    _write(gate, "worker", {"worker/a.py": (4, 10, 0, 0)})
    assert gate.check(suites=["worker"]) == 1


# ------------------------------------------------------------------------------- diff coverage (new and changed lines)

def git(gate, *args):
    subprocess.run(["git", "-C", str(gate.ROOT), "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                   check=True, capture_output=True)


def commit(gate, files: dict[str, str | None]):
    """Write (or with None delete) files under the backend's package, then commit everything."""
    for name, text in files.items():
        path = gate.SOURCES["backend"][0] / name
        if text is None:
            path.unlink()
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    git(gate, "add", "-A")
    git(gate, "commit", "-q", "-m", "change")


def covered(gate, files: dict[str, dict]):
    """coverage.py JSON with line detail for the backend: {name: {executed, missing, excluded, branches, missed}}."""
    out = {"files": {}, "totals": {"covered_lines": 0, "num_statements": 0, "covered_branches": 0, "num_branches": 0}}
    for name, f in files.items():
        executed, missing = f.get("executed", []), f.get("missing", [])
        taken, missed = f.get("branches", []), f.get("missed", [])
        s = {"covered_lines": len(executed), "num_statements": len(executed) + len(missing),
             "covered_branches": len(taken), "num_branches": len(taken) + len(missed)}
        out["files"][f"shop/{name}"] = {"summary": s, "executed_lines": executed, "missing_lines": missing,
                                            "excluded_lines": f.get("excluded", []), "executed_branches": taken,
                                            "missing_branches": missed}
        for k, v in s.items():
            out["totals"][k] += v
    gate.RESULTS.mkdir(exist_ok=True)
    (gate.RESULTS / "coverage-backend.json").write_text(json.dumps(out))
    (gate.RESULTS / "coverage-worker.json").write_text(json.dumps(
        {"files": {}, "totals": {"covered_lines": 1, "num_statements": 1, "covered_branches": 0, "num_branches": 0}}))


def lines(n: int, first: int = 1) -> str:
    return "".join(f"x{i} = {i}\n" for i in range(first, first + n))


def head(gate) -> str:
    return subprocess.run(["git", "-C", str(gate.ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(gate):
    """A git checkout at ROOT whose baseline was taken at its first commit: a.py with 4 lines, 2 of them covered."""
    git(gate, "init", "-q")
    commit(gate, {"a.py": lines(4)})
    covered(gate, {"a.py": {"executed": [1, 2], "missing": [3, 4]}})
    assert gate.check() == 0
    assert json.loads(gate.BASELINE.read_text())["commit"] == head(gate)
    return gate


def diff(gate) -> dict:
    return json.loads((gate.RESULTS / "gate.json").read_text())["diff"]


A = "shop/a.py"


def test_without_a_baseline_commit_the_rule_is_skipped_with_a_message_and_a_green_run_records_one(gate, capsys):
    measured(gate, {"shop/a.py": (5, 10, 0, 0)})  # not a git checkout: nothing to record
    assert gate.check() == 0
    assert "diff coverage: skipped: no baseline commit recorded yet" in capsys.readouterr().out
    assert "commit" not in json.loads(gate.BASELINE.read_text())
    assert gate.diff_coverage("abc")["skipped"] == "not a git checkout with a commit: the changed lines cannot be found"
    git(gate, "init", "-q")  # a repository without commits (where the product started): still nothing to record
    assert gate.check() == 0 and "commit" not in json.loads(gate.BASELINE.read_text())
    commit(gate, {"a.py": lines(4)})
    assert gate.check() == 0 and diff(gate)["skipped"].startswith("no baseline commit recorded yet")
    data = json.loads(gate.BASELINE.read_text())
    assert data["commit"] == head(gate) and data["suites"]["backend"]["files"]["shop/a.py"]["line"] == 50.0


def test_a_checkout_below_another_repository_is_not_this_checkout(gate, tmp_path, monkeypatch):
    git(gate, "init", "-q")
    commit(gate, {"a.py": lines(1)})
    monkeypatch.setattr(gate, "ROOT", tmp_path / "shop")  # inside the repository, but not its top
    assert gate.head_commit() is None


def test_a_baseline_commit_git_does_not_know_is_skipped_never_a_crash(repo):
    data = json.loads(repo.BASELINE.read_text())
    data["commit"] = "0" * 40
    repo.BASELINE.write_text(json.dumps(data))
    assert repo.check() == 0
    assert "is not in this checkout" in diff(repo)["skipped"]
    assert json.loads(repo.BASELINE.read_text())["commit"] == head(repo)  # a green run starts the rule again from here


def test_a_changed_line_that_is_not_covered_is_red_even_when_the_file_percentage_holds(repo, capsys):
    start = head(repo)
    commit(repo, {"a.py": lines(6)})  # two lines added: one covered, one not; the file stays at 50%
    covered(repo, {"a.py": {"executed": [1, 2, 5], "missing": [3, 4, 6]}})
    assert repo.check() == 1
    out = capsys.readouterr().out
    assert f"✗ {A}:6: changed line not covered" in out
    assert "a.py:5:" not in out and "a.py:3:" not in out  # old untested lines are the ratchet's business
    assert f"diff coverage since {start[:10]}: 1/2 changed lines and 0/0 branches covered (50.0%)" in out
    d = diff(repo)
    assert (d["lines"], d["covered_lines"], d["percent"]) == (2, 1, 50.0)
    assert d["uncovered"] == [{"file": A, "line": 6, "what": "changed line not covered"}]
    assert json.loads(repo.BASELINE.read_text())["commit"] == start  # red: the baseline (and its commit) stay


def test_a_covered_change_is_green_and_moves_the_baseline_commit(repo):
    commit(repo, {"a.py": lines(2) + "x3 = 'changed'\n" + lines(1, 4) + lines(1, 5)})  # line 3 changed, line 5 added
    covered(repo, {"a.py": {"executed": [1, 2, 3, 5], "missing": [4]}})
    assert repo.check() == 0
    assert (diff(repo)["lines"], diff(repo)["covered_lines"], diff(repo)["uncovered"]) == (2, 2, [])
    assert json.loads(repo.BASELINE.read_text())["commit"] == head(repo)


def test_a_run_of_some_suites_keeps_the_baseline_commit(repo):
    """The diff rule of the next run then looks back at least as far: stricter, never laxer."""
    start = head(repo)
    commit(repo, {"a.py": lines(5)})
    covered(repo, {"a.py": {"executed": [1, 2, 5], "missing": [3, 4]}})
    assert repo.check(suites=["backend"]) == 0
    assert json.loads(repo.BASELINE.read_text())["commit"] == start
    assert repo.check(suites=["backend", "worker"]) == 0
    assert json.loads(repo.BASELINE.read_text())["commit"] == start  # no number moved: the older commit stays (stricter)
    covered(repo, {"a.py": {"executed": [1, 2, 3, 5], "missing": [4]}})
    assert repo.check(suites=["backend", "worker"]) == 0
    assert json.loads(repo.BASELINE.read_text())["commit"] == head(repo)  # numbers moved in a run of every suite


def test_a_branch_on_a_changed_line_that_is_never_taken_is_red(repo):
    commit(repo, {"a.py": lines(4) + "if x1:\n    x5 = 5\n"})
    covered(repo, {"a.py": {"executed": [1, 2, 5, 6], "missing": [3, 4], "branches": [[5, 6]], "missed": [[5, -1], [2, 3]]}})
    assert repo.check() == 1
    d = diff(repo)
    assert d["uncovered"] == [{"file": A, "line": 5, "what": "changed line: its branch to the exit is never taken"}]
    assert (d["branches"], d["covered_branches"]) == (2, 1)
    commit(repo, {"a.py": lines(4) + "if x1:\n    x5 = 5\nx6 = 6\n"})
    covered(repo, {"a.py": {"executed": [1, 2, 5, 6, 7], "missing": [3, 4], "missed": [[5, 7]]}})
    assert repo.check() == 1
    assert diff(repo)["uncovered"][-1]["what"] == "changed line: its branch to line 7 is never taken"


def test_a_changed_line_excluded_with_a_reason_does_not_count_and_without_one_is_red(repo):
    commit(repo, {"a.py": lines(4) + "if debug:  # pragma: no cover — only on a developer's machine\n    x5 = 5\n"})
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4], "excluded": [5, 6]}})
    assert repo.check() == 0 and diff(repo)["lines"] == 0 and diff(repo)["files"] == {}
    commit(repo, {"a.py": lines(4) + "if debug:  # pragma: no cover\n    x5 = 5\n"})
    assert repo.check() == 1


def test_deleted_lines_and_lines_without_code_add_nothing(repo):
    commit(repo, {"a.py": "# a comment\n" + lines(1, 1) + lines(2, 3)})  # x2 deleted, a comment added on top
    covered(repo, {"a.py": {"executed": [2, 3], "missing": [4]}})  # the comment is no statement
    assert repo.check() == 0
    assert (diff(repo)["lines"], diff(repo)["uncovered"]) == (0, [])


def test_a_deleted_file_adds_nothing(repo):
    commit(repo, {"b.py": lines(2)})
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4]}, "b.py": {"executed": [1, 2]}})
    assert repo.check() == 0
    commit(repo, {"b.py": None})
    assert repo.diff_coverage(head(repo) + "~1") == repo.diff_coverage(head(repo)) | {"base": head(repo) + "~1"}


def test_a_new_file_counts_every_line(repo):
    commit(repo, {"new.py": lines(3)})
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4]}, "new.py": {"executed": [1, 2], "missing": [3]}})
    assert repo.check() == 1
    d = diff(repo)
    assert d["files"]["shop/new.py"] == {"lines": 3, "covered_lines": 2, "branches": 0, "covered_branches": 0}
    assert [u["line"] for u in d["uncovered"]] == [3]


def test_a_renamed_file_counts_only_the_lines_changed_in_it(repo):
    base = json.loads(repo.BASELINE.read_text())["commit"]
    commit(repo, {"a.py": None, "b.py": lines(4) + lines(1, 5)})  # renamed, one line added
    covered(repo, {"b.py": {"executed": [1, 2], "missing": [3, 4, 5]}})
    d = repo.diff_coverage(base)
    assert d["uncovered"] == [{"file": "shop/b.py", "line": 5, "what": "changed line not covered"}]
    assert d["lines"] == 1  # the four moved lines are not new


def test_a_changed_file_coverage_did_not_measure_is_red(repo):
    commit(repo, {"c.py": lines(2), "notes.txt": "not python\n"})
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4]}})
    assert repo.check() == 1
    assert diff(repo)["uncovered"] == [{"file": "shop/c.py", "line": 1, "what": "changed, but not measured by coverage"}]


def test_a_suite_that_measured_nothing_is_left_to_the_other_rule(repo):
    commit(repo, {"a.py": lines(6)})
    (repo.RESULTS / "coverage-backend.json").unlink()
    assert repo.check() == 1
    assert diff(repo)["uncovered"] == [] and "backend: no coverage measured (did the tests run?)" in problems(repo)


def test_a_failing_git_diff_is_an_error_not_an_empty_change(repo):
    with pytest.raises(RuntimeError):
        repo.changed_lines("not-a-commit", ["backend"])


def test_a_branch_on_an_uncovered_changed_line_is_reported_once_as_the_line(repo):
    commit(repo, {"a.py": lines(4) + "if x1:\n    x5 = 5\n"})
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4, 5, 6], "missed": [[5, 6], [5, -1], [2, 3]]}})
    assert repo.check() == 1
    d = diff(repo)
    assert [(u["line"], u["what"]) for u in d["uncovered"]] == [(5, "changed line not covered"), (6, "changed line not covered")]
    assert d["branches"] == 0


# ------------------------------------------------------------------------------------------------ the command line

@pytest.mark.parametrize("argv, called", [
    ([], (None, None)),
    (["--accept", "code removed"], ("code removed", None)),
    (["--suites", "tools"], (None, ["tools"])),
    (["--suites", "tools,", "--accept", "why"], ("why", ["tools"])),
])
def test_the_command_line_hands_the_reason_and_the_suites_to_the_check(monkeypatch, argv, called):
    gate = _module()
    seen = []
    monkeypatch.setattr(gate, "check", lambda reason, suites: seen.append((reason, suites)) or 0)
    assert gate.main(["gate.py", *argv], REPO) == 0 and seen == [called]


@pytest.mark.parametrize("argv, message", [
    (["--accept"], "--accept needs a reason"),
    (["--accept", " "], "--accept needs a reason"),
    (["--suites"], "--suites takes a comma-separated list of tools"),
    (["--suites", "frontend"], "--suites takes a comma-separated list of tools"),
    (["--suites", "tools,shop"], "--suites takes a comma-separated list of tools"),
])
def test_wrong_arguments_are_refused(argv, message, capsys):
    assert _module().main(["gate.py", *argv], REPO) == 2 and message in capsys.readouterr().err


def test_a_product_without_a_configuration_is_refused(tmp_path, capsys):
    assert _module().main(["gate.py"], tmp_path) == 2 and "gate: crissp/testsuite/suites.json is missing" in capsys.readouterr().err


def test_run_as_a_script_it_exits_with_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["gate.py", "--accept"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(GATE), run_name="__main__")
    assert stopped.value.code == 2


def test_a_green_run_that_changes_no_number_leaves_the_baseline_as_it_is(repo):
    """Only numbers that move (or --accept) rewrite the baseline: a run with the same coverage on a later commit leaves
    the file byte for byte (the diff rule then looks back further, stricter, never laxer), so a green full run never
    asks for an extra commit just to record a hash."""
    before = repo.BASELINE.read_bytes()
    git(repo, "commit", "-q", "--allow-empty", "-m", "a change that moves no number")
    covered(repo, {"a.py": {"executed": [1, 2], "missing": [3, 4]}})
    assert repo.check() == 0
    assert repo.BASELINE.read_bytes() == before
    covered(repo, {"a.py": {"executed": [1, 2, 3], "missing": [4]}})  # a number moves: then the baseline and its commit do
    assert repo.check() == 0
    data = json.loads(repo.BASELINE.read_text())
    assert data["commit"] == head(repo) and data["suites"]["backend"]["files"]["shop/a.py"]["line"] == 75.0
