"""crissp/testsuite/setup.sh installs only what is missing or out of date (lib/setup_plan.py decides and does it): uv,
the parts' venvs and node_modules the product's suites.json names, the commands its steps need. On a small example
product, with a stand-in for every installer: nothing is installed by a test."""

import importlib.util
import json
import os
import runpy
import subprocess
import sys
import time
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location("setup_plan_under_test", LIB / "setup_plan.py")
sp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sp)

CONF = {"product": "Shop", "steps": [{"key": "unit", "label": "Unit", "run": "true"}],
        "setup": {"venvs": ["app/backend"], "npm": ["app/frontend"], "needs": [{"command": "initdb", "hint": "brew install postgresql"}]}}
EVERYTHING = {"uv": "/bin/uv", "initdb": "/bin/initdb", "npm": "/bin/npm"}


@pytest.fixture
def shop(tmp_path):
    """A product with a backend (requirements that include the pinned tools) and a frontend, nothing installed."""
    root = tmp_path / "shop"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps(CONF))
    (root / "crissp/testsuite/requirements.txt").write_text("pytest==8.4.2\n")
    app = root / "app/backend"
    app.mkdir(parents=True)
    (app / "requirements.txt").write_text("fastapi==1.0\n")
    (app / "requirements-dev.txt").write_text(
        "-r requirements.txt  # the app\n# a comment\n-r ../../crissp/testsuite/requirements.txt\n--requirement requirements.txt\n")
    (root / "app/frontend").mkdir(parents=True)
    (root / "app/frontend/package-lock.json").write_text("{}")
    return root


def which(found: dict):
    return lambda name: found.get(name)


def conf(root: Path) -> dict:
    return sp.project.load(root)


def installed_venv(root: Path) -> None:
    venv = root / "app/backend/.venv"
    (venv / "bin").mkdir(parents=True, exist_ok=True)
    (venv / "bin/python").symlink_to(sys.executable)
    (venv / "bin/pip").write_text(f"#!{venv}/bin/python\n")
    sp.stamp(root / "app/backend", root)


def installed_npm(root: Path) -> None:
    record = root / "app/frontend/node_modules/.package-lock.json"
    record.parent.mkdir(parents=True)
    record.write_text("{}")


def test_requirements_follow_includes_once(shop):
    files = sp.requirement_files(shop / "app/backend/requirements-dev.txt")
    assert [f.name for f in files] == ["requirements-dev.txt", "requirements.txt", "requirements.txt"]
    assert files[2].parent.name == "testsuite" and sp.requirement_files(shop / "missing.txt") == []


def test_a_product_with_nothing_installed_gets_everything(shop):
    lines = sp.plan(shop, conf(shop), which=which({}), brew=shop / "no-uv")
    assert lines == ["uv missing", "venv app/backend missing", "npm app/frontend missing",
                     "need initdb brew install postgresql"]
    assert sp.plan(shop, conf(shop), version=(3, 11), which=which(EVERYTHING))[0] == "python too-old 3.11"
    assert "uv missing" not in sp.plan(shop, conf(shop), which=which({}), brew=Path(sys.executable))  # Homebrew's uv counts


def test_everything_in_place_is_nothing_to_do_and_a_change_makes_it_stale(shop):
    installed_venv(shop)
    installed_npm(shop)
    assert sp.plan(shop, conf(shop), which=which(EVERYTHING)) == []
    (shop / "crissp/testsuite/requirements.txt").write_text("pytest==9.0.0\n")  # the pinned tools moved on
    later = time.time() + 5
    os.utime(shop / "app/frontend/package-lock.json", (later, later))
    assert sp.plan(shop, conf(shop), which=which(EVERYTHING)) == ["venv app/backend stale", "npm app/frontend stale"]


def test_a_venv_that_is_broken_or_moved_is_made_anew(shop, tmp_path):
    venv = shop / "app/backend/.venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin/python").symlink_to(tmp_path / "gone-python")
    assert sp.venv_state(shop / "app/backend", shop) == "broken"
    (venv / "bin/python").unlink()
    (venv / "bin/python").symlink_to(sys.executable)
    (venv / "bin/pytest").write_text("#!/elsewhere/.venv/bin/python\n")
    assert sp.venv_state(shop / "app/backend", shop) == "moved"


