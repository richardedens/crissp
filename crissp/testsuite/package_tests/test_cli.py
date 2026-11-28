"""The crissp command passes every option of a guard on to it untouched (crissp check --plan, crissp deploy --cluster,
crissp ux --shoot <walk>), for the project it is started in. Fast: the scripts are stood in, nothing is run."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from crissp import cli


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
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, cwd, env, check: calls.append((cmd, cwd, env["CRISSP_ROOT"], check))
                        or type("Done", (), {"returncode": 1})())
    monkeypatch.chdir(tmp_path)
    assert cli.main(argv, env={}) == 1
    (cmd, cwd, root, check), = calls
    assert check is False  # its exit code is the answer, not an exception
    assert cmd[1:] == [str(cli.ENGINE / "testsuite" / "lib" / "repair.py"), *passed] and str(cwd) == root == str(tmp_path.resolve())


def test_init_onboards_vibe_when_a_vibe_home_exists(tmp_path, monkeypatch):
    """F-24 / E5-F1-01: init writes .vibe/config.toml (pinning this crissp) and trusts the folder in VIBE_HOME."""
    project = tmp_path / "proj"
    project.mkdir()
    vibe = tmp_path / "vibe-home"
    vibe.mkdir()
    monkeypatch.chdir(project)
    env = {"VIBE_HOME": str(vibe)}
    assert cli.main(["init", "--yes", "--no-git", "--product", "Example"], env=env) == 0
    config = (project / ".vibe" / "config.toml").read_text()
    assert 'name = "crissp"' in config and "uvx" in config and f"crissp=={cli.__version__}" in config
    db = (vibe / "trusted_folders.toml").read_text()
    assert "trusted = [" in db and f'"{project.resolve()}"' in db
    # a second init keeps the project's own config and never duplicates the trust entry
    (project / ".vibe" / "config.toml").write_text("# ours\n")
    assert cli.main(["init", "--yes", "--no-git"], env=env) == 0
    assert (project / ".vibe" / "config.toml").read_text() == "# ours\n"
    assert (vibe / "trusted_folders.toml").read_text().count(f'"{project.resolve()}"') == 1


def test_init_writes_the_vibe_config_and_says_so_when_vibe_is_not_installed(tmp_path, monkeypatch, capsys):
    """F-24: no Vibe home (VIBE_HOME or ~/.vibe missing): the config is still written, the skip is said."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    missing = tmp_path / "no-vibe-home"
    assert cli.main(["init", "--yes", "--no-git"], env={"VIBE_HOME": str(missing)}) == 0
    assert (project / ".vibe" / "config.toml").is_file()
    assert not missing.exists()
    assert "Vibe" in capsys.readouterr().out


def test_init_detects_the_system_and_whether_vibe_is_installed(tmp_path, monkeypatch, capsys):
    """F-25 / E5-F1-02: one line says the system, whether vibe was found, and what the onboarding did."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    home = tmp_path / "vibe-home"
    home.mkdir()
    monkeypatch.setattr(cli.shutil, "which", lambda name: f"/usr/bin/{name}" if name == "vibe" else None)
    env = {"VIBE_HOME": str(home)}
    assert cli.main(["init", "--yes", "--no-git"], env=env) == 0
    out = capsys.readouterr().out
    assert f"Vibe on {cli.system()}" in out and "trusted" in out
    assert f'"{project.resolve()}"' in (home / "trusted_folders.toml").read_text()
    # vibe on PATH but never run (no Vibe home yet): said, not trusted
    env = {"VIBE_HOME": str(tmp_path / "no-home")}
    assert cli.main(["init", "--yes", "--no-git"], env=env) == 0
    out = capsys.readouterr().out
    assert "start vibe once" in out and not (tmp_path / "no-home").exists()
    # no vibe at all
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert cli.main(["init", "--yes", "--no-git"], env=env) == 0
    assert "not installed" in capsys.readouterr().out


def test_system_names_each_platform(monkeypatch):
    """F-25: Windows, macOS and Linux each name themselves."""
    monkeypatch.setattr(cli.os, "name", "nt")
    monkeypatch.setattr(cli.sys, "platform", "win32")
    assert cli.system() == "Windows"
    monkeypatch.setattr(cli.os, "name", "posix")
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert cli.system() == "macOS"
    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert cli.system() == "Linux"


def test_init_trusts_through_the_engines_vibe_module(tmp_path, monkeypatch):
    """F-26: init and repair share one trust function (the engine's lib/vibe.py), so a Windows path is added once
    and a one-line list stays valid TOML from init too."""
    assert Path(cli.vibe.__file__) == cli.ENGINE / "testsuite" / "lib" / "vibe.py"
    home = tmp_path / "vibe-home"
    home.mkdir()
    (home / "trusted_folders.toml").write_text('trusted = ["/a"]\n')
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    for _ in range(2):
        assert cli.main(["init", "--yes", "--no-git"], env={"VIBE_HOME": str(home)}) == 0
    assert tomllib.loads((home / "trusted_folders.toml").read_text()) == {
        "trusted": ["/a", str(project.resolve())], "untrusted": []}


def test_init_asks_before_trusting_the_folder_in_vibe(tmp_path, capsys):
    """F-28: trusting is the decision Vibe's own prompt is for: without --yes init asks (no: nothing in Vibe's file,
    and it says how to trust later), and when it trusts it says how to undo it."""
    home = tmp_path / "vibe-home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    args = cli.parser().parse_args(["init", "--no-git"])
    asked = []
    answers = iter(["y", "n"])
    assert cli.init(project, args, {"VIBE_HOME": str(home)}, ask=lambda q: asked.append(q) or next(answers)) == 0
    assert "Trust" in asked[1] and str(home / "trusted_folders.toml") in asked[1]
    assert not (home / "trusted_folders.toml").exists()
    assert "not trusted" in capsys.readouterr().out
    answers = iter(["y", ""])  # Enter says yes
    assert cli.init(project, args, {"VIBE_HOME": str(home)}, ask=lambda q: next(answers)) == 0
    assert str(project) in (home / "trusted_folders.toml").read_text() and "to undo" in capsys.readouterr().out
    answers = iter(["y"])  # already trusted: not asked again
    assert cli.init(project, args, {"VIBE_HOME": str(home)}, ask=lambda q: next(answers)) == 0
    assert "already trusts" in capsys.readouterr().out


def test_the_vibe_config_names_this_folder_and_stays_out_of_git(tmp_path, monkeypatch):
    """F-100 (was F-29): .vibe/config.toml names this machine's folder (cwd, CRISSP_ROOT) and uvx by its full path,
    so Vibe's desktop app finds the server and the project; it is no file to share, so all of .vibe/ stays out of
    git and each clone's crissp repair --yes writes its own."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes"], env={"VIBE_HOME": str(tmp_path / "no-home")}) == 0
    (project / ".vibe" / "cache.json").write_text("{}")
    server = tomllib.loads((project / ".vibe" / "config.toml").read_text())["mcp_servers"][0]
    assert server["cwd"] == str(project.resolve()) and server["env"] == {"CRISSP_ROOT": str(project.resolve())}
    assert server["args"] == [f"crissp=={cli.__version__}", "mcp"]

    def ignored(rel: str) -> bool:
        return subprocess.run(["git", "-C", str(project), "check-ignore", "-q", rel], check=False).returncode == 0
    assert ignored(".vibe/config.toml") and ignored(".vibe/cache.json")


