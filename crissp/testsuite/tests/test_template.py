"""What a project gets when it is CRISSPified (crissp/template/): the testsuite's skeleton and the uxsuite's part are
valid configurations once {{PRODUCT}} is filled in, and name nothing but placeholders (test_generic_names reads them)."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "crissp" / "template" / "crissp"
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import project  # noqa: E402


def filled(path: Path, product: str = "Example") -> dict:
    text = path.read_text()
    assert "{{PRODUCT}}" in text  # the one name a project fills in
    return json.loads(text.replace("{{PRODUCT}}", product))


def configured(tmp_path: Path, *parts: str) -> tuple[dict, Path]:
    root = tmp_path / "example"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(json.dumps(filled(TEMPLATE / "testsuite" / "suites.json")))
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
    assert [s["key"] for s in project.steps(conf, root)] == ["backend", "gate", "backend-lint", "frontend",
                                                              "frontend-lint"]
    assert {s["key"]: s["dir"] for s in conf["steps"]} == {"backend": "app/backend", "backend-lint": "app/backend",
                                                         "frontend": "app/frontend", "frontend-lint": "app/frontend"}
    assert [(r["match"], r["steps"]) for r in conf["paths"]] == [("app/backend/", ["backend", "backend-lint"]),
                                                                ("app/frontend/", ["frontend", "frontend-lint"])]
    lint = next(s for s in conf["steps"] if s["key"] == "frontend-lint")  # F-30: the frontend is linted like the backend
    assert lint["run"] == "npm run --silent lint" and lint["when"] == "app/frontend/package.json"
    assert "docker-compose.yml" in [r["match"] for r in conf["shared"]]  # how the parts run together: the full run
    assert ".githooks/" in [r["match"] for r in conf["shared"]]  # F-50: what git runs before every commit
    assert [s["key"] for s in conf["steps"] if s["parallel"]] == ["backend"]  # E1-F1-02: spread over the machine


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
    assert team["product"] == "Example" and len(team["personas"]) == 5 and sum(p["moderator"] for p in team["personas"]) == 1
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
        for words in ("Sessions that stay small", "/clear", "/compact", "in a subagent", "start with `run` and are read with `status`",
                      "Explore agent"):
            assert words in text, (doc.name, words)
