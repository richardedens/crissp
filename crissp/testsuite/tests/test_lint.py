"""F-38: this repository lints its own plain JavaScript (ESLint) and its bash scripts (shellcheck), as the `lint` step.

The lint tools are this repository's, dev-only: pinned in crissp/testsuite/lint/ and never in the wheel. These tests
prove the wiring (every file is linted, every change to one runs the step, CI runs it); the step itself proves the
files are clean. They never install or run a linter.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
LIB = REPO / "crissp" / "testsuite" / "lib"
LINT = REPO / "crissp" / "testsuite" / "lint"
sys.path.insert(0, str(LIB))
import impact
import project


def tracked() -> list[str]:
    return subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True).stdout.split()


def shell_scripts() -> list[str]:
    """Every tracked bash script: a bash/sh shebang, or a .sh file (lib/steps.sh is sourced, it has none)."""
    out = []
    for f in tracked():
        path = REPO / f
        if not path.is_file():
            continue
        first = path.read_bytes().split(b"\n", 1)[0]
        if f.endswith(".sh") or (first.startswith(b"#!") and (b"bash" in first or first.rstrip().endswith(b"/sh"))):
            out.append(f)
    return sorted(out)


def javascript() -> list[str]:
    return sorted(f for f in tracked() if f.endswith((".js", ".mjs")) and not f.startswith("crissp/testsuite/lint/"))


def listed(kind: str) -> list[str]:
    run = subprocess.run(
        ["bash", str(LINT / "lint.sh"), "--list", kind],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin", "CRISSP_ROOT": str(REPO)},
    )
    assert run.returncode == 0, run.stderr
    return sorted(run.stdout.split())


def test_this_repository_has_a_lint_step_with_its_own_dev_only_tools():
    conf = project.load(REPO)
    lint = next(s for s in conf["steps"] if s["key"] == "lint")
    assert lint["run"] == "crissp/testsuite/lint/lint.sh" and not lint["full_only"] and lint["tests"] == []
    package = json.loads((LINT / "package.json").read_text())
    assert package["private"] is True
    assert set(package["devDependencies"]) == {
        "eslint",
        "@eslint/js",
        "globals",
        "stylelint",
        "stylelint-config-recommended",
    }
    assert all(v[0].isdigit() for v in package["devDependencies"].values()), "pinned, exact versions"
    assert (LINT / "package-lock.json").is_file() and (LINT / "eslint.config.js").is_file()
    assert [
        line for line in (LINT / "requirements.txt").read_text().splitlines() if line and not line.startswith("#")
    ] and all(
        "==" in line
        for line in (LINT / "requirements.txt").read_text().splitlines()
        if line and not line.startswith("#")
    )


def test_the_lint_tools_are_never_in_the_wheel_and_their_versions_are_audited():
    wheel = (REPO / "pyproject.toml").read_text().split("[tool.hatch.build.targets.wheel]", 1)[1].split("\n[", 1)[0]
    assert "crissp/testsuite/lint" not in wheel and '"crissp/testsuite"' not in wheel
    audit = project.load(REPO)["audit"]
    assert "crissp/testsuite/lint/requirements.txt" in audit["pip"] and "crissp/testsuite/lint" in audit["npm"]


def test_the_step_lints_every_bash_script_and_every_javascript_file_of_this_repository():
    assert shell_scripts() and listed("shell") == shell_scripts()
    assert javascript() and listed("js") == javascript()


def test_a_change_to_a_linted_file_runs_the_lint_step():
    conf = project.load(REPO)
    for f in (
        shell_scripts()
        + javascript()
        + ["crissp/testsuite/lint/eslint.config.js", "crissp/testsuite/lint/package-lock.json"]
    ):
        kind, detail = impact.classify(f, conf)
        assert kind == "full" or (kind == "suites" and "lint" in detail), (f, kind, detail)
    # every part's change is also scanned for secrets, and its code for unsafe code (F-43, F-44)
    assert impact.classify("crissp/testsuite/dashboard/app.js", conf) == (
        "suites",
        ("tools", "lint", "secrets", "sast"),
    )
    assert impact.classify("crissp/testsuite/lint/eslint.config.js", conf) == ("suites", ("lint", "secrets"))
    assert impact.classify("crissp/testsuite/lib/collect.py", conf) == (
        "suites",
        ("tools", "python-lint", "secrets", "sast"),
    )


def test_ci_sets_up_node_and_runs_the_lint_step():
    ci = (REPO / ".github" / "workflows" / "ci.yml").read_text()
    assert "actions/setup-node@" in ci
    run = next(line for line in ci.splitlines() if "crissp/testsuite/run.sh --quick" in line)
    assert "lint" in run.split("--quick", 1)[1].split()


def test_the_lint_script_says_how_to_use_it():
    run = subprocess.run(
        ["bash", str(LINT / "lint.sh"), "--list", "nonsense"], cwd=REPO, capture_output=True, text=True, check=False
    )
    assert run.returncode == 2 and "usage" in run.stderr


def css() -> list[str]:
    return sorted(f for f in tracked() if f.endswith(".css"))


def test_the_step_lints_every_css_file_of_this_repository_with_stylelint():
    """F-96: ESLint read crissp's JavaScript, but nothing read its CSS (the look, the dashboard, the session pages, the
    UX suite, the website): a deprecated `word-break: break-word` sat in the dashboard's stylesheet three times."""
    assert css() and listed("css") == css()
    config = (LINT / "stylelint.config.mjs").read_text()
    assert '"stylelint-config-recommended"' in config  # likely mistakes; the layout stays as written
    lock = json.loads((LINT / "package-lock.json").read_text())["packages"]
    assert (
        lock["node_modules/stylelint"]["version"]
        == json.loads((LINT / "package.json").read_text())["devDependencies"]["stylelint"]
    )
    script = (LINT / "lint.sh").read_text()
    assert "== stylelint (every CSS file)" in script and 'bad "stylelint"' in script
    conf = project.load(REPO)
    for f in [*css(), "crissp/testsuite/lint/stylelint.config.mjs"]:
        kind, detail = impact.classify(f, conf)
        assert kind == "suites" and "lint" in detail, (f, kind, detail)
    assert "break-word" not in (REPO / "crissp/testsuite/dashboard/style.css").read_text()
