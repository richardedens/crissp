"""crissp repair brings a project level with the template (F-160 to F-162): the template's steps, every stale crissp
pin in the tracked files, and the scans a project runs itself next to crissp's."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import level
import repair

TEMPLATE = json.loads((repair.TEMPLATE / "crissp/testsuite/suites.json").read_text())


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit_all(root: Path) -> None:
    git(root, "init", "-q")
    git(root, "add", "-A")


def step(key: str) -> dict:
    return next(s for s in TEMPLATE["steps"] if s["key"] == key)


@pytest.fixture
def behind(tmp_path) -> Path:
    """A project brought in by an older crissp: backend steps only, no audit block, an older pin everywhere."""
    root = tmp_path / "shop"
    write(
        root / "crissp/testsuite/suites.json",
        json.dumps(
            {
                "product": "shop",
                "steps": [step("backend"), step("backend-lint"), step("frontend")],
                "paths": [{"match": "app/backend/", "steps": ["backend", "backend-lint"]}],
                "shared": [{"match": "docker-compose.yml", "why": "how the parts run together"}],
            }
        ),
    )
    write(root / "app/backend/main.py", "x = 1\n")
    write(root / "app/frontend/package.json", "{}\n")
    return root


def test_the_missing_template_steps_whose_part_is_here_are_added_with_their_path_rules(behind):
    data = json.loads((behind / "crissp/testsuite/suites.json").read_text())
    out, what, said = level.suites(behind, data, TEMPLATE)
    keys = [s["key"] for s in out["steps"]]
    assert keys == ["backend", "backend-lint", "frontend", "frontend-lint", "audit", "secrets", "sast"]
    assert "frontend-lint, audit, secrets, sast" in what[0] and "audit block" in what[1]
    rules = {r["match"]: r["steps"] for r in out["paths"]}
    assert rules["app/backend/"] == ["backend", "backend-lint", "secrets", "sast"]  # its own rule, extended
    assert rules["app/frontend/"] == ["frontend", "frontend-lint", "secrets", "sast"]  # the template's, added
    assert out["audit"] == TEMPLATE["audit"]
    assert out["shared"][0]["match"] == "docker-compose.yml" and ".githooks/" in what[2]
    assert said == [] and data["steps"] == out["steps"][:3]  # the project's file as read is not changed


def test_a_step_whose_part_is_not_here_is_said_and_one_under_its_own_name_is_not_missing(tmp_path):
    root = tmp_path / "web"
    write(root / "app/backend/main.py", "")
    data = {
        "steps": [{**step("backend"), "key": "api"}, step("backend-lint"), step("audit"), step("secrets")],
        "audit": {},
        "shared": TEMPLATE["shared"],
        "paths": [],
    }
    out, what, said = level.suites(root, data, TEMPLATE)
    assert [s["key"] for s in out["steps"]][-1] == "sast" and what == [
        "the template's steps sast (their parts are here)"
    ]
    assert {r["match"]: r["steps"] for r in out["paths"]} == {
        "app/backend/": ["backend-lint", "secrets", "sast"],
        "app/frontend/": ["secrets", "sast"],
    }
    assert len(said) == 2 and "no frontend step" in said[0] and "app/frontend/package.json is not here" in said[0]
    assert "no frontend-lint step (the frontend's lint" in said[1] and "`run`: frontend_lint" in said[1]


def test_a_project_level_with_the_template_needs_nothing(tmp_path):
    assert level.suites(tmp_path, TEMPLATE, TEMPLATE) == (None, [], [])
    assert level.suites(tmp_path, {"steps": [{"key": "x", "run": "y"}]}, {"shared": []})[0] is None


def test_repair_names_the_missing_steps_and_yes_adds_them(behind, capsys):
    assert repair.main([], {"CRISSP_ROOT": str(behind)}) == 1
    out = capsys.readouterr().out
    assert (
        "  suites     crissp/testsuite/suites.json lacks the template's steps frontend-lint, audit, secrets, sast"
        in out
    )
    assert repair.main(["--yes"], {"CRISSP_ROOT": str(behind)}) == 0
    conf = json.loads((behind / "crissp/testsuite/suites.json").read_text())
    assert [s["key"] for s in conf["steps"]][3:] == [
        "frontend-lint",
        "audit",
        "secrets",
        "sast",
        "quality",  # F-145: new-steps adds the newest ones after, on what the suites repair wrote
        "licenses",
        "dast",
    ]
    assert {"dast", "quality", "pip"} <= set(conf["audit"])
    capsys.readouterr()
    repair.main([], {"CRISSP_ROOT": str(behind)})
    assert "  suites " not in capsys.readouterr().out


def test_a_missing_part_is_said_under_needs_you(tmp_path, capsys):
    root = tmp_path / "x"
    write(root / "crissp/testsuite/suites.json", json.dumps({**TEMPLATE, "steps": [step("backend")]}))
    repair.main([], {"CRISSP_ROOT": str(root)})
    out = capsys.readouterr().out
    assert "  - suites.json has no frontend-lint step" in out
    assert repair.suites_needs(tmp_path / "nowhere") == []


def test_no_steps_and_the_old_steps_are_left_to_the_steps_repair(tmp_path):
    root = tmp_path / "x"
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": [{"key": "unit"}]}))
    assert repair.fix_suites(root) is None and repair.suites_needs(root) == []
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": []}))
    assert repair.fix_suites(root) is None
    write(root / "crissp/testsuite/suites.json", json.dumps({"steps": {"no": "list"}}))
    assert repair.fix_suites(root) is None and repair.suites_needs(root) == []


def test_every_older_pin_in_the_tracked_files_moves_and_is_listed(behind, capsys):
    write(behind / "deploy.sh", '#!/bin/bash\nexec uvx crissp==0.1.8 deploy "$@"\n')
    write(behind / "README.md", "Run `uvx crissp==0.1.8 check`, or crissp==0.1.10rc1, never crissp==9.0.0.\n")
    write(behind / "crissp/deploy/deploy.json", '{"crissp": "crissp==0.1.8"}\n')
    write(behind / "CHANGELOG.md", "0.1.8: crissp==0.1.8 was the pin\n")  # the history stays
    write(behind / "crissp/backlog/PLAN.md", "crissp==0.1.8\n")
    write(behind / ".mcp.json", '{"mcpServers": {}}\n')  # fix_pin's file
    write(behind / "logo.png", "")
    (behind / "logo.png").write_bytes(b"\x89PNG crissp==0.1.8 \xff\xfe")
    write(behind / "untracked.sh", "crissp==0.1.8\n")
    commit_all(behind)
    (behind / "untracked.sh").unlink()
    git(behind, "rm", "-q", "--cached", "README.md")
    git(behind, "add", "README.md")
    found = level.stale_pins(behind, "0.2.1")
    assert found == {
        "README.md": ["crissp==0.1.10rc1", "crissp==0.1.8"],
        "crissp/deploy/deploy.json": ["crissp==0.1.8"],
        "deploy.sh": ["crissp==0.1.8"],
    }
    assert repair.main(["--yes"], {"CRISSP_ROOT": str(behind), "CRISSP_VERSION": "0.2.1"}) == 0
    assert "  pins       older crissp pins in README.md (crissp==0.1.10rc1 crissp==0.1.8)" in capsys.readouterr().out
    assert (behind / "deploy.sh").read_text() == '#!/bin/bash\nexec uvx crissp==0.2.1 deploy "$@"\n'
    assert (behind / "README.md").read_text() == (
        "Run `uvx crissp==0.2.1 check`, or crissp==0.2.1, never crissp==9.0.0.\n"
    )
    assert (behind / "CHANGELOG.md").read_text() == "0.1.8: crissp==0.1.8 was the pin\n"
    assert level.stale_pins(behind, "0.2.1") == {}


def test_without_git_or_a_version_crissp_could_pin_no_pin_moves(tmp_path):
    write(tmp_path / "deploy.sh", "crissp==0.1.8\n")
    assert level.stale_pins(tmp_path, "0.2.1") == {}  # not a repository: nothing is tracked
    commit_all(tmp_path)
    assert level.stale_pins(tmp_path, "main") == {}
    assert repair.fix_pins(tmp_path, None) is None


def test_no_git_at_all_tracks_nothing(tmp_path, monkeypatch):
    def gone(*a, **k):
        raise OSError("no git")

    monkeypatch.setattr(level.subprocess, "run", gone)
    assert level.tracked(tmp_path) == []


def test_a_large_file_is_no_script(tmp_path, monkeypatch):
    write(tmp_path / "big.sh", "crissp==0.1.8\n")
    monkeypatch.setattr(level, "BIG", 3)
    assert level.text_of(tmp_path / "big.sh") is None and level.text_of(tmp_path / "missing") is None


def test_scans_of_the_projects_own_are_said_with_the_one_to_keep(tmp_path, capsys):
    root = tmp_path / "shop"
    write(root / "crissp/testsuite/suites.json", json.dumps(TEMPLATE))
    write(root / "app/backend/requirements-dev.txt", "bandit==1.8\n")
    write(root / ".bandit", "[bandit]\n")
    write(root / ".github/workflows/ci.yml", "- run: gitleaks dir .\n- run: grype myimage\n")
    write(root / "scripts/scan.sh", "gitleaks detect --source . --no-git\n")
    write(root / ".pre-commit-config.yaml", "- id: gitleaks\n  entry: gitleaks git --pre-commit --staged\n")
    write(root / ".gitlab-ci.yml", "- gitleaks detect --redact\n- uses: gitleaks/gitleaks-action@v2\n")
    write(root / "docs/notes.md", "we tried bandit and grype\n")  # not where a scan runs
    write(root / "crissp/deploy/x.sh", "grype x\n")  # crissp's own folder
    commit_all(root)
    lines = level.overlaps(root)
    assert len(lines) == 4
    assert lines[0].startswith("bandit (.bandit, app/backend/requirements-dev.txt) and crissp's backend-lint")
    assert lines[1].startswith("gitleaks on the files (.github/workflows/ci.yml, scripts/scan.sh)")
    assert lines[2].startswith("gitleaks on the history (.gitlab-ci.yml) and crissp's secrets step")
    assert lines[3].startswith("Grype (.github/workflows/ci.yml) and crissp's audit step")
    repair.main([], {"CRISSP_ROOT": str(root)})
    assert "  - bandit (.bandit" in capsys.readouterr().out


def test_a_project_without_scans_of_its_own_hears_none(tmp_path):
    write(tmp_path / "Makefile", "test:\n\tpytest\n")
    commit_all(tmp_path)
    assert level.overlaps(tmp_path) == []
