"""check.sh and check-all.sh (doors to lib/check.py), run for real in a throwaway product with a stand-in for
crissp/testsuite/run.sh that records what it was asked to run: one run at a time, "commit first", the plan, exit 3 for
shared ground, the certificate moving on green and only on green, and a clear stop without git."""

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
LIB = ROOT / "crissp/testsuite/lib"
STEPS = "backend gate web build"
STAND_IN = """#!/usr/bin/env bash
# stand-in for crissp/testsuite/run.sh: records its arguments, writes steps.json; RUN_FAILS=<step> makes that step red
R="$(cd "$(dirname "$0")" && pwd)/results"; mkdir -p "$R"
echo "$*" >> "$R/run-args.txt"
[ "${1:-}" = --quick ] && shift
steps="${*:-%s}"
python3 - "$R/steps.json" "${RUN_FAILS:-}" $steps <<'PY'
import json, sys
out, fails, steps = sys.argv[1], sys.argv[2], sys.argv[3:]
json.dump({s: "failed" if s == fails else "passed" for s in steps}, open(out, "w"))
PY
if [ -n "${RUN_FAILS:-}" ]; then printf '✗ src/a.py:3: changed line not covered\\ncoverage gate: RED\\n' > "$R/gate.log"; exit 1; fi
rm -f "$R/gate.log"
""" % STEPS
SHOP = {"product": "Shop", "steps": [
    {"key": "backend", "label": "Backend", "dir": "app/backend", "run": "covered", "seconds": 40, "gate": True,
     "sources": ["app/backend/shop"]},
    {"key": "web", "label": "Frontend", "dir": "app/frontend", "run": "npm test", "seconds": 15},
    {"key": "build", "label": "Build", "run": "npm run build", "full_only": True}],
    "paths": [{"match": "app/backend/", "steps": ["backend"]}, {"match": "app/frontend/src/", "steps": ["web"]}],
    "shared": [{"match": "*/Dockerfile", "why": "what goes into an image"}]}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout


def product(tmp_path: Path) -> Path:
    """A throwaway shop with this repository's check scripts and libraries, stand-ins for run.sh and setup.sh."""
    root = tmp_path / "repo"
    (root / "crissp/testsuite/lib").mkdir(parents=True)
    for name in ("check.sh", "check-all.sh"):
        shutil.copy(ROOT / "crissp" / name, root / "crissp" / name)
    for name in ("check.py", "impact.py", "release.py", "project.py"):
        shutil.copy(LIB / name, root / "crissp/testsuite/lib" / name)
    (root / "crissp/testsuite/run.sh").write_text(STAND_IN)
    (root / "crissp/testsuite/setup.sh").write_text('#!/usr/bin/env bash\n[ -z "${SETUP_FAILS:-}" ] || { echo "setup: uv is missing" >&2; exit 1; }\n')
    for name in ("run.sh", "setup.sh"):
        (root / "crissp/testsuite" / name).chmod(0o755)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps(SHOP))
    (root / ".gitignore").write_text("crissp/testsuite/results/\n__pycache__/\n")
    (root / "app/backend/shop").mkdir(parents=True)
    (root / "app/backend/shop/main.py").write_text("x = 1\n")
    (root / "VERSION").write_text("0.1.0\n")
    (root / "CHANGELOG.md").write_text("## 0.1.0 — unreleased\n- first\n")
    return root


@pytest.fixture
def repo(tmp_path):
    root = product(tmp_path)
    _git(root, "init", "-q")
    return root


def door(root: Path, script: str, *args: str, **env: str) -> subprocess.CompletedProcess:
    """The script itself, as the product owner starts it."""
    clean = {k: v for k, v in os.environ.items() if k != "CRISSP_ROOT"}  # the script names its own project
    return subprocess.run([str(root / "crissp" / script), *args], cwd=root, capture_output=True, text=True,
                          env={**clean, **env}, timeout=120)