def test_init_on_windows_says_the_guards_run_in_wsl(tmp_path, monkeypatch, capsys):
    """F-25 / F-14: on native Windows init says the system, that the bash guards run inside WSL 2, and still
    onboards Vibe."""
    monkeypatch.setattr(cli, "system", lambda: "Windows")
    monkeypatch.setattr(cli, "windows", lambda: True)
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes", "--no-git"], env={"VIBE_HOME": str(tmp_path / "no-home")}) == 0
    out = capsys.readouterr().out
    assert "Vibe on Windows" in out and "WSL 2" in out


def test_a_dash_a_chat_or_word_processor_made_long_still_is_an_option(ran, tmp_path):
    """F-22: Teams, Outlook and Word turn -- into an em or en dash; crissp reads a leading one as --."""
    assert cli.main(["check", "—plan"], env={}) == 0
    assert cli.main(["ux", "–shoot", "first—visit"], env={}) == 0
    assert ran == [(tmp_path.resolve(), "check.sh", ["--plan"]), (tmp_path.resolve(), "ux.sh", ["--shoot", "first—visit"])]


def test_init_makes_the_lint_hook_and_turns_it_on(tmp_path, monkeypatch, capsys):
    """F-50: init writes .githooks/pre-commit (executable) and sets core.hooksPath, so git lints before every commit."""
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes"], env={"VIBE_HOME": str(tmp_path / "no-home")}) == 0
    hook = project / ".githooks" / "pre-commit"
    assert hook.read_bytes() == (cli.TEMPLATE / "githooks" / "pre-commit").read_bytes() and hook.stat().st_mode & 0o111
    path = subprocess.run(["git", "-C", str(project), "config", "core.hooksPath"], capture_output=True, text=True,
                          check=False).stdout.strip()
    assert path == ".githooks" and "git hook: on" in capsys.readouterr().out


def test_init_never_switches_off_hooks_a_repository_already_has(tmp_path, monkeypatch, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / ".git" / "hooks" / "pre-commit").write_text("#!/bin/sh\n")
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes"], env={"VIBE_HOME": str(tmp_path / "no-home")}) == 0
    path = subprocess.run(["git", "-C", str(project), "config", "core.hooksPath"], capture_output=True, text=True,
                          check=False).stdout.strip()
    assert path == "" and "switch them off" in capsys.readouterr().out
    assert (project / ".githooks" / "pre-commit").is_file()  # made, for when they move their hooks there


def test_init_without_git_makes_the_hook_file_only(tmp_path, monkeypatch, capsys):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.chdir(project)
    assert cli.main(["init", "--yes", "--no-git"], env={"VIBE_HOME": str(tmp_path / "no-home")}) == 0
    assert (project / ".githooks" / "pre-commit").is_file() and "git hook: no git repository" in capsys.readouterr().out


def test_hook_runs_the_engines_hook_for_the_project(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd, cwd, env, check: calls.append((cmd, cwd, env["CRISSP_ROOT"]))
                        or type("Done", (), {"returncode": 1})())
    monkeypatch.chdir(tmp_path)
    assert cli.main(["hook"], env={}) == 1
    (cmd, cwd, root), = calls
    assert cmd[1:] == [str(cli.ENGINE / "testsuite" / "lib" / "hook.py")] and str(cwd) == root == str(tmp_path.resolve())
