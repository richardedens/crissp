"""What a project gets when it is CRISSPified (crissp/template/): the testsuite's skeleton and the uxsuite's part are
valid configurations once {{PRODUCT}} is filled in, and name nothing but placeholders (test_generic_names reads them)."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "crissp" / "template" / "crissp"
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import project


def filled(path: Path, product: str = "Example") -> dict:
    text = path.read_text()
    assert "{{PRODUCT}}" in text  # the one name a project fills in
    return json.loads(text.replace("{{PRODUCT}}", product))


def configured(tmp_path: Path, *parts: str) -> tuple[dict, Path]:
    root = tmp_path / "example"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(
        json.dumps(filled(TEMPLATE / "testsuite" / "suites.json"))
    )
    for part in parts:
        (root / part).parent.mkdir(parents=True, exist_ok=True)
        (root / part).mkdir() if not part.endswith(".json") else (root / part).write_text("{}")
    return project.load(root), root


def test_the_testsuite_skeleton_is_a_valid_configuration(tmp_path):
    conf, _ = configured(tmp_path)
    assert conf["product"] == "Example"
    assert all(s["label"].startswith("CRISSP: ") for s in conf["steps"])  # what the project fills in is marked


def test_the_default_parts_are_app_backend_and_app_frontend_and_a_step_exists_once_its_part_does(tmp_path):
    conf, root = configured(tmp_path)  # D-02: a project just brought in has no part yet, so no step fails on nothing
    assert project.steps(conf, root) == []
    conf, root = configured(tmp_path / "both", "app/backend", "app/frontend/package.json")
    assert [s["key"] for s in project.steps(conf, root)] == [
        "backend",
        "gate",
        "backend-lint",
        "frontend",
        "frontend-lint",
        "audit",
        "secrets",
        "sast",
    ]
    assert {s["key"]: s["dir"] for s in conf["steps"]} == {
        "backend": "app/backend",
        "backend-lint": "app/backend",
        "frontend": "app/frontend",
        "frontend-lint": "app/frontend",
        "audit": ".",
        "secrets": ".",
        "sast": ".",
    }
    assert [(r["match"], r["steps"]) for r in conf["paths"]] == [
        ("app/backend/", ["backend", "backend-lint", "secrets", "sast"]),
        ("app/frontend/", ["frontend", "frontend-lint", "secrets", "sast"]),
    ]
    assert "docker-compose.yml" in [r["match"] for r in conf["shared"]]  # how the parts run together: the full run
    assert ".githooks/" in [r["match"] for r in conf["shared"]]  # F-50: what git runs before every commit
    assert [s["key"] for s in conf["steps"] if s["parallel"]] == ["backend"]  # E1-F1-02: spread over the machine
    lint = next(
        s for s in conf["steps"] if s["key"] == "frontend-lint"
    )  # F-34: crissp's own tools, the project's files
    assert lint["run"] == "frontend_lint" and lint["when"] == "app/frontend/package.json"  # untouched


def test_every_project_is_audited_in_its_full_run_on_the_default_places(tmp_path):
    """F-42: CVEs in the dependencies and images, misconfigurations in the Dockerfiles, the chart and Terraform; a place
    the project does not have yet is listed, not red."""
    conf, _ = configured(tmp_path)
    step = next(s for s in conf["steps"] if s["key"] == "audit")
    assert step["run"] == "audit run" and step["full_only"] and step["when"] == "app"
    assert conf["audit"] == {
        "missing": "skip",
        "pip": ["app/backend/requirements.txt"],
        "npm": ["app/frontend"],
        "fs": ["app/backend", "app/frontend"],
        "dockerfiles": ["app/*/Dockerfile"],
        "config": ["crissp/deploy/helm/app", "crissp/deploy/terraform"],
        "images": ["docker-compose.yml", "crissp/deploy/helm/app/values.yaml"],
        "own_images": {"values": "crissp/deploy/helm/app/values.yaml", "parts": ["backend", "frontend"]},
        "sast": ["app"],
        "sast_rules": [],
    }


def test_every_project_scans_its_git_history_for_secrets(tmp_path):
    """F-43: gitleaks over the history, in every check that touches a part; the project's own gitleaks files count."""
    conf, _ = configured(tmp_path)
    step = next(s for s in conf["steps"] if s["key"] == "secrets")
    assert step["run"] == "audit secrets" and not step["full_only"] and step["when"] == "app"


def test_every_project_s_code_is_scanned_for_unsafe_code(tmp_path):
    """F-44: Semgrep with crissp's rules on app/ (the project's own rules folders can be named in sast_rules), and
    ruff's Bandit rules (S) on top of the backend's own ruff configuration."""
    conf, _ = configured(tmp_path)
    step = next(s for s in conf["steps"] if s["key"] == "sast")
    assert step["run"] == "audit sast" and not step["full_only"] and step["when"] == "app"
    assert conf["audit"]["sast"] == ["app"]
    lint = next(s for s in conf["steps"] if s["key"] == "backend-lint")
    assert lint["run"] == "ruff_check ."


def test_the_ux_suite_walks_the_local_stack_the_deploy_template_names():
    compose = json.loads((REPO / "crissp" / "deploy" / "deploy.json").read_text())["compose"]
    assert compose["file"] == "docker-compose.yml" and set(compose["services"]) == {"backend", "frontend"}
    url = compose["url"].replace("{port}", str(compose["port"]["default"]))
    assert filled(TEMPLATE / "uxsuite" / "team.json")["url"] == url  # not a dev server, not a prototype