@pytest.fixture
def sh(capfd, monkeypatch):
    """What the script does, run in this process (so coverage sees lib/check.py), with the product's stand-ins for
    run.sh and setup.sh; its output and that of the stand-ins, as the script would print it."""
    check = _check()

    def call(root: Path, script: str, *args: str, **env: str) -> subprocess.CompletedProcess:
        monkeypatch.setattr(check, "SCRIPTS", root / "crissp/testsuite")
        for name in ("RUN_FAILS", "SETUP_FAILS"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        capfd.readouterr()
        code = check.main(["check.py", "changed" if script == "check.sh" else "all", *args], root)
        out, err = capfd.readouterr()
        return subprocess.CompletedProcess(script, code, out, err)
    return call


def commit(root: Path, path: str, text: str) -> None:
    (root / path).parent.mkdir(parents=True, exist_ok=True)
    (root / path).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", path)


def first_commit(root: Path) -> None:
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "one")


def cert(root: Path) -> dict:
    return json.loads((root / "crissp/testsuite/results/release.json").read_text())


def last_run(root: Path) -> str:
    return (root / "crissp/testsuite/results/run-args.txt").read_text().splitlines()[-1]


def test_without_git_check_sh_says_so_and_check_all_still_proves_the_tree(tmp_path, sh):
    """No .git: check.sh cannot know what changed since a green commit, so it stops with what to do (never a crash);
    check-all.sh still runs every step, for proof, and writes no certificate."""
    root = product(tmp_path)
    for args in ((), ("--plan",)):
        r = sh(root, "check.sh", *args)
        assert r.returncode == 2 and "Not a git checkout" in r.stderr and "Run git init and commit" in r.stderr
        assert "Traceback" not in r.stderr
    r = sh(root, "check-all.sh")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "writes no release certificate (run git init and commit for one)" in r.stderr
    assert "Every step passed (no certificate: not a git checkout)." in r.stdout and last_run(root) == ""
    assert not (root / "crissp/testsuite/results/release.json").exists()
    r = sh(root, "check-all.sh", RUN_FAILS="web")
    assert r.returncode == 1 and "Not green: fix what failed above" in r.stdout
    assert sh(root, "check-all.sh", SETUP_FAILS="1").returncode == 1


def test_a_repository_without_a_commit_is_refused(repo, sh):
    r = sh(repo, "check-all.sh")
    assert r.returncode == 2 and "No commit yet: commit first" in r.stderr
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 2 and "No full run yet: start with crissp/check-all.sh." in r.stderr


def test_the_full_run_writes_a_green_certificate_and_check_sh_builds_on_it(repo, sh):
    first_commit(repo)
    r = sh(repo, "check-all.sh")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Green: crissp/deploy.sh may go." in r.stdout and cert(repo)["commit"] == _git(repo, "rev-parse", "HEAD").strip()
    assert not (repo / "crissp/testsuite/results/.run.lock").exists()  # the lock goes with the run
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 0 and "Nothing changed since the last green state." in r.stdout

    commit(repo, "docs/notes.md", "a note\n")
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 0 and "1 changed file(s)" in r.stdout and "Notes only, nothing to test: 1 file(s)" in r.stdout
    r = sh(repo, "check.sh")
    assert r.returncode == 0 and "Green: crissp/deploy.sh may go." in r.stdout
    assert cert(repo)["commit"] == _git(repo, "rev-parse", "HEAD").strip()

    commit(repo, "app/backend/shop/main.py", "x = 2\n")
    commit(repo, "CHANGELOG.md", "## 0.1.0 — unreleased\n- first\n- second\n")
    r = sh(repo, "check.sh", "--plan")
    assert "Light checks: release-notes" in r.stdout and "Suites: backend, gate" in r.stdout and "About 1 min." in r.stdout
    before = cert(repo)["commit"]
    r = sh(repo, "check.sh", RUN_FAILS="gate")
    assert r.returncode == 1 and "✗ src/a.py:3: changed line not covered" in r.stdout and "Not green" in r.stdout
    assert cert(repo)["commit"] == before  # red: the certificate stays
    r = sh(repo, "check.sh")
    assert r.returncode == 0 and "Release notes (VERSION, CHANGELOG.md)" in r.stdout and last_run(repo) == "--quick backend gate"
    assert cert(repo)["commit"] == _git(repo, "rev-parse", "HEAD").strip()


def test_red_release_notes_are_red_and_the_certificate_stays(repo, sh):
    first_commit(repo)
    assert sh(repo, "check-all.sh").returncode == 0
    commit(repo, "VERSION", "0.2.0\n")
    r = sh(repo, "check.sh")
    assert r.returncode == 1 and "FAILED" in r.stdout and "should name the version in VERSION (0.2.0)" in r.stdout


