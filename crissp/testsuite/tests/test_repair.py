"""crissp repair (F-10, D-02): what a project brought in before the default layout has out of place is shown, and put
in place only with --yes; it never deletes, never overwrites, never touches the backlog and never commits."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import repair  # noqa: E402

OLD_STEPS = [
    {"key": "unit", "label": "Unit tests", "dir": ".", "run": "covered tests", "gate": True, "sources": ["src"]},
    {"key": "lint", "label": "Lint", "dir": ".", "run": "py -m ruff check --no-cache .", "seconds": 3}]
OLD_AGREEMENT = ("ask the crissp tools (`brief`, `backlog`; `crissp/tool`, registered\nin `.mcp.json`) instead of reading "
                 "the backlog files")


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def keys(root: Path) -> list[str]:
    return [r.key for r in repair.find(root)]


def bring_in(root: Path) -> None:
    """Everything crissp init makes in crissp/ (filled in), the framework's text and its ignore rules."""
    for src in (repair.TEMPLATE / "crissp").rglob("*"):
        if src.is_file():
            write(root / "crissp" / src.relative_to(repair.TEMPLATE / "crissp"), src.read_text().replace("{{PRODUCT}}", "x"))
    write(root / "crissp/CRISSP.md", (repair.ENGINE / "CRISSP.md").read_text())
    write(root / ".gitignore", (repair.TEMPLATE / "gitignore.crissp").read_text())


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.org", "GIT_COMMITTER_NAME": "t",
                        "GIT_COMMITTER_EMAIL": "t@example.org", "HOME": str(root), "PATH": "/usr/bin:/bin"})


@pytest.fixture
def old(tmp_path) -> Path:
    """A project as the template made it before D-02, with what a first session then did."""
    root = tmp_path / "shop"
    write(root / "crissp/testsuite/suites.json", json.dumps(
        {"product": "shop", "steps": OLD_STEPS, "paths": [{"match": "src/", "steps": ["unit", "lint"]},
                                                          {"match": "tests/", "steps": ["unit"]},
                                                          {"match": "docs/api/", "steps": ["lint"]}],
         "shared": [{"match": "*/Dockerfile", "why": "what goes into an image"}], "notes": ["notes/"]}))
    write(root / "crissp/uxsuite/team.json", json.dumps({"product": "shop", "url": "http://127.0.0.1:5173"}))
    write(root / "crissp/uxsuite/walks/first-visit.json", "{}")
    write(root / "crissp/uxsuite/prototype/index.html", "<!doctype html>")
    write(root / "crissp/uxsuite/notes.txt", "ideas")
    write(root / "crissp/deploy/deploy.json", json.dumps({"compose": {"url": "http://127.0.0.1:{port}",
                                                                      "port": {"setting": "APP_PORT", "default": 9090}}}))
    write(root / "crissp/CLAUDE.md", f"# shop\n\nWhere the work stands: {OLD_AGREEMENT}.\n")
    write(root / "crissp/backlog/FINDINGS.md", "| F-01 | here | kept as it is | E1 |\n")
    return root


def test_it_shows_what_is_out_of_place_and_changes_nothing_without_yes(old, capsys):
    before = {p: p.read_bytes() for p in old.rglob("*") if p.is_file()}
    assert repair.main([], {"CRISSP_ROOT": str(old)}) == 1
    out = capsys.readouterr().out
    assert {p: p.read_bytes() for p in old.rglob("*") if p.is_file()} == before
    for key in ("steps", "ux-url", "ux-extra", "agreement"):
        assert f"  {key} " in out, key
    assert "crissp/uxsuite/prototype → docs/ux/prototype" in out and "crissp/uxsuite/notes.txt → docs/ux/notes.txt" in out
    assert "http://127.0.0.1:5173 → http://127.0.0.1:9090" in out
    assert "Needs you:" in out and "no commit yet" in out and "no docker-compose.yml" in out
    assert out.rstrip().endswith("crissp repair --yes puts them in place. Nothing is committed.")


