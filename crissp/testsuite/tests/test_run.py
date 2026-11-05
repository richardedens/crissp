"""lib/run.py runs the product's steps (crissp/testsuite/run.sh is its door): each in its folder, with what it needs to
know, its output in its log, the run's result in steps.json; the gate for the gated steps that ran. Real bash commands
on a small example product; pytest itself is never started from here."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location("run_under_test", LIB / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)

CONF = {"product": "Shop", "steps": [
    {"key": "unit", "label": "Unit tests", "dir": "app", "seconds": 3, "gate": True, "sources": ["app/shop"],
     "omit": ["*/tests/*"], "fail_under": 100,
     "run": 'echo "in $(basename "$PWD") for $STEP"; echo "$COVERAGE_SOURCES|$COVERAGE_OMIT|$COVERAGE_FAIL_UNDER"; '
            'echo "$JUNIT $COVERAGE_JSON"; type covered | head -1; [ -z "${UNIT_FAILS:-}" ]'},
    {"key": "lint", "label": "Lint", "run": 'echo "lint: ${COVERAGE_SOURCES:-none}"'},
    {"key": "build", "label": "Build", "run": "echo built", "full_only": True},
    {"key": "elsewhere", "label": "In a folder that is gone", "dir": "gone", "run": "true", "full_only": True}]}


@pytest.fixture
def shop(tmp_path, monkeypatch):
    root = tmp_path / "shop"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(json.dumps(CONF))
    (root / "app" / "shop").mkdir(parents=True)
    monkeypatch.delenv("UNIT_FAILS", raising=False)
    monkeypatch.setenv("COVERAGE_OMIT", "from-the-shell")  # never inherited by a step that leaves nothing out
    return root


def gate_stand_in(argv, **kw):
    """The gate is a Python script of the engine: here it only says what it was asked."""
    if argv[0] == sys.executable:
        kw["stdout"].write(" ".join(argv[1:]) + "\n")
        return subprocess.CompletedProcess(argv, 0)
    return subprocess.run(argv, **kw)


def results(root: Path) -> Path:
    return root / "crissp" / "testsuite" / "results"


def test_the_full_run_runs_every_step_in_its_folder_and_writes_what_it_proved(shop, capsys):
    assert run.main(["run.py"], shop, gate_stand_in) == 1  # the step in a folder that is gone is red
    out = capsys.readouterr().out
    assert "▸ Unit tests" in out and "passed (" in out and "▸ In a folder that is gone" in out and "failed (" in out
    r = results(shop)
    assert json.loads((r / "steps.json").read_text()) == {"unit": "passed", "gate": "passed", "lint": "passed",
                                                          "build": "passed", "elsewhere": "failed"}
    rows = [json.loads(line) for line in (r / "steps.jsonl").read_text().splitlines()]
    assert [x["key"] for x in rows] == ["unit", "gate", "lint", "build", "elsewhere"] and rows[0]["label"] == "Unit tests"
    unit = (r / "unit.log").read_text().splitlines()
    assert unit[0] == "in app for unit"
    assert unit[1] == f"{shop / 'app/shop'}|*/tests/*|100"  # what coverage measures, from the configuration
    assert unit[2] == f"{r / 'unit.xml'} {r / 'coverage-unit.json'}" and unit[3] == "covered is a function"
    assert (r / "lint.log").read_text() == "lint: none\n"  # no sources: no coverage settings, none from the shell
    assert (r / "gate.log").read_text().strip().endswith("gate.py --suites unit")
    assert (r / "elsewhere.log").read_text() == "no folder gone in the project\n"


def test_a_quick_run_leaves_out_the_full_run_only_steps_and_a_red_step_is_red(shop, monkeypatch, capsys):
    monkeypatch.setenv("UNIT_FAILS", "1")
    assert run.main(["run.py", "--quick"], shop, gate_stand_in) == 1
    assert json.loads((results(shop) / "steps.json").read_text()) == {"unit": "failed", "gate": "passed", "lint": "passed"}


def test_the_steps_a_change_touches_and_only_those(shop, capsys):
    (results(shop)).mkdir(parents=True)
    for name in ("lint.log", "unit.log", "gate.json", "coverage-unit.json"):
        (results(shop) / name).write_text("old")
    assert run.main(["run.py", "--quick", "lint"], shop, gate_stand_in) == 0
    r = results(shop)
    assert json.loads((r / "steps.json").read_text()) == {"lint": "passed"}
    assert (r / "unit.log").read_text() == "old" and (r / "gate.json").read_text() == "old"  # another step's results stay
    assert run.main(["run.py", "--quick", "unit", "gate", "build"], shop, gate_stand_in) == 0
    assert list(json.loads((r / "steps.json").read_text())) == ["unit", "gate", "build"]  # run order, not asked order
    assert not (r / "coverage-unit.json").exists() and not (r / "gate.json").exists()  # cleared before the step ran
    assert run.main(["run.py", "--quick", "gate"], shop, gate_stand_in) == 0
    assert (r / "gate.log").read_text().strip().endswith("gate.py")  # no gated step ran: the gate checks what it has


def test_a_step_the_product_does_not_have_or_a_broken_configuration_is_refused(shop, capsys):
    assert run.main(["run.py", "--quick", "smoke"], shop) == 2
    assert "run: unknown step smoke (known: unit gate lint build elsewhere)" in capsys.readouterr().err
    (shop / "crissp/testsuite/suites.json").write_text("{")
    assert run.main(["run.py"], shop) == 2 and "suites.json is not valid JSON" in capsys.readouterr().err
    assert run.select([], False, []) == []
    with pytest.raises(ValueError, match=r"\(known: none\)"):
        run.select([], False, ["x"])


def test_covered_runs_pytest_under_coverage_with_the_step_s_settings(tmp_path):
    """lib/steps.sh: pytest under coverage, lines and branches, of the sources; JUnit and JSON where the gate reads them."""
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "py").write_text('#!/usr/bin/env bash\necho "py $*" >> "$RESULTS/calls"\n[ "$*" != "${FAIL_ON:-}" ]\n')
    (bin_ / "py").chmod(0o755)
    env = {"PATH": "/usr/bin:/bin", "BASH_ENV": str(LIB / "steps.sh"), "PY": str(bin_ / "py"), "RESULTS": str(tmp_path),
           "JUNIT": "J.xml", "COVERAGE_JSON": "C.json", "COVERAGE_SOURCES": "/s", "COVERAGE_OMIT": "*/t/*",
           "COVERAGE_FAIL_UNDER": "100"}
    assert subprocess.run(["bash", "-c", "covered tests -k x"], env=env).returncode == 0
    assert (tmp_path / "calls").read_text().splitlines() == [
        "py -m coverage run --branch --source=/s --omit=*/t/* -m pytest -q -p no:cacheprovider --junitxml=J.xml tests -k x",
        "py -m coverage json -q -o C.json", "py -m coverage report --show-missing --fail-under=100"]
    below = {**env, "FAIL_ON": "-m coverage report --show-missing --fail-under=100"}
    assert subprocess.run(["bash", "-c", "covered tests"], env=below).returncode == 1  # under fail_under: red
    red = {**env, "FAIL_ON": "-m coverage run --branch --source=/s --omit=*/t/* -m pytest -q -p no:cacheprovider --junitxml=J.xml"}
    assert subprocess.run(["bash", "-c", "covered"], env=red).returncode == 1  # a red test is red
    plain = {k: v for k, v in env.items() if not k.startswith("COVERAGE_") or k == "COVERAGE_JSON"}
    (tmp_path / "calls").unlink()
    assert subprocess.run(["bash", "-c", "covered"], env=plain).returncode == 0
    assert (tmp_path / "calls").read_text().splitlines()[0] == \
        "py -m coverage run --branch -m pytest -q -p no:cacheprovider --junitxml=J.xml"


def test_without_py_it_runs_the_pinned_tools_with_uv(tmp_path):
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "uv").write_text('#!/usr/bin/env bash\necho "uv $*"\n')
    (bin_ / "uv").chmod(0o755)
    done = subprocess.run(["bash", "-c", "py -m coverage --version"], capture_output=True, text=True,
                          env={"PATH": f"{bin_}:/usr/bin:/bin", "BASH_ENV": str(LIB / "steps.sh"), "TOOLS": "/t/req.txt"})
    assert done.stdout == "uv run --quiet --no-project --with-requirements /t/req.txt python -m coverage --version\n"


def test_run_sh_is_a_door_to_run_py_after_setup():
    text = (LIB.parent / "run.sh").read_text()
    assert '"$SUITE/setup.sh" || exit 1' in text and 'exec python3 "$SUITE/lib/run.py" "$@"' in text
    assert 'export CRISSP_ROOT="${CRISSP_ROOT:-' in text


def test_run_as_a_script_it_runs_main(monkeypatch, tmp_path):
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path))  # no configuration there: refused, with why
    monkeypatch.setattr(sys, "argv", ["run.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB / "run.py"), run_name="__main__")
    assert stopped.value.code == 2
