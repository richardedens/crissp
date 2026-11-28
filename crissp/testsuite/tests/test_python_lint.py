"""crissp lints its own Python (F-35): the pinned ruff, configured in pyproject.toml, runs as the `python-lint` step over src/,
crissp/ and site/, check.sh runs it for every change there, and CI runs it on every push and pull request."""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "crissp/testsuite/lib"))
import impact  # noqa: E402
import project  # noqa: E402

LINTED = ("src", "crissp", "site")


def _conf() -> dict:
    return project.load(ROOT)


def _lint(conf: dict) -> dict:
    return next(s for s in conf["steps"] if s["key"] == "python-lint")


def test_ruff_is_configured_in_pyproject_for_the_python_crissp_supports():
    ruff = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]
    assert ruff["target-version"] == "py312" and ruff["line-length"] == 120
    assert "lint" in ruff


def test_the_lint_step_runs_the_pinned_ruff_over_src_crissp_and_site():
    pinned = re.search(r"^ruff==\S+$", (ROOT / "crissp/testsuite/requirements.txt").read_text(), re.MULTILINE)
    assert pinned, "ruff is pinned with the other test tools"
    lint = _lint(_conf())
    assert lint["dir"] == "." and not lint["gate"] and not lint["full_only"]
    assert lint["run"] == "py -m ruff check --no-cache " + " ".join(LINTED)  # py: the pinned tools (lib/steps.sh)


def test_every_change_to_linted_python_brings_the_lint_step():
    conf = _conf()
    for path in ("src/crissp/cli.py", "crissp/testsuite/lib/collect.py", "crissp/testsuite/tests/test_gate.py",
                 "crissp/testsuite/package_tests/test_cli.py", "crissp/uxsuite/api.py", "crissp/tool/server.py",
                 "crissp/deploy/tests/test_chart.py", "site/build.sh", "pyproject.toml"):
        kind, steps = impact.classify(path, conf)
        assert kind == "suites" and "python-lint" in steps, path
    assert impact.classify("crissp/backlog/FINDINGS.md", conf) == ("nothing", "")  # notes still need nothing


def test_ci_runs_the_lint_step():
    workflow = (ROOT / ".github/workflows/ci.yml").read_text()
    run = next(line for line in workflow.splitlines() if "crissp/testsuite/run.sh" in line)
    assert "python-lint" in run.split("run.sh", 1)[1].split()


def test_a_pytest_raises_match_with_regex_signs_is_escaped_or_raw():
    """F-90: `match=` is a regular expression. `match="cannot hold a |"` matched every message (an empty alternative),
    so the test it was in could not fail. ruff's RUF043 refuses such a pattern unless it is escaped or raw."""
    lint = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    assert "RUF043" in lint.get("extend-select", []) + lint.get("select", [])