def test_the_framework_and_the_agreement_name_the_default_layout():
    for doc in (REPO / "crissp" / "CRISSP.md", TEMPLATE / "CLAUDE.md"):
        text = doc.read_text()
        for name in ("app/backend", "app/frontend", "docker-compose.yml", "crissp ux --propose"):
            assert name in text, (doc.name, name)
    agreement = (TEMPLATE / "CLAUDE.md").read_text()
    assert "`crissp/tool`" not in agreement  # an installed project's tools come from the crissp MCP server (F-10)


def test_the_testsuite_skeleton_starts_with_no_changes_an_honest_gap_and_no_accepted_risk():
    changes = filled(TEMPLATE / "testsuite" / "changes.json")
    assert changes["changes"] == [] and len(changes["gaps"]) == 1 and changes["gaps"][0].startswith("CRISSP: ")
    assert json.loads((TEMPLATE / "testsuite" / "accepted-risks.json").read_text()) == {"accepted": []}


def test_the_uxsuite_part_is_there_with_its_own_ignore_and_no_old_ux_team():
    ux = TEMPLATE / "uxsuite"
    rules = [x for x in (ux / ".gitignore").read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert rules == ["results/"]  # what the suite makes stays local
    team = filled(ux / "team.json")
    assert (
        team["product"] == "Example"
        and len(team["personas"]) == 5
        and sum(p["moderator"] for p in team["personas"]) == 1
    )
    assert sorted(p.name for p in (ux / "walks").glob("*.json")) == ["first-visit.json"]
    assert not (TEMPLATE / "uxteam").exists()


def test_parallel_workers_share_one_postgresql_server_with_a_database_each():
    # a worker per CPU must not mean a PostgreSQL server per worker: one server for the run, a database per worker
    for doc in (REPO / "crissp" / "CRISSP.md", TEMPLATE / "CLAUDE.md", REPO / "crissp" / "testsuite" / "README.md"):
        text = " ".join(doc.read_text().split())
        for words in ("one PostgreSQL server", "a database per worker", "PYTEST_XDIST_WORKER"):
            assert words in text, (doc.name, words)


def test_the_framework_and_the_agreement_say_how_a_session_stays_small():
    """E4-F1-01: every step resends the whole conversation; the habits that keep it short are part of the agreement."""
    for doc in (REPO / "crissp" / "CRISSP.md", TEMPLATE / "CLAUDE.md", REPO / "crissp" / "CLAUDE.md"):
        text = " ".join(doc.read_text().split())
        for words in (
            "Sessions that stay small",
            "/clear",
            "/compact",
            "in a subagent",
            "start with `run` and are read with `status`",
            "Explore agent",
        ):
            assert words in text, (doc.name, words)


def test_the_sessions_section_names_the_vibe_way_too():
    """F-102: 'Sessions that stay small' spoke only Claude Code; a Vibe session gets its own equivalents, in the same
    section repair keeps in step (F-21), so projects brought in earlier get them with crissp repair --yes."""
    for doc in (REPO / "crissp" / "CRISSP.md", TEMPLATE / "CLAUDE.md", REPO / "crissp" / "CLAUDE.md"):
        text = doc.read_text()
        start = text.index("## Sessions that stay small")
        section = " ".join(text[start : text.index("\n## ", start + 1)].split())
        for words in (
            "Mistral Vibe",
            "a new session in the desktop app",
            "`/compact <what to keep>`",
            "`task` tool",
            "`explore` agent",
            "auto_compact_threshold",
            "Vibe sessions too",
        ):
            assert words in section, (doc.name, words)


def test_the_root_agents_file_gives_an_agent_its_first_moves():
    """F-110: Vibe reads AGENTS.md as its instructions. A pointer to two long files made it explore for ten steps and
    start the full run on "use crissp fully"; the root file now says the first moves itself, short, in the template and
    in this repository alike, and crissp/AGENTS.md says it is not for the main session."""
    for agents in (REPO / "AGENTS.md", REPO / "crissp/template/AGENTS.md"):
        text = agents.read_text()
        assert len(text.splitlines()) <= 25, agents
        for needed in (
            "`brief`",
            "`stage`",
            "`backlog`",
            "`run`",
            "`status`",
            "`check-all`",
            "search_tool_functions",
            ".agents/skills/crissp/SKILL.md",
            "`.env`",
            "repair",
        ):
            assert needed in text, (agents, needed)
    for sub in (REPO / "crissp/AGENTS.md", TEMPLATE / "AGENTS.md"):
        assert "main session" in sub.read_text().split("\n\n")[1] and "ignores this file" in sub.read_text()


def tools() -> list[str]:
    """The names of the tools the crissp MCP server offers (crissp/tool/server.py's TOOLS)."""
    sys.path.insert(0, str(REPO / "crissp" / "tool"))
    import server

    return [t["name"] for t in server.TOOLS]


def test_the_crissp_skill_is_the_engines_and_this_repository_uses_it():
    """F-111: the playbook for the crissp tools, as an agent skill (.agents/skills: Vibe loads it when needed, and it
    can be committed): when to call which tool, what waits for the product owner, what to do when a tool is slow."""
    skill = REPO / "crissp/template/agents/skills/crissp/SKILL.md"
    text = skill.read_text()
    head = text.split("---")[1]
    assert "name: crissp" in head and "description: " in head
    for tool in tools():  # every tool the crissp MCP server offers, so a new one cannot be missed (stage, F-130)
        assert f"`{tool}`" in text, tool
    assert "check-all" in text and "{{" not in text
    assert (REPO / ".agents/skills/crissp/SKILL.md").read_text() == text