def test_shared_ground_stops_check_sh_with_exit_3(repo, sh):
    first_commit(repo)
    assert sh(repo, "check-all.sh").returncode == 0
    commit(repo, "app/backend/Dockerfile", "FROM python\n")
    for args in (("--plan",), ()):
        r = sh(repo, "check.sh", *args)
        assert r.returncode == 3 and "Needs the full run (crissp/check-all.sh), because:" in r.stdout
        assert "app/backend/Dockerfile: what goes into an image" in r.stdout


def test_uncommitted_changes_are_refused(repo, sh):
    first_commit(repo)
    assert sh(repo, "check-all.sh").returncode == 0
    (repo / "app/backend/shop/main.py").write_text("x = 'loose'\n")
    for script in ("check.sh", "check-all.sh"):
        r = sh(repo, script)
        assert r.returncode == 2 and "Commit your changes first" in r.stderr and "main.py" in r.stderr


def test_a_red_full_run_says_so_and_fails(repo, sh):
    first_commit(repo)
    r = sh(repo, "check-all.sh", RUN_FAILS="web")
    assert r.returncode == 1 and "Not green: web." in r.stdout and "Not green: fix what failed above" in r.stdout


def test_one_run_at_a_time(repo, sh):
    first_commit(repo)
    lock = repo / "crissp/testsuite/results/.run.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(os.getpid()))  # a process that is alive: this test
    (lock / "what").write_text("check-all.sh")
    for script in ("check.sh", "check-all.sh"):
        r = sh(repo, script)
        assert r.returncode == 4 and "A run is already in progress (check-all.sh" in r.stderr
    (lock / "pid").write_text("999999")  # left behind by a run that was killed
    assert sh(repo, "check-all.sh").returncode == 0 and not lock.exists()


def test_a_setup_that_cannot_install_stops_the_run_with_its_fix(repo, sh):
    first_commit(repo)
    r = sh(repo, "check-all.sh", SETUP_FAILS="1")
    assert r.returncode == 1 and "setup: uv is missing" in r.stderr and not (repo / "crissp/testsuite/results/release.json").exists()
    assert sh(repo, "check-all.sh").returncode == 0
    commit(repo, "app/backend/shop/main.py", "x = 2\n")
    r = sh(repo, "check.sh", SETUP_FAILS="1")
    assert r.returncode == 1 and "setup: uv is missing" in r.stderr
    assert sh(repo, "check.sh", "--plan", SETUP_FAILS="1").returncode == 0  # the plan only reads: no setup needed


def test_check_sh_runs_the_steps_the_product_s_map_names(repo, sh):
    first_commit(repo)
    assert sh(repo, "check-all.sh").returncode == 0
    commit(repo, "app/frontend/src/layout.ts", "export const gap = 4;\n")
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 0 and "Suites: web" in r.stdout and "backend" not in r.stdout
    commit(repo, "app/backend/shop/pricing.py", "PRICE = 1\n")
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 0 and "Suites: backend, gate, web" in r.stdout
    assert sh(repo, "check.sh").returncode == 0 and last_run(repo) == "--quick backend gate web"
    commit(repo, "Makefile", "all:\n")
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 3 and "Makefile: not mapped to a part of Shop" in r.stdout


def test_a_baseline_raised_by_the_run_is_named_and_a_certificate_that_cannot_move_says_why(repo, sh):
    first_commit(repo)
    (repo / "crissp/testsuite/coverage-baseline.json").write_text("{}")
    _git(repo, "add", ".")
    _git(repo, "commit", "-qm", "baseline")
    (repo / "crissp/testsuite/run.sh").write_text(STAND_IN + 'echo "{\\"raised\\": 1}" > "$R/../coverage-baseline.json"\n')
    _git(repo, "commit", "-qam", "a run that raises the baseline")
    r = sh(repo, "check-all.sh")
    assert r.returncode == 0 and "The coverage baseline went up: commit crissp/testsuite/coverage-baseline.json" in r.stdout
    _git(repo, "commit", "-qam", "the raised baseline")
    commit(repo, "docs/x.md", "x\n")
    results = repo / "crissp/testsuite/results"
    started = json.loads((results / "release-start.json").read_text())
    (results / "release-start.json").write_text(json.dumps({**started, "started": started["started"] + 9e9}))  # a run broke off
    r = sh(repo, "check.sh")
    assert r.returncode == 1 and "A full run was started after this certificate" in r.stdout and "Certificate not moved." in r.stdout


