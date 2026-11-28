"""crissp lints its own Python (F-35): the pinned ruff, configured in pyproject.toml, runs as the `python-lint` step over src/,
crissp/ and site/, check.sh runs it for every change there, and CI runs it on every push and pull request."""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "crissp/testsuite/lib"))
import impact
import project

sys.path.insert(0, str(ROOT / "crissp/testsuite/lint"))
import python_lint as pl

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
    assert lint["run"] == "py crissp/testsuite/lint/python_lint.py"  # py: the pinned tools (lib/steps.sh)
    assert pl.LINTED == LINTED and pl.RUFF[:4] == ("-m", "ruff", "check", "--no-cache")


def test_every_change_to_linted_python_brings_the_lint_step():
    conf = _conf()
    for path in (
        "src/crissp/cli.py",
        "crissp/testsuite/lib/collect.py",
        "crissp/testsuite/tests/test_gate.py",
        "crissp/testsuite/package_tests/test_cli.py",
        "crissp/uxsuite/api.py",
        "crissp/tool/server.py",
        "crissp/deploy/tests/test_chart.py",
        "site/build.sh",
        "pyproject.toml",
    ):
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
    assert "RUF043" in lint.get("extend-select", []) or "RUF" in lint.get("select", [])


def test_the_standard_holds_bugs_security_and_dead_noqa_and_lives_in_pyproject_alone():
    """F-92: ruff's defaults alone (E4, E7, E9, F) let likely bugs (B), unsafe calls (S), a noqa that suppresses
    nothing (RUF100) and a module without a docstring through. The rules sit in pyproject.toml, never as step flags,
    so an editor or a hand-run ruff gives the step's answer; a shell stays forbidden (S602 is not ignored)."""
    lint = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    for family in ("E", "W", "F", "B", "S", "SIM", "I", "N", "UP", "C4", "RUF", "PLW1510", "D100"):
        assert family in lint["select"], family
    assert "S602" not in lint.get("ignore", []) and not {"S", "B", "RUF100"} & set(lint.get("ignore", []))
    assert "--select" not in _lint(_conf())["run"] and "--ignore" not in _lint(_conf())["run"]


# F-93: the engine runs on the standard library only, and holds no duplicate code. Before, the first was proven only by
# the wheel's empty dependency list (an import of a tool would have failed in a user's project, not here) and the
# second by nothing (F-26 removed two copied functions by hand).


def _engine(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def test_an_import_outside_the_standard_library_is_a_finding_by_file_and_line(tmp_path):
    root = _engine(
        tmp_path,
        {
            "src/crissp/cli.py": "import json\nimport crissp.x\nimport requests\n",
            "crissp/testsuite/lib/collect.py": "import measure\nfrom . import serve\nfrom yaml import safe_load\n",
            "crissp/testsuite/lib/measure.py": "def f():\n    import numpy.linalg\n",  # one inside a function counts too
            "crissp/testsuite/lib/tests/test_x.py": "import pytest\n",  # tests run with the pinned tools
            "crissp/testsuite/lib/pytest_plugin/p.py": "import pytest\n",
            "crissp/tool/server.py": "import urllib.request\n",
            "crissp/uxsuite/ux_shoot.py": "def run():\n    from playwright.sync_api import sync_playwright\n",
            "crissp/uxsuite/api.py": "import ux_shoot\nimport playwright\n",  # playwright: ux_shoot.py alone
        },
    )
    assert pl.foreign_imports(root) == [
        "crissp/testsuite/lib/collect.py:3: imports yaml, not the standard library",
        "crissp/testsuite/lib/measure.py:2: imports numpy, not the standard library",
        "crissp/uxsuite/api.py:2: imports playwright, not the standard library",
        "src/crissp/cli.py:3: imports requests, not the standard library",
    ]


def test_the_engine_itself_imports_the_standard_library_only():
    assert pl.foreign_imports(ROOT) == []


def _git(root: Path, *files: str) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "add", *files], cwd=root, check=True)


def test_pylint_compares_the_tracked_python_ruff_reads_and_skips_the_unsafe_rule_tests(tmp_path):
    root = _engine(
        tmp_path,
        {
            "src/a.py": "",
            "crissp/b.py": "",
            "site/c.py": "",
            "other/d.py": "",
            "crissp/e.txt": "",
            "crissp/testsuite/sast/tests/bad.py": "",
            "crissp/untracked.py": "",
        },
    )
    _git(root, "src", "crissp/b.py", "site", "other", "crissp/e.txt", "crissp/testsuite")
    assert sorted(pl.python_files(root)) == ["crissp/b.py", "site/c.py", "src/a.py"]


def _stand_in(monkeypatch, answers: dict[str, subprocess.CompletedProcess]) -> list[list[str]]:
    """subprocess.run stood in for ruff and pylint (no test runs or fetches a linter); git runs for real."""
    calls, real = [], subprocess.run

    def run(cmd, **kw):
        if cmd[0] == "git":
            return real(cmd, **kw)
        calls.append(cmd)
        name = "pylint" if "pylint" in cmd else "ruff format" if "format" in cmd else "ruff"
        return answers.get(name) or subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(pl.subprocess, "run", run)
    return calls


