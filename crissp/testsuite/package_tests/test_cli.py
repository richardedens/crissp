"""The crissp command passes every option of a guard on to it untouched (crissp check --plan, crissp deploy --cluster,
crissp ux --shoot <walk>), for the project it is started in. Fast: the scripts are stood in, nothing is run."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from crissp import cli  # noqa: E402


@pytest.fixture
def ran(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli, "run_script", lambda root, name, argv, env: calls.append((root, name, argv)) or 0)
    monkeypatch.chdir(tmp_path)
    return calls


@pytest.mark.parametrize("argv, script, passed", [
    (["check", "--plan"], "check.sh", ["--plan"]),
    (["check"], "check.sh", []),
    (["check-all"], "check-all.sh", []),
    (["deploy", "--cluster-plan"], "deploy.sh", ["--cluster-plan"]),
    (["deploy", "--cluster"], "deploy.sh", ["--cluster"]),
    (["ux", "--shoot", "first-visit"], "ux.sh", ["--shoot", "first-visit"]),
    (["ux", "--propose", "first-visit", "the cart first"], "ux.sh", ["--propose", "first-visit", "the cart first"]),
])
def test_a_guards_options_pass_through(ran, argv, script, passed, tmp_path):
    assert cli.main(argv, env={}) == 0
    assert ran == [(tmp_path.resolve(), script, passed)]


def test_root_before_the_command_still_names_the_project(ran, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    assert cli.main(["--root", str(other), "check", "--plan"], env={}) == 0
    assert ran == [(other.resolve(), "check.sh", ["--plan"])]


def test_an_unknown_command_is_refused(ran, capsys):
    with pytest.raises(SystemExit):
        cli.main(["launch"], env={})
    assert ran == []


def test_the_engine_is_told_it_runs_as_the_crissp_command(tmp_path):
    """So the guards say `crissp check-all`, not a script path the project does not have (F-04)."""
    env = cli.engine_env(tmp_path, {"PATH": "/usr/bin"})
    assert env["CRISSP_COMMAND"] == "crissp" and env["CRISSP_ROOT"] == str(tmp_path)
    assert env["CRISSP_VERSION"] == cli.__version__  # F-20: repair moves the .mcp.json pin to this crissp


@pytest.mark.parametrize("argv, passed", [(["repair"], []), (["repair", "--yes"], ["--yes"]),
                                         (["repair", "\u2014yes"], ["--yes"]), (["repair", "\u2013yes"], ["--yes"])])
def test_repair_runs_the_engines_repair_for_the_project(monkeypatch, tmp_path, argv, passed):
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, cwd, env: calls.append((cmd, cwd, env["CRISSP_ROOT"]))
                        or type("Done", (), {"returncode": 1})())
    monkeypatch.chdir(tmp_path)
    assert cli.main(argv, env={}) == 1
    (cmd, cwd, root), = calls
    assert cmd[1:] == [str(cli.ENGINE / "testsuite" / "lib" / "repair.py"), *passed] and str(cwd) == root == str(tmp_path.resolve())


def test_a_dash_a_chat_or_word_processor_made_long_still_is_an_option(ran, tmp_path):
    """F-22: Teams, Outlook and Word turn -- into an em or en dash; crissp reads a leading one as --."""
    assert cli.main(["check", "—plan"], env={}) == 0
    assert cli.main(["ux", "–shoot", "first—visit"], env={}) == 0
    assert ran == [(tmp_path.resolve(), "check.sh", ["--plan"]), (tmp_path.resolve(), "ux.sh", ["--shoot", "first—visit"])]