def test_yes_puts_everything_in_place_and_keeps_what_the_project_wrote(old, capsys):
    assert repair.main(["--yes"], {"CRISSP_ROOT": str(old)}) == 0
    out = capsys.readouterr().out
    assert "Repaired 8" in out and "Review the diff and commit when you are happy." in out
    conf = json.loads((old / "crissp/testsuite/suites.json").read_text())
    template = json.loads((repair.TEMPLATE / "crissp/testsuite/suites.json").read_text())
    assert conf["steps"] == template["steps"]
    assert [r["match"] for r in conf["paths"]] == ["app/backend/", "app/frontend/", "docs/api/"]  # its own rule kept
    assert conf["shared"][0]["match"] == "*/Dockerfile" and "docker-compose.yml" in [
        r["match"] for r in conf["shared"]]  # its own shared ground first, the template's added once
    assert conf["product"] == "shop" and conf["notes"] == ["notes/"]
    assert json.loads((old / "crissp/uxsuite/team.json").read_text()) == {"product": "shop", "url": "http://127.0.0.1:9090"}
    assert (old / "docs/ux/prototype/index.html").read_text() == "<!doctype html>"
    assert (old / "docs/ux/notes.txt").read_text() == "ideas" and not (old / "crissp/uxsuite/prototype").exists()
    assert (old / "crissp/uxsuite/walks/first-visit.json").is_file()  # its configuration stays
    agreement = (old / "crissp/CLAUDE.md").read_text()
    assert "`crissp/tool`" not in agreement and "the crissp MCP server, registered\nin `.mcp.json`" in agreement
    assert repair.SESSIONS in agreement  # F-21: both repairs of the agreement land, the tool's first
    assert (old / "crissp/backlog/FINDINGS.md").read_text() == "| F-01 | here | kept as it is | E1 |\n"
    # the crissp/ folder: what the template has and it lacked is made, filled in; the framework's text is this crissp's
    assert (old / "crissp/uxsuite/.gitignore").read_text() == (repair.TEMPLATE / "crissp/uxsuite/.gitignore").read_text()
    assert "{{PRODUCT}}" not in (old / "crissp/uxsuite/README.md").read_text()
    assert "shop" in (old / "crissp/uxsuite/README.md").read_text()
    assert (old / "crissp/CRISSP.md").read_text() == (repair.ENGINE / "CRISSP.md").read_text()
    assert "crissp/uxsuite/results/" in (old / ".gitignore").read_text().splitlines()
    assert repair.main([], {"CRISSP_ROOT": str(old)}) == 1  # what needs a person is still said
    again = capsys.readouterr().out
    assert "nothing out of place." in again and "Needs you:" in again


