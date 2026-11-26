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
    assert ".vibe/" in (project / ".gitignore").read_text().splitlines()
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


def test_windows_paths_land_as_valid_toml_and_match_vibes_own_entry(tmp_path):
    """F-25: a Windows path (backslashes) is written as valid TOML, and Vibe's own forward-slash entry in
    trusted_folders.toml counts as already trusted, so it is not duplicated."""
    home = tmp_path / "vibe-home"
    home.mkdir()
    win = Path("C:\\Users\\x\\proj")
    assert cli.toml_str(win) == '"C:\\\\Users\\\\x\\\\proj"'
    (home / "trusted_folders.toml").write_text('trusted = [\n    "C:/Users/x/proj",\n]\nuntrusted = []\n')
    assert "already trusts" in cli.trust_vibe(win, {"VIBE_HOME": str(home)})
    (home / "trusted_folders.toml").write_text("trusted = []\n")
    assert "trusted" in cli.trust_vibe(win, {"VIBE_HOME": str(home)})
    assert (home / "trusted_folders.toml").read_text() == 'trusted = [\n    "C:\\\\Users\\\\x\\\\proj",\n]\n'


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
