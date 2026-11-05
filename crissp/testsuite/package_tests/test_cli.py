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
