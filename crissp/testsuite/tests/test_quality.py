"""crissp/testsuite/lib/quality.py: Sonar-style metrics (complexity, duplication) held by a ratchet: they may only get
better, like coverage. Lizard is stood in: never a real run in a test."""

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("quality_under_test", LIB / "quality.py")
quality = importlib.util.module_from_spec(spec)
spec.loader.exec_module(quality)

BLOCK = "".join(f"    total = total + values[{n}] * {n + 1}\n" for n in range(12))


def row(file, function, ccn, start=1):
    """One line of lizard --csv: nloc, ccn, token, param, length, location, file, function, long_name, start, end."""
    return f'5,{ccn},40,1,6,"{function}@{start}-{start + 5}@{file}","{file}","{function}","{function}( x )",{start},{start + 5}'


class Lizard:
    """Stands in for the pinned lizard: answers with the CSV rows it was given, and records what it was asked."""

    def __init__(self, rows=(), code=0, err=""):
        self.rows, self.code, self.err, self.calls = list(rows), code, err, []

    def __call__(self, argv, cwd):
        self.calls.append((argv, cwd))
        return self.code, "\n".join(self.rows) + "\n", self.err


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app/backend").mkdir(parents=True)
    (tmp_path / "app/frontend/src").mkdir(parents=True)
    (tmp_path / "app/backend/shop.py").write_text("def price(values):\n    total = 0\n" + BLOCK + "    return total\n")
    (tmp_path / "app/backend/tests").mkdir()
    (tmp_path / "app/backend/tests/test_shop.py").write_text("def test_price():\n    assert True\n")
    (tmp_path / "app/frontend/src/cart.js").write_text("export const cart = [];\n")
    (tmp_path / "app/frontend/README.md").write_text("not code\n")
    return tmp_path


CONF = {"paths": ["app"]}


def test_files_are_the_code_under_the_paths_without_tests_or_vendored_code(repo):
    (repo / "app/frontend/node_modules/x").mkdir(parents=True)
    (repo / "app/frontend/node_modules/x/index.js").write_text("x\n")
    assert quality.files(repo, CONF) == ["app/backend/shop.py", "app/frontend/src/cart.js"]
    assert quality.files(repo, {"paths": ["app"], "exclude": ["*/frontend/*"]}) == ["app/backend/shop.py"]


def test_files_are_the_tracked_ones_in_a_git_repository(repo):
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "app/backend/shop.py"], cwd=repo, check=True)
    assert quality.files(repo, CONF) == ["app/backend/shop.py"]


def test_a_path_that_is_not_there_yet_is_listed_never_a_failure(repo):
    assert quality.absent(repo, {"paths": ["app", "web"]}) == ["web"]


def test_complexity_comes_from_the_pinned_lizard_per_function(repo):
    lizard = Lizard([row("app/backend/shop.py", "price", 18, 1), row("app/backend/shop.py", "price", 4, 30),
                     row("app/frontend/src/cart.js", "add", 3)])
    measured = quality.complexity(repo, ["app/backend/shop.py", "app/frontend/src/cart.js"], lizard)
    assert measured == {"app/backend/shop.py::price": {"file": "app/backend/shop.py", "function": "price", "line": 1, "ccn": 18},
                        "app/frontend/src/cart.js::add": {"file": "app/frontend/src/cart.js", "function": "add", "line": 1,
                                                          "ccn": 3}}  # two functions of one name: the worst counts
    (argv, cwd), = lizard.calls
    assert argv[:6] == ["uv", "tool", "run", "--quiet", "--from", quality.LIZARD] and "--csv" in argv and cwd == repo
    assert argv[-2:] == ["app/backend/shop.py", "app/frontend/src/cart.js"]


def test_a_lizard_that_cannot_run_is_a_problem_never_a_pass(repo):
    with pytest.raises(quality.QualityError, match="lizard could not run.*no uv"):
        quality.complexity(repo, ["app/backend/shop.py"], Lizard(code=2, err="no uv"))
    assert quality.complexity(repo, [], Lizard(code=2)) == {}  # nothing to measure: lizard is not asked


def test_duplication_finds_the_same_lines_in_two_files_whatever_their_indent(repo):
    (repo / "app/backend/copy.py").write_text("def other(values):\n  total = 1\n" + BLOCK.replace("    ", "  ") + "  return 0\n")
    found = quality.duplication(repo, ["app/backend/copy.py", "app/backend/shop.py"], 10)
    assert found["lines"] == 24 and found["of"] == 30 and found["percent"] == 80.0
    (block,) = found["blocks"]
    assert block == {"lines": 12, "at": [["app/backend/copy.py", 3], ["app/backend/shop.py", 3]]}


def test_duplication_skips_blank_lines_braces_and_comments_and_blocks_below_the_minimum(repo):
    trivial = "".join("}\n\n# a comment\n)\n" for _ in range(20))
    (repo / "a.js").write_text(trivial)
    (repo / "b.js").write_text(trivial)
    assert quality.duplication(repo, ["a.js", "b.js"], 10)["lines"] == 0
    assert quality.duplication(repo, ["app/backend/shop.py"], 10)["lines"] == 0  # one file, no copy
    assert quality.duplication(repo, [], 10) == {"min_lines": 10, "lines": 0, "of": 0, "percent": 0.0, "blocks": []}


