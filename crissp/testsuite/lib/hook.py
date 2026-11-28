"""The lint before every commit (F-50): git runs .githooks/pre-commit, which runs this for the project.

    crissp hook                              what .githooks/pre-commit calls (the project's pinned crissp)
    python3 crissp/testsuite/lib/hook.py     the same, in the framework's own checkout

It runs the project's lint steps (crissp/testsuite/suites.json): the step `lint` and every step whose key ends in
`-lint` (backend-lint, frontend-lint, python-lint …) that is there now (`when`), each in its folder with lib/steps.sh
and the pinned tools at hand, as a run does. It writes no results: the checks still run every step. A red lint stops
the commit; `git commit --no-verify` skips the hook once.

The hook is on when the repository's core.hooksPath is .githooks. crissp init and crissp repair set it (turn_on), but
only where it switches nothing off: not over a core.hooksPath of the project's own, nor over hooks in .git/hooks.
"""

import os
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402

TEMPLATE = ENGINE.parents[1] / "template"  # .githooks/pre-commit is the template's githooks/pre-commit
TOOLS = ENGINE.parent / "requirements.txt"
HELPERS = ENGINE / "steps.sh"
HOOKS = ".githooks"


def is_lint(key: str) -> bool:
    return key == "lint" or key.endswith("-lint")


def lint_steps(root: Path) -> list[dict]:
    return [s for s in project.steps(project.load(root), root) if is_lint(s["key"])]


def run(root: Path, env: dict, runner=subprocess.run) -> int:
    """Each lint step, its output straight to the terminal; 1 when one is red or the configuration is broken."""
    try:
        steps = lint_steps(root)
    except project.ConfigError as e:
        print(f"crissp hook: {e}")
        return 1
    if not steps:
        print("crissp hook: no lint steps in crissp/testsuite/suites.json (lint, *-lint): nothing to lint.")
        return 0
    red = []
    for step in steps:
        done = runner(
            ["bash", "-c", step["run"]],
            cwd=root / step["dir"],
            check=False,
            env={**env, "CRISSP_ROOT": str(root), "STEP": step["key"], "TOOLS": str(TOOLS), "BASH_ENV": str(HELPERS)},
        )
        status = "passed" if done.returncode == 0 else "failed"
        print(f"crissp hook: {step['label']} {status}")
        if status == "failed":
            red.append(step["label"])
    if red:
        print(
            f"crissp hook: not committed, the lint is red ({', '.join(red)}). Fix it, or commit once without it: "
            "git commit --no-verify (crissp check and CI still run it)."
        )
        return 1
    return 0


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, check=False)
    except OSError:  # no git at all
        return None


def state(root: Path) -> str:
    """no-git | on | other (core.hooksPath of its own) | local-hooks (.git/hooks has hooks) | off."""
    inside = _git(root, "rev-parse", "--git-dir")
    if inside is None or inside.returncode != 0:
        return "no-git"
    path = _git(root, "config", "--get", "core.hooksPath").stdout.strip()
    if path:
        return "on" if path.rstrip("/") == HOOKS else "other"
    hooks = (root / inside.stdout.strip()) / "hooks"
    if hooks.is_dir() and any(p.is_file() and p.suffix != ".sample" for p in hooks.iterdir()):
        return "local-hooks"
    return "off"


def hooks_path(root: Path) -> str:
    return _git(root, "config", "--get", "core.hooksPath").stdout.strip()


def turn_on(root: Path) -> None:
    _git(root, "config", "core.hooksPath", HOOKS)


def needs(root: Path) -> str:
    """What a person has to do for the hook to run, or "" (said by init and repair, never done)."""
    now = state(root)
    if now == "other":
        return (
            f"core.hooksPath is {hooks_path(root)}: crissp's lint hook ({HOOKS}/pre-commit) does not run; call it "
            f"from your own pre-commit, or set core.hooksPath {HOOKS}"
        )
    if now == "local-hooks":
        return (
            f".git/hooks has hooks of its own: core.hooksPath {HOOKS} would switch them off; move them to "
            f"{HOOKS}/, then crissp repair --yes turns the lint hook on"
        )
    return ""


def main(argv: list[str], env: dict) -> int:
    if argv:
        print("usage: crissp hook   (git runs it before every commit: .githooks/pre-commit)")
        return 2
    return run(Path(env.get("CRISSP_ROOT") or os.getcwd()).resolve(), env)


if __name__ == "__main__":  # pragma: no cover — run by .githooks/pre-commit (crissp hook); main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