def test_duplicate_code_runs_the_pinned_pylint_with_pyprojects_settings(tmp_path, monkeypatch):
    root = _engine(tmp_path, {"src/a.py": "", "crissp/b.py": ""})
    _git(root, "src", "crissp")
    monkeypatch.setattr(pl.shutil, "which", lambda name: "/bin/uv")
    found = subprocess.CompletedProcess([], 8, "crissp/b.py:1:0: R0801: Similar lines in 2 files\n", "")
    calls = _stand_in(monkeypatch, {"pylint": found})
    assert pl.duplicates(root) == ["pylint: crissp/b.py:1:0: R0801: Similar lines in 2 files"]
    assert calls[0][:5] == ["/bin/uv", "run", "--quiet", "--no-project", "--with-requirements"]
    assert calls[0][5] == str(ROOT / "crissp/testsuite/lint/requirements.txt")
    assert calls[0][6:] == ["pylint", "--rcfile=pyproject.toml", "crissp/b.py", "src/a.py"]
    pinned = (ROOT / "crissp/testsuite/lint/requirements.txt").read_text()
    assert re.search(r"^pylint==\S+$", pinned, re.MULTILINE), "pylint is pinned, dev-only, next to shellcheck"
    pylint = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["pylint"]
    assert pylint["messages control"] == {"disable": ["all"], "enable": ["duplicate-code"]}
    assert pylint["similarities"]["min-similarity-lines"] == 6


def test_without_uv_the_duplicate_check_is_a_finding_never_a_silent_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(pl.shutil, "which", lambda name: None)
    assert pl.duplicates(tmp_path) == [
        "pylint: uv is not installed: the duplicate-code check cannot run (https://docs.astral.sh/uv/)"
    ]


def test_a_tool_that_fails_without_saying_why_still_fails(tmp_path, monkeypatch):
    _stand_in(monkeypatch, {"ruff": subprocess.CompletedProcess([], 2, "", "  \n")})
    assert pl.tool("ruff", ["ruff"], tmp_path) == ["ruff: exit 2"]


def test_the_step_is_clean_or_names_every_finding(tmp_path, monkeypatch, capsys):
    root = _engine(tmp_path, {"crissp/tool/server.py": "import json\n"})
    _git(root, "crissp")
    monkeypatch.setattr(pl.shutil, "which", lambda name: "/bin/uv")
    calls = _stand_in(monkeypatch, {})
    assert pl.main({"CRISSP_ROOT": str(root)}) == 0
    assert "python-lint: clean" in capsys.readouterr().out
    assert calls[0] == [sys.executable, "-m", "ruff", "check", "--no-cache", "--quiet", "src", "crissp", "site"]
    assert calls[1] == [sys.executable, "-m", "ruff", "format", "--check", "--no-cache", "src", "crissp", "site"]
    (root / "crissp/tool/server.py").write_text("import requests\n")
    _stand_in(monkeypatch, {"ruff": subprocess.CompletedProcess([], 1, "crissp/tool/server.py:1:1: F401 unused\n", "")})
    monkeypatch.chdir(root)
    assert pl.main({}) == 1
    assert capsys.readouterr().out.splitlines() == [
        "python-lint: 2 finding(s):",
        "  ruff: crissp/tool/server.py:1:1: F401 unused",
        "  crissp/tool/server.py:1: imports requests, not the standard library",
    ]


def test_a_change_to_the_lint_tools_runs_their_tests_and_the_python_lint():
    kind, steps = impact.classify("crissp/testsuite/lint/python_lint.py", _conf())
    assert kind == "suites" and {"tools", "python-lint", "sast"} <= set(steps)
    assert "python-lint" in impact.classify("crissp/testsuite/lint/requirements.txt", _conf())[1]  # pylint's pin
    tools = next(s for s in _conf()["steps"] if s["key"] == "tools")
    assert "crissp/testsuite/lint" in tools["sources"]  # held at 100% lines and branches with the rest


def test_an_editor_writes_files_the_way_the_checks_hold_them():
    """F-95: no .editorconfig, so an editor wrote crissp's files with its own defaults (tabs, CRLF, no final newline,
    4-space JSON) and the lint said so only afterwards. It says UTF-8, LF and a final newline everywhere, 4 spaces for
    Python and ruff's line length, crissp's own JSON layout, and costs a run nothing (a note)."""
    import configparser

    conf = configparser.ConfigParser()
    conf.read_string("[top]\n" + (ROOT / ".editorconfig").read_text())
    assert conf["top"]["root"] == "true"
    every = conf["*"]
    assert (every["charset"], every["end_of_line"], every["insert_final_newline"]) == ("utf-8", "lf", "true")
    assert every["indent_style"] == "space" and every["trim_trailing_whitespace"] == "true"
    ruff = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]
    assert int(every["max_line_length"]) == ruff["line-length"] and conf["*.py"]["indent_size"] == "4"
    assert conf["*.json"]["indent_size"] == "1" and conf["*.md"]["trim_trailing_whitespace"] == "false"
    assert impact.classify(".editorconfig", _conf()) == ("nothing", "")


def test_the_python_has_one_layout_checked_and_blame_skips_the_layout_commit():
    """F-97: crissp's Python had no layout standard (each file as its author typed it, lines up to 300 long). It was
    formatted once with ruff format; the step checks the layout (ruff format --check) and the line length (E501, 130 for
    a docstring or message), and git blame skips the layout commit (.git-blame-ignore-revs, GitHub reads it too)."""
    lint = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["ruff"]["lint"]
    assert "E501" not in lint.get("ignore", []) and lint["pycodestyle"]["max-line-length"] == 130
    assert pl.FORMAT == ("-m", "ruff", "format", "--check", "--no-cache")
    revs = [line for line in (ROOT / ".git-blame-ignore-revs").read_text().splitlines() if line and line[0] != "#"]
    assert revs and all(re.fullmatch(r"[0-9a-f]{40}", r) for r in revs)
    for rev in revs:
        subject = subprocess.run(
            ["git", "log", "-1", "--format=%s", rev], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout
        assert subject in ("", "F-97: ruff format, once, over crissp's own Python (layout only)\n"), rev  # "": shallow