def test_a_project_in_place_hears_nothing_out_of_place(tmp_path, capsys):
    root = tmp_path / "fine"
    bring_in(root)
    write(root / "docker-compose.yml", "services: {}\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "start")
    assert repair.main([], {"CRISSP_ROOT": str(root)}) == 0
    assert capsys.readouterr().out == "crissp repair: nothing out of place.\n"


def test_steps_of_its_own_and_a_vite_dev_server_are_left_alone(tmp_path):
    root = tmp_path / "own"
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": [{"key": "api", "label": "A", "run": "x"}]}))
    write(root / "crissp/uxsuite/team.json", json.dumps({"url": "http://127.0.0.1:5173"}))
    write(root / "app/frontend/vite.config.ts", "export default {}\n")
    assert "steps" not in keys(root) and "ux-url" not in keys(root)


def test_old_steps_stay_while_src_is_really_there_and_an_empty_list_gets_the_default(tmp_path):
    root = tmp_path / "src-project"
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": OLD_STEPS}))
    write(root / "src/a.py", "x = 1\n")
    assert "steps" not in keys(root)
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": []}))
    fix = next(r for r in repair.find(root) if r.key == "steps")
    assert "no steps" in fix.what
    fix.do()
    assert [s["key"] for s in json.loads((root / "crissp/testsuite/suites.json").read_text())["steps"]] == [
        "backend", "backend-lint", "frontend"]


def test_no_configuration_and_broken_json_are_not_repaired(tmp_path):
    root = tmp_path / "bare"
    root.mkdir()
    assert repair.find(root) == []
    write(root / "crissp/testsuite/suites.json", "{not json")
    write(root / "crissp/uxsuite/team.json", "[]")
    assert "steps" not in keys(root) and "ux-url" not in keys(root)


def test_without_deploy_settings_the_stack_is_the_default_port(tmp_path):
    root = tmp_path / "nodeploy"
    write(root / "crissp/uxsuite/team.json", json.dumps({"url": "http://127.0.0.1:5173"}))
    url = {r.key: r.what for r in repair.find(root)}["ux-url"]
    assert "→ http://127.0.0.1:8080" in url
    write(root / "crissp/deploy/deploy.json", "{}")
    assert "→ http://127.0.0.1:8080" in {r.key: r.what for r in repair.find(root)}["ux-url"]


def test_a_move_never_overwrites_it_says_so_instead(old):
    write(old / "docs/ux/prototype/index.html", "theirs")
    fixes = {r.key: r for r in repair.find(old)}
    assert [p.name for p in fixes["ux-extra"].moves] == ["notes.txt"]  # only what has a free place
    assert any("docs/ux/prototype is already there" in n for n in repair.needs(old))
    fixes["ux-extra"].do()
    assert (old / "docs/ux/prototype/index.html").read_text() == "theirs"
    assert (old / "crissp/uxsuite/prototype/index.html").is_file()


def test_the_frameworks_own_repository_keeps_its_engine_in_crissp_uxsuite(tmp_path, monkeypatch):
    monkeypatch.setattr(repair, "ENGINE", tmp_path / "eng" / "crissp")
    write(tmp_path / "eng/crissp/uxsuite/ux_team.py", "")
    write(tmp_path / "eng/crissp/uxsuite/team.json", json.dumps({"url": "http://127.0.0.1:8766"}))
    assert repair.find(tmp_path / "eng") == []


def test_the_root_is_crissp_root_else_the_current_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert repair.main([], {}) == 1  # an empty folder: no commit, no compose file
    assert "Needs you:" in capsys.readouterr().out


def test_it_runs_as_a_script(old):
    done = subprocess.run([sys.executable, str(REPO / "crissp/testsuite/lib/repair.py")], capture_output=True, text=True,
                          env={"CRISSP_ROOT": str(old), "PATH": "/usr/bin:/bin"}, check=False)
    assert done.returncode == 1 and "crissp repair:" in done.stdout


def test_without_git_there_is_no_commit(tmp_path, monkeypatch):
    def gone(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(repair.subprocess, "run", gone)
    assert any(line.startswith("no commit yet") for line in repair.needs(tmp_path))


def test_anything_but_yes_is_the_usage(tmp_path, capsys):
    assert repair.main(["--force"], {"CRISSP_ROOT": str(tmp_path)}) == 2
    assert capsys.readouterr().out == "usage: crissp repair [--yes]\n"


def test_the_crissp_folder_keeps_its_own_walks_and_a_gitignore_is_made_when_there_is_none(tmp_path):
    root = tmp_path / "walked"
    bring_in(root)
    (root / "crissp/uxsuite/walks/first-visit.json").unlink()
    write(root / "crissp/uxsuite/walks/checkout.json", "{}")
    (root / ".gitignore").unlink()
    (root / "crissp/backlog/PLAN.md").unlink()
    (root / "crissp/CRISSP.md").write_text("an old framework\n")
    fixes = {r.key: r for r in repair.find(root)}
    assert list(fixes) == ["missing", "crissp-md", "gitignore"]
    assert "crissp/backlog/PLAN.md" in fixes["missing"].what and "first-visit" not in fixes["missing"].what
    assert " …) → added" in fixes["gitignore"].what
    for fix in fixes.values():
        fix.do()
    assert not (root / "crissp/uxsuite/walks/first-visit.json").exists() and keys(root) == []
    assert (root / ".gitignore").read_text().startswith("# --- C.R.I.S.S.P.: added by crissp repair\n")


def test_a_gitignore_without_a_last_newline_gets_one_before_the_rules(tmp_path):
    root = tmp_path / "nl"
    bring_in(root)
    rules = (repair.TEMPLATE / "gitignore.crissp").read_text().splitlines()
    (root / ".gitignore").write_text("\n".join(x for x in rules if x != ".DS_Store"))  # one rule short, no newline
    (fix,) = repair.find(root)
    assert fix.what == ".gitignore lacks 1 of the framework's rules (.DS_Store) → added"
    fix.do()
    assert (root / ".gitignore").read_text().endswith("!*.tfvars.example\n# --- C.R.I.S.S.P.: added by crissp repair\n.DS_Store\n")


def test_a_folder_never_brought_in_is_told_to_run_init(tmp_path):
    assert repair.needs(tmp_path)[0] == "not brought in: no crissp/ here; crissp init brings it in"


def test_plain_path_sources_in_changes_json_become_file_and_symbol(tmp_path, capsys):
    """F-20: the dashboard reads a source as {file, symbol}; a plain path becomes the file from the top."""
    root = tmp_path / "shop"
    bring_in(root)
    changes = {"changes": [{"id": "a", "sources": ["app/x.py", {"file": "app/y.py", "symbol": "def y"}]},
                           {"id": "b", "sources": ["app/z/"]}, "not an entry"], "gaps": ["kept"]}
    write(root / "crissp/testsuite/changes.json", json.dumps(changes))
    assert "changes" in keys(root)
    repair.main([], {"CRISSP_ROOT": str(root)})
    assert "2 sources are plain paths" in capsys.readouterr().out
    repair.main(["--yes"], {"CRISSP_ROOT": str(root)})
    fixed = json.loads((root / "crissp/testsuite/changes.json").read_text())
    assert fixed["changes"][0]["sources"] == [{"file": "app/x.py", "symbol": ""}, {"file": "app/y.py", "symbol": "def y"}]
    assert fixed["changes"][1]["sources"] == [{"file": "app/z/", "symbol": ""}] and fixed["gaps"] == ["kept"]
    assert fixed["changes"][2] == "not an entry"  # what it does not understand, it leaves as it is
    assert "changes" not in keys(root)


def test_the_mcp_pin_follows_the_crissp_that_repairs(tmp_path, capsys):
    """F-20: .mcp.json pins crissp; a newer crissp's repair moves the pin to itself, never anything else in the file."""
    root = tmp_path / "shop"
    bring_in(root)
    mcp = {"mcpServers": {"crissp": {"command": "uvx", "args": ["crissp==0.1.2", "mcp"], "env": {"PYTHONUTF8": "1"}},
                          "other": {"command": "x", "args": ["crissp==0.1.2"]}}}
    write(root / ".mcp.json", json.dumps(mcp))
    assert "mcp-pin" not in [r.key for r in repair.find(root)]  # no version known (not run as the crissp command)
    assert "mcp-pin" not in [r.key for r in repair.find(root, "0.1.2")]
    repair.main(["--yes"], {"CRISSP_ROOT": str(root), "CRISSP_VERSION": "0.1.5",
                            "VIBE_HOME": str(tmp_path / "vibe-home")})  # F-24: keep the trust file out of a real ~/.vibe
    assert "crissp==0.1.2 → crissp==0.1.5" in capsys.readouterr().out
    fixed = json.loads((root / ".mcp.json").read_text())
    assert fixed["mcpServers"]["crissp"] == {"command": "uvx", "args": ["crissp==0.1.5", "mcp"], "env": {"PYTHONUTF8": "1"}}
    assert fixed["mcpServers"]["other"] == mcp["mcpServers"]["other"]
    write(root / ".mcp.json", json.dumps({"mcpServers": {"crissp": {"command": "uvx", "args": ["crissp", "mcp"]}}}))
    assert "mcp-pin" not in [r.key for r in repair.find(root, "0.1.5")]  # not pinned: left as it is


def test_the_agreement_gets_this_crissps_sessions_section(tmp_path, capsys):
    """F-21: crissp/CLAUDE.md's 'Sessions that stay small' is crissp's: added when missing, replaced when it differs."""
    root = tmp_path / "shop"
    bring_in(root)
    agreement = root / "crissp/CLAUDE.md"
    section = repair.section((repair.TEMPLATE / "crissp/CLAUDE.md").read_text(), repair.SESSIONS)
    assert section.startswith(repair.SESSIONS) and "/clear" in section and "## Working" not in section
    assert "sessions" not in keys(root)  # as init made it: in place

    write(agreement, "# shop\n\n## Own rules\n\nkept\n\n## Working with the product owner\n\n- ask\n")
    repair.main(["--yes"], {"CRISSP_ROOT": str(root)})
    assert "sessions" in capsys.readouterr().out
    assert agreement.read_text() == ("# shop\n\n## Own rules\n\nkept\n\n" + section
                                     + "## Working with the product owner\n\n- ask\n")
    assert "sessions" not in keys(root)

    write(agreement, f"# shop\n\n{repair.SESSIONS}\n\nan old text\n\n## After\n\nkept\n")
    [r.do() for r in repair.find(root) if r.key == "sessions"]
    assert agreement.read_text() == f"# shop\n\n{section}## After\n\nkept\n"

    write(agreement, f"# shop\n\n{repair.SESSIONS}\n\nold, at the end")
    [r.do() for r in repair.find(root) if r.key == "sessions"]
    assert agreement.read_text() == f"# shop\n\n{section}"

    write(agreement, "# shop\n\nno sections, no newline")
    [r.do() for r in repair.find(root) if r.key == "sessions"]
    assert agreement.read_text() == f"# shop\n\nno sections, no newline\n\n{section}"

    agreement.unlink()
    assert "sessions" not in keys(root)  # no agreement: `missing` makes it from the template


def test_vibe_config_and_trust_are_put_in_place(tmp_path):
    """F-24 / E5-F1-01: a project brought in before Vibe onboarding gets .vibe/config.toml and a trust entry."""
    root = tmp_path / "shop"
    bring_in(root)
    home = tmp_path / "vibe"
    home.mkdir()
    write(home / "trusted_folders.toml", 'trusted = [\n    "/elsewhere",\n]\nuntrusted = []\n')
    fix = next(r for r in repair.find(root, "9.9.9", home) if r.key == "vibe")
    assert "crissp==9.9.9" in fix.what and "trusted" in fix.what
    fix.do()
    assert 'crissp==9.9.9' in (root / ".vibe" / "config.toml").read_text()
    db = (home / "trusted_folders.toml").read_text()
    assert f'"{root}"' in db and '"/elsewhere"' in db
    assert "vibe" not in [r.key for r in repair.find(root, "9.9.9", home)]  # in place now


def test_vibe_repair_needs_a_version_and_a_brought_in_project(tmp_path):
    root = tmp_path / "x"
    assert "vibe" not in [r.key for r in repair.find(root, "9.9.9", tmp_path)]  # not brought in
    bring_in(root)
    assert "vibe" not in [r.key for r in repair.find(root)]  # no version known: not run as the crissp command
    home = tmp_path / "no-vibe-home"  # no Vibe installed: the config is still made, no trust file appears
    fix = next(r for r in repair.find(root, "9.9.9", home) if r.key == "vibe")
    fix.do()
    assert (root / ".vibe" / "config.toml").is_file() and not home.exists()
    write(root / ".vibe/config.toml", "# ours\n")
    assert "vibe" not in [r.key for r in repair.find(root, "9.9.9", home)]  # config there, no Vibe home: nothing to do
    home2 = tmp_path / "vibe2"
    home2.mkdir()
    write(home2 / "trusted_folders.toml", f'trusted = [\n    "{root}",\n]\n')
    assert "vibe" not in [r.key for r in repair.find(root, "9.9.9", home2)]  # config there and trusted: nothing to do


def test_vibe_repair_leaves_an_untrusted_folder_and_an_unknown_file_alone(tmp_path):
    """F-26: a folder the user marked untrusted is never proposed for trust, nor is one in a file crissp does not
    know; with the config in place there is then nothing to do."""
    root = tmp_path / "shop"
    bring_in(root)
    home = tmp_path / "vibe"
    home.mkdir()
    for text in (f'trusted = []\nuntrusted = [\n    "{root}",\n]\n', "trusted = [\n"):
        write(home / "trusted_folders.toml", text)
        (root / ".vibe/config.toml").unlink(missing_ok=True)
        fix = next(r for r in repair.find(root, "9.9.9", home) if r.key == "vibe")
        assert "trusted" not in fix.what
        fix.do()
        assert (home / "trusted_folders.toml").read_text() == text
        assert "vibe" not in [r.key for r in repair.find(root, "9.9.9", home)]


def test_vibe_trust_alone_when_the_config_is_already_there(tmp_path):
    """F-24: .vibe/config.toml exists but the folder is not trusted: only the trust entry is added, config kept."""
    root = tmp_path / "shop"
    bring_in(root)
    write(root / ".vibe/config.toml", "# ours\n")
    home = tmp_path / "vibe"
    home.mkdir()
    write(home / "trusted_folders.toml", "trusted = []\n")
    fix = next(r for r in repair.find(root, "9.9.9", home) if r.key == "vibe")
    assert "config.toml" not in fix.what and "trusted" in fix.what
    fix.do()
    assert (root / ".vibe/config.toml").read_text() == "# ours\n"  # never overwritten
    assert f'"{root}"' in (home / "trusted_folders.toml").read_text()