class Installer:
    """A stand-in for venv, pip and npm: records each command; FAILS names the one that fails."""

    def __init__(self, fails: str = "") -> None:
        self.calls, self.fails = [], fails

    def __call__(self, argv, **kw):
        self.calls.append(argv)
        kw["stdout"].write(f"ran {' '.join(map(str, argv))}\n")
        if argv[1:3] == ["-m", "venv"]:
            installed = Path(argv[3])
            (installed / "bin").mkdir(parents=True)
            (installed / "bin/python").symlink_to(sys.executable)
        return subprocess.CompletedProcess(argv, 1 if self.fails and self.fails in " ".join(map(str, argv)) else 0)


def test_apply_installs_what_is_missing_and_says_what_it_changed(shop, capsys):
    run = Installer()
    assert sp.apply(shop, conf(shop), runner=run, which=which(EVERYTHING), python="/py") == 0
    assert [c[:3] for c in run.calls] == [["/py", "-m", "venv"], [str(shop / "app/backend/.venv/bin/python"), "-m", "pip"],
                                          ["npm", "ci", "--no-audit"]]
    out = capsys.readouterr().out
    assert "setup: app/backend/.venv made anew (missing)" in out and "app/frontend/node_modules installed (npm ci: missing)" in out
    assert sp.venv_state(shop / "app/backend", shop) == "ok"  # stamped
    (shop / "crissp/testsuite/requirements.txt").write_text("pytest==9.0.0\n")
    installed_npm(shop)
    run = Installer()
    assert sp.apply(shop, conf(shop), runner=run, which=which(EVERYTHING)) == 0
    assert len(run.calls) == 1 and "updated (its requirements changed)" in capsys.readouterr().out  # pip only, no new venv
    assert sp.apply(shop, conf(shop), runner=Installer(), which=which(EVERYTHING)) == 0 and capsys.readouterr().out == ""


@pytest.mark.parametrize("found, fails, version, message", [
    ({}, "", (3, 14), "setup: uv is missing. Install it: brew install uv"),
    (EVERYTHING, "", (3, 11), "this is Python 3.11; the testsuite needs 3.12 or newer"),
    ({"uv": "/bin/uv", "npm": "/bin/npm"}, "", (3, 14), "setup: initdb is missing: brew install postgresql"),
    (EVERYTHING, "-m venv", (3, 14), "could not make app/backend/.venv"),
    (EVERYTHING, "-m pip", (3, 14), "could not install app/backend/requirements-dev.txt"),
    ({"uv": "/bin/uv", "initdb": "/bin/initdb"}, "", (3, 14), "npm is missing. Install Node.js"),
    (EVERYTHING, "npm ci", (3, 14), "npm ci failed in app/frontend"),
])
def test_what_cannot_be_installed_stops_with_how_to_fix_it(shop, capsys, found, fails, version, message):
    assert sp.apply(shop, conf(shop), runner=Installer(fails), which=which(found), brew=shop / "no-uv", version=version) == 1
    err = capsys.readouterr().err
    assert message in err
    if fails:  # what the installer said is shown
        assert "----- last lines of crissp/testsuite/results/setup.log -----" in err and "ran " in err


def test_the_command_line_plans_applies_and_refuses(shop, capsys):
    installed_venv(shop)
    installed_npm(shop)
    conf = json.loads((shop / "crissp/testsuite/suites.json").read_text())
    conf["setup"]["needs"] = [{"command": "no-such-command-xyz", "hint": "install it"}]  # missing on every machine
    (shop / "crissp/testsuite/suites.json").write_text(json.dumps(conf))
    assert sp.main(["setup_plan.py", "plan"], shop) == 0
    assert capsys.readouterr().out.endswith("need no-such-command-xyz install it\n")
    shop_without_needs = json.loads((shop / "crissp/testsuite/suites.json").read_text())
    shop_without_needs["setup"] = {"venvs": ["app/backend"]}  # what is installed already, nothing this machine may lack
    (shop / "crissp/testsuite/suites.json").write_text(json.dumps(shop_without_needs))
    assert sp.main(["setup_plan.py", "apply"], shop) == (0 if sp.uv_path() else 1)
    assert sp.main(["setup_plan.py"], shop) == 2
    (shop / "crissp/testsuite/suites.json").write_text("{")
    assert sp.main(["setup_plan.py", "plan"], shop) == 1 and "setup: crissp/testsuite/suites.json is not valid JSON" in capsys.readouterr().err


def test_setup_sh_is_a_door_to_setup_plan():
    text = (LIB.parent / "setup.sh").read_text()
    assert 'exec python3 "$SUITE/lib/setup_plan.py" apply' in text and 'export CRISSP_ROOT="${CRISSP_ROOT:-' in text


def test_run_as_a_script_it_says_how_to_use_it(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["setup_plan.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB / "setup_plan.py"), run_name="__main__")
    assert stopped.value.code == 2