def test_a_broken_configuration_or_a_lost_commit_stops_the_plan(repo, sh):
    first_commit(repo)
    assert sh(repo, "check-all.sh").returncode == 0
    results = repo / "crissp/testsuite/results"
    (results / "release.json").write_text(json.dumps({**cert(repo), "commit": "0" * 40}))
    r = sh(repo, "check.sh", "--plan")
    assert r.returncode == 2 and "The plan could not be made" in r.stderr


# ------------------------------------------------------------------------------------------------ check.py itself

def _check():
    sys.path.insert(0, str(LIB))
    spec = importlib.util.spec_from_file_location("check_under_test", LIB / "check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_command_line_takes_changed_or_all(tmp_path, monkeypatch, capsys):
    check = _check()
    seen = []
    monkeypatch.setattr(check, "everything", lambda root: seen.append(("all", root)) or 0)
    monkeypatch.setattr(check, "changed", lambda root, plan: seen.append(("changed", plan)) or 0)
    assert check.main(["check.py", "all"], tmp_path) == 0 and check.main(["check.py", "changed", "--plan"], tmp_path) == 0
    assert check.main(["check.py", "changed"], tmp_path) == 0 and seen == [("all", tmp_path), ("changed", True), ("changed", False)]
    for argv in ([], ["changed", "--now"], ["all", "x"], ["deploy"]):
        assert check.main(["check.py", *argv], tmp_path) == 2
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path))
    assert check.main(["check.py", "all"]) == 0 and seen[-1] == ("all", tmp_path.resolve())


def test_a_lock_with_a_living_owner_but_no_details_still_says_a_run_holds_it(tmp_path):
    check = _check()
    lock = tmp_path / ".run.lock"
    lock.mkdir()
    (lock / "pid").write_text(str(os.getpid()))
    assert check.Lock(tmp_path, "x").take() == "A run is already in progress (a run, started ?). Wait for it, or stop it first."


def test_the_doors_run_check_py_for_their_own_project(tmp_path):
    """The scripts themselves: without git, check.sh stops with what to do; check-all.sh still proves the tree."""
    root = product(tmp_path)
    r = door(root, "check.sh", "--plan")
    assert r.returncode == 2 and "Not a git checkout" in r.stderr and "Traceback" not in r.stderr
    r = door(root, "check-all.sh")
    assert r.returncode == 0 and "Every step passed (no certificate: not a git checkout)." in r.stdout
    _git(root, "init", "-q")
    first_commit(root)
    r = door(root, "check-all.sh")
    assert r.returncode == 0 and "Green: crissp/deploy.sh may go." in r.stdout


def test_the_scripts_are_doors_to_check_py():
    for script, command in (("check.sh", "changed"), ("check-all.sh", "all")):
        text = (ROOT / "crissp" / script).read_text()
        assert f'exec python3 "$ENGINE/testsuite/lib/check.py" {command} "$@"' in text  # the engine: next to the script
        assert 'export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"' in text  # the project: crissp sets it


def test_run_as_a_script_it_says_how_to_use_it(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["check.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB / "check.py"), run_name="__main__")
    assert stopped.value.code == 2


def test_the_first_full_run_says_plainly_what_is_left(repo, sh):
    """F-06: a new project's first full run writes the baseline; it says that, and the exact commands that follow."""
    first_commit(repo)
    assert not (repo / "crissp/testsuite/coverage-baseline.json").exists()
    (repo / "crissp/testsuite/run.sh").write_text(STAND_IN + 'echo "{\\"first\\": 1}" > "$R/../coverage-baseline.json"\n')
    _git(repo, "commit", "-qam", "a run that writes the first baseline")
    r = sh(repo, "check-all.sh")
    assert r.returncode == 0 and "This was the first full run: it wrote the coverage baseline." in r.stdout
    assert "git add crissp/testsuite/coverage-baseline.json && git commit -m \"Coverage baseline\"" in r.stdout
    assert "went up" not in r.stdout
