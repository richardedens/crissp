"""F-50: before every commit, git runs the project's lint steps (.githooks/pre-commit, `crissp hook`, lib/hook.py).
crissp init and crissp repair turn the hook on with core.hooksPath, but never over hooks a project already has."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import hook

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@example.org", "PATH": "/usr/bin:/bin"}
STEPS = [
    {"key": "backend", "label": "Backend", "dir": ".", "run": "echo backend-ran"},
    {"key": "backend-lint", "label": "Backend lint", "dir": ".", "run": "echo backend-lint-ran"},
    {"key": "lint", "label": "Lint", "dir": ".", "run": "echo lint-ran; ${LINT_FAILS:+false}"},
    {"key": "frontend-lint", "label": "Frontend lint", "dir": "app/frontend", "run": "echo never",
     "when": "app/frontend/package.json"},
    {"key": "linter-tests", "label": "Not a lint step", "dir": ".", "run": "echo linter-tests-ran"},
]


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False,
                          env={**GIT_ENV, "HOME": str(root)})


@pytest.fixture
def shop(tmp_path) -> Path:
    root = tmp_path / "shop"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps({"product": "Shop", "steps": STEPS}))
    return root


def test_the_lint_steps_are_lint_and_every_step_ending_in_lint_that_is_there(shop):
    assert [s["key"] for s in hook.lint_steps(shop)] == ["backend-lint", "lint"]  # frontend-lint: no app/frontend yet


def test_the_hook_runs_each_lint_step_in_its_folder_with_the_step_helpers(shop, capfd):
    assert hook.run(shop, env={"PATH": "/usr/bin:/bin"}) == 0
    out = capfd.readouterr().out
    assert "backend-lint-ran" in out and "lint-ran" in out and "backend-ran" not in out and "linter-tests" not in out
    assert "crissp hook: Backend lint passed" in out and "crissp hook: Lint passed" in out


def test_a_red_lint_step_stops_the_commit_and_says_how_to_skip_it_once(shop, capfd):
    assert hook.run(shop, env={"PATH": "/usr/bin:/bin", "LINT_FAILS": "1"}) == 1
    out = capfd.readouterr().out
    assert "crissp hook: Lint failed" in out and "git commit --no-verify" in out


def test_the_step_helpers_and_pinned_tools_are_at_hand(shop):
    seen = {}
    hook.run(shop, env={"PATH": "/usr/bin:/bin"}, runner=lambda cmd, cwd, env, check: seen.update(env=env, cwd=cwd)
             or subprocess.CompletedProcess(cmd, 0))
    assert seen["env"]["BASH_ENV"] == str(hook.ENGINE / "steps.sh") and seen["env"]["TOOLS"] == str(hook.TOOLS)
    assert seen["env"]["CRISSP_ROOT"] == str(shop) and seen["cwd"] == shop


def test_a_project_without_lint_steps_commits_and_hears_why(tmp_path, capsys):
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    (tmp_path / "crissp/testsuite/suites.json").write_text(json.dumps({"product": "Bare", "steps": []}))
    assert hook.run(tmp_path, env={}) == 0
    assert "no lint steps" in capsys.readouterr().out


def test_a_broken_configuration_stops_the_commit(tmp_path, capsys):
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    (tmp_path / "crissp/testsuite/suites.json").write_text("{")
    assert hook.run(tmp_path, env={}) == 1
    assert "crissp hook:" in capsys.readouterr().out


def test_state_and_turn_on(tmp_path):
    assert hook.state(tmp_path) == "no-git"
    git(tmp_path, "init", "-q")
    assert hook.state(tmp_path) == "off"
    hook.turn_on(tmp_path)
    assert hook.state(tmp_path) == "on" and git(tmp_path, "config", "core.hooksPath").stdout.strip() == ".githooks"


def test_hooks_a_project_already_has_are_never_switched_off(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / ".git/hooks/pre-commit").write_text("#!/bin/sh\nexit 0\n")  # a hook of its own (not a .sample)
    assert hook.state(tmp_path) == "local-hooks"
    (tmp_path / ".git/hooks/pre-commit").unlink()
    git(tmp_path, "config", "core.hooksPath", ".husky")
    assert hook.state(tmp_path) == "other"


def test_without_git_installed_there_is_no_git(tmp_path, monkeypatch):
    def gone(*a, **k):
        raise FileNotFoundError("git")
    monkeypatch.setattr(hook.subprocess, "run", gone)
    assert hook.state(tmp_path) == "no-git"


def test_main_runs_the_hook_for_crissp_root_and_refuses_arguments(shop, capfd):
    assert hook.main([], {"CRISSP_ROOT": str(shop), "PATH": "/usr/bin:/bin"}) == 0
    assert "lint-ran" in capfd.readouterr().out
    assert hook.main(["--what"], {}) == 2 and "usage: crissp hook" in capfd.readouterr().out


def test_the_pre_commit_hook_runs_the_lint_and_blocks_a_red_commit(shop):
    """The real hook file in a real repository: a green lint commits, a red one does not."""
    git(shop, "init", "-q")
    (shop / ".githooks").mkdir()
    (shop / ".githooks/pre-commit").write_bytes((hook.TEMPLATE / "githooks" / "pre-commit").read_bytes())
    (shop / ".githooks/pre-commit").chmod(0o755)
    engine = shop / "crissp/testsuite/lib"  # as in the framework's checkout: the engine is at hand
    engine.mkdir()
    (engine / "hook.py").write_text("import sys\nprint('the engine hook ran')\nsys.exit(int(__import__('os').environ"
                                    ".get('LINT_FAILS', '0')))\n")
    hook.turn_on(shop)
    git(shop, "add", "-A")
    done = git(shop, "commit", "-qm", "green")
    assert done.returncode == 0 and "the engine hook ran" in done.stdout + done.stderr
    (shop / "x").write_text("x")
    git(shop, "add", "x")
    red = subprocess.run(["git", "-C", str(shop), "commit", "-qm", "red"], capture_output=True, text=True, check=False,
                         env={**GIT_ENV, "HOME": str(shop), "LINT_FAILS": "1"})
    assert red.returncode != 0 and git(shop, "log", "--oneline").stdout.count("\n") == 1


def test_this_repository_has_the_templates_hook():
    """The framework lints itself the same way: .githooks/pre-commit is the template's, executable."""
    ours, template = REPO / ".githooks/pre-commit", hook.TEMPLATE / "githooks/pre-commit"
    assert ours.read_bytes() == template.read_bytes()
    assert ours.stat().st_mode & 0o111 and template.stat().st_mode & 0o111