def test_a_copy_inside_one_file_counts_too(repo):
    (repo / "twice.py").write_text("def a(values):\n" + BLOCK + "\n\ndef b(values):\n" + BLOCK)
    found = quality.duplication(repo, ["twice.py"], 10)
    assert found["lines"] == 24 and found["blocks"][0]["at"] == [["twice.py", 2], ["twice.py", 17]]


def measured(over=None, dup=0):
    over = over or {}
    return {"complex": {k: {"file": k.split("::")[0], "function": k.split("::")[1], "line": 1, "ccn": v}
                        for k, v in over.items()}, "duplication": {"lines": dup, "of": 100, "percent": float(dup)}}


def test_the_first_run_sets_the_baseline():
    verdict, baseline = quality.judge(measured({"a.py::f": 20}, 12), None)
    assert verdict == [] and baseline == {"complex": {"a.py::f": 20}, "duplicated_lines": 12}


def test_a_new_complex_function_more_complexity_or_more_copies_fail():
    base = {"complex": {"a.py::f": 20}, "duplicated_lines": 12}
    verdict, kept = quality.judge(measured({"a.py::f": 22, "b.py::g": 16}, 13), base)
    assert verdict == ["a.py::f grew more complex: cyclomatic complexity 22, was 20",
                       "b.py::g is new and too complex: cyclomatic complexity 16 (at most 15)",
                       "more duplicated lines: 13, was 12"]
    assert kept == base  # a red run never moves the baseline


def test_a_green_run_ratchets_the_baseline_down():
    base = {"complex": {"a.py::f": 20, "b.py::g": 17}, "duplicated_lines": 12}
    verdict, kept = quality.judge(measured({"a.py::f": 18}, 5), base)
    assert verdict == [] and kept == {"complex": {"a.py::f": 18}, "duplicated_lines": 5}


def test_accept_takes_the_numbers_as_they_are_with_the_reason():
    kept = quality.accepted(measured({"a.py::f": 30}, 40), "a parser that is complex by nature", "2026-11-28")
    assert kept == {"complex": {"a.py::f": 30}, "duplicated_lines": 40,
                    "accepted": {"reason": "a parser that is complex by nature", "on": "2026-11-28"}}


def suites(repo, conf):
    (repo / "crissp/testsuite").mkdir(parents=True, exist_ok=True)
    (repo / "crissp/testsuite/suites.json").write_text(json.dumps({"steps": [], "audit": {"quality": conf}}))


def test_main_measures_writes_the_results_and_ratchets(repo, monkeypatch, capsys):
    suites(repo, {"paths": ["app", "web"], "complexity": 15, "duplicate_lines": 10})
    monkeypatch.setattr(quality, "runner", Lizard([row("app/backend/shop.py", "price", 18)]))
    assert quality.main(["quality.py"], repo) == 0  # the first run: the baseline is set
    said = capsys.readouterr().out
    assert "app/backend/shop.py::price  cyclomatic complexity 18" in said and "baseline set" in said
    assert "not there yet, not measured: web" in said
    report = json.loads((repo / "crissp/testsuite/results/quality.json").read_text())
    assert report["ok"] and report["functions_over"] == 1 and report["regressions"] == []
    base = repo / "crissp/testsuite/quality-baseline.json"
    assert json.loads(base.read_text()) == {"complex": {"app/backend/shop.py::price": 18}, "duplicated_lines": 0}

    monkeypatch.setattr(quality, "runner", Lizard([row("app/backend/shop.py", "price", 19)]))
    assert quality.main(["quality.py"], repo) == 1
    said = capsys.readouterr().out
    assert "REGRESSION app/backend/shop.py::price grew more complex" in said and "--accept" in said
    assert json.loads(base.read_text())["complex"] == {"app/backend/shop.py::price": 18}

    assert quality.main(["quality.py", "--accept", "a known hard function"], repo) == 0
    assert json.loads(base.read_text())["accepted"]["reason"] == "a known hard function"
    assert "accepted" in capsys.readouterr().out

    monkeypatch.setattr(quality, "runner", Lizard([]))
    assert quality.main(["quality.py"], repo) == 0  # better: the baseline goes down
    assert json.loads(base.read_text()) == {"complex": {}, "duplicated_lines": 0}


def test_main_says_a_problem_and_a_wrong_call(repo, monkeypatch, capsys):
    suites(repo, {"paths": ["app"]})
    monkeypatch.setattr(quality, "runner", Lizard(code=1, err="uv: command not found"))
    assert quality.main(["quality.py"], repo) == 1
    assert "PROBLEM  lizard could not run" in capsys.readouterr().out
    assert quality.main(["quality.py", "--accept"], repo) == 2
    assert quality.main(["quality.py", "--accept", " "], repo) == 2
    (repo / "crissp/testsuite/suites.json").write_text("{")
    assert quality.main(["quality.py"], repo) == 2


def test_without_paths_there_is_nothing_to_measure(repo, monkeypatch, capsys):
    suites(repo, {"paths": ["web"]})
    monkeypatch.setattr(quality, "runner", Lizard())
    assert quality.main(["quality.py"], repo) == 0
    assert "Nothing to measure yet" in capsys.readouterr().out
    (repo / "crissp/testsuite/suites.json").write_text(json.dumps({"steps": []}))
    assert quality.main(["quality.py"], repo) == 0  # no quality section: the defaults (app)


def test_the_runner_runs_the_command(tmp_path):
    assert quality.runner(["python3", "-c", "print('ok')"], tmp_path) == (0, "ok\n", "")
    assert quality.runner(["no-such-command-crissp"], tmp_path)[0] == 127