def _hook_in(shop: Path, tmp_path: Path, tools: dict[str, str]) -> subprocess.CompletedProcess:
    """The template's hook in a project without the engine, with stand-ins for uvx and crissp on PATH."""
    git(shop, "init", "-q")
    (shop / ".mcp.json").write_text(json.dumps({"mcpServers": {"crissp": {"command": "uvx",
                                                                           "args": ["crissp==1.2.3", "mcp"]}}}))
    bin_ = tmp_path / "bin"
    bin_.mkdir()
    (bin_ / "python3").symlink_to(sys.executable)
    for name, body in tools.items():
        (bin_ / name).write_text(f"#!/bin/sh\n{body}\n")
        (bin_ / name).chmod(0o755)
    return subprocess.run(["bash", str(hook.TEMPLATE / "githooks/pre-commit")], cwd=shop, capture_output=True,
                          text=True, check=False, env={**GIT_ENV, "HOME": str(shop), "PATH": f"{bin_}:/usr/bin:/bin"})


def test_a_project_s_hook_runs_the_crissp_that_mcp_json_pins(shop, tmp_path):
    done = _hook_in(shop, tmp_path, {"uvx": 'echo "uvx $*"; exit 3', "crissp": "echo never"})
    assert done.returncode == 3 and done.stdout == "uvx crissp==1.2.3 hook\n"


def test_without_uv_the_hook_runs_the_crissp_on_path(shop, tmp_path):
    done = _hook_in(shop, tmp_path, {"crissp": 'echo "crissp $*"'})
    assert done.returncode == 0 and done.stdout == "crissp hook\n"


def test_without_any_crissp_the_hook_stops_the_commit_and_says_how_to_go_on(shop, tmp_path):
    done = _hook_in(shop, tmp_path, {})
    assert done.returncode == 1 and "uvx crissp==1.2.3" in done.stderr and "git commit --no-verify" in done.stderr


def test_the_pinned_crissp_on_path_is_used_without_fetching(shop, tmp_path):
    pinned = '[ "$1" = --version ] && echo "crissp 1.2.3" || echo "crissp $*"'
    done = _hook_in(shop, tmp_path, {"uvx": "echo never", "crissp": pinned})
    assert done.returncode == 0 and done.stdout == "crissp hook\n"
