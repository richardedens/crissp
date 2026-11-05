"""deploy.sh's decisions for a product's local Docker Compose stack: what stops a deploy (the release gate, the release
notes), what is rebuilt (only the services whose files changed, one at a time with --no-deps), and that a product
without a compose file is told so. The services and what goes into them come from crissp/deploy/deploy.json."""

import copy
import importlib.util
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[1]
LIB = SUITE / "lib" / "deploy_plan.py"
DEPLOY_SH = SUITE.parent / "deploy.sh"
DEPLOY_JSON = SUITE.parent / "deploy" / "deploy.json"


def _module():
    spec = importlib.util.spec_from_file_location("deploy_plan_under_test", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dp = _module()

COMPOSE = {
    "file": "docker-compose.yml",
    "url": "http://127.0.0.1:{port}",
    "port": {"setting": "APP_PORT", "default": 8080},
    "health": ["/", "/api/health"],
    "services": {
        "backend": {"inputs": ["docker-compose.yml", "app/backend/Dockerfile", "app/backend/requirements.txt",
                               "app/backend/src/"],
                    "exclude": []},
        "frontend": {"inputs": ["docker-compose.yml", "app/frontend/"], "exclude": ["app/frontend/test/", "*.md"]},
    },
}


def _plan(**kw):
    args = {"gate": [], "notes": [], "deployed": {"commit": "a" * 40, "version": "0.1.0"}, "changed": [], "head": "b" * 40,
            "version": "0.2.0", "compose": COMPOSE, "product": "shop", "port": "8080", "has_file": True}
    return dp.plan(**{**args, **kw})


# ------------------------------------------------------------------------------------------------ the settings

def test_nothing_product_specific_is_written_in_the_code():
    text = LIB.read_text()
    assert "INPUTS = {" not in text and "COMPONENTS = (" not in text and "app/backend" not in text


def test_the_example_deploy_json_names_the_services_and_what_goes_into_them():
    compose = dp.load_compose(DEPLOY_JSON)
    assert compose["file"] and compose["services"]
    for name, service in compose["services"].items():
        assert re.fullmatch(r"[a-z][a-z0-9_-]*", name) and service["inputs"], name


def test_without_deploy_json_there_is_no_compose_stack(tmp_path):
    assert dp.load_compose(tmp_path / "deploy.json") == {}
    assert dp.services({}) == []


# ------------------------------------------------------------------------------------------------ what is rebuilt

@pytest.mark.parametrize("path, components", [
    ("app/backend/src/main.py", ["backend"]),
    ("app/backend/requirements.txt", ["backend"]),
    ("app/backend/Dockerfile", ["backend"]),
    ("app/backend/tests/test_x.py", []),
    ("app/frontend/src/App.tsx", ["frontend"]),
    ("app/frontend/package-lock.json", ["frontend"]),
    ("app/frontend/test/layout.test.ts", []),
    ("app/frontend/NOTES.md", []),
    ("docker-compose.yml", ["backend", "frontend"]),
    ("CHANGELOG.md", []),
    ("crissp/testsuite/lib/gate.py", []),
])
def test_each_service_is_rebuilt_only_when_a_file_that_goes_into_it_changed(path, components):
    assert list(dp.rebuilds(COMPOSE, [path])) == components


def test_without_a_deploy_record_everything_is_rebuilt_and_why_is_said():
    assert dp.rebuilds(COMPOSE, None, "no deploy recorded yet") == {
        c: ["no deploy recorded yet"] for c in ("backend", "frontend")}
    p = _plan(deployed=None, changed=None, why_all="no deploy recorded yet")
    assert p["services"] == ["backend", "frontend"] and not p["stops"]


# ------------------------------------------------------------------------------------------------ what stops a deploy

def test_a_red_release_gate_or_release_notes_stop_it():
    p = _plan(gate=["No full run found: run crissp/check-all.sh on this code."], notes=["VERSION is missing"])
    assert p["stops"] == ["Release gate: No full run found: run crissp/check-all.sh on this code.",
                          "Release notes: VERSION is missing"]


def test_without_a_compose_file_nothing_is_rebuilt_and_it_is_said():
    p = _plan(has_file=False, changed=None)
    assert p["services"] == [] and p["compose"] is False
    text = dp.render_text(p)
    assert "No compose file (docker-compose.yml): nothing to deploy locally." in text
    assert "crissp/deploy.sh --cluster" in text
    assert "PLAN_COMPOSE=0" in dp.render_shell(p)
    empty = dp.plan(gate=[], notes=[], deployed=None, changed=None, head="b" * 40, version="1.0.0", compose={},
                    product="shop", port="", has_file=False)
    assert "No compose file (deploy.json names none)" in dp.render_text(empty)


# ------------------------------------------------------------------------------------------------ how it is shown

def test_the_text_says_what_why_and_how():
    p = _plan(changed=["app/backend/src/main.py"] + [f"app/frontend/src/f{i}.ts" for i in range(8)])
    text = dp.render_text(p)
    assert text.startswith(f"Deploy shop 0.2.0 (commit {'b' * 8})\n  Last deployed: 0.1.0 (commit {'a' * 8})")
    assert "Rebuild backend (docker compose up -d --build --no-deps backend), because: app/backend/src/main.py" in text
    assert "Rebuild frontend (docker compose up -d --build --no-deps frontend), because: app/frontend/src/f0.ts" in text
    assert "f5.ts …" in text and "Stops" not in text
    assert text.endswith("  Then: health checks (http://127.0.0.1:8080/, http://127.0.0.1:8080/api/health), and record "
                         "this commit and version as deployed.")
    fresh = dp.render_text(_plan(changed=["docker-compose.yml"], deployed=None))
    assert "Last deployed: nothing recorded yet" in fresh and "Rebuild backend" in fresh and "Rebuild frontend" in fresh
    stopped = dp.render_text(_plan(gate=["red"]))
    assert "Stops, nothing is rebuilt:\n    - Release gate: red" in stopped
    assert "Nothing to rebuild: no file that goes into backend, frontend changed." in stopped


def test_the_shell_variables_carry_the_plan_quoted():
    p = _plan(changed=["docker-compose.yml"], gate=["a", "b"])
    assert dp.render_shell(p).splitlines() == [
        "PLAN_STOPS=2", "PLAN_COMPOSE=1", "PLAN_FILE=docker-compose.yml", "PLAN_SERVICES='backend frontend'",
        "PLAN_VERSION=0.2.0", f"PLAN_COMMIT={'b' * 40}", "PLAN_PRODUCT=shop",
        "PLAN_HEALTH='http://127.0.0.1:8080/ http://127.0.0.1:8080/api/health'"]
    assert "PLAN_SERVICES=''" in dp.render_shell(_plan())


def test_the_port_comes_from_the_environment_then_dot_env_then_the_default(tmp_path):
    assert dp.port(COMPOSE, tmp_path, {}) == "8080"
    (tmp_path / ".env").write_text("OTHER=1\nAPP_PORT=\"9001\"\nSECRET=never-read\n")
    assert dp.port({**COMPOSE, "port": {"setting": "NONE", "default": 1}}, tmp_path, {}) == "1"  # not in .env
    assert dp.port(COMPOSE, tmp_path, {}) == "9001"
    assert dp.port(COMPOSE, tmp_path, {"APP_PORT": "9002"}) == "9002"
    assert dp.port({**COMPOSE, "port": {}}, tmp_path, {}) == ""


# ------------------------------------------------------------------------------------------------ deploy.sh itself

def test_deploy_sh_never_runs_compose_without_no_deps():
    """Compose is called one service at a time, with --no-deps: never the whole stack, never recreated as a dependency."""
    text = DEPLOY_SH.read_text()
    calls = [line for line in text.splitlines() if re.search(r"^\s*docker compose\b", line)]
    assert calls and all("--no-deps" in c and " up -d --build " in c for c in calls)
    assert "docker compose down" not in text and "--force-recreate" not in text
    assert 'for service in $PLAN_SERVICES' in text


def test_deploy_sh_runs_the_gate_first_without_a_bypass():
    text = DEPLOY_SH.read_text()
    body = text[text.index("# --- local"):]
    assert body.index('[ "$PLAN_COMPOSE" = 1 ]') < body.index("release.py\" check") < body.index("release-notes") \
        < body.index('[ "$PLAN_STOPS" = 0 ]') < body.index("docker compose")
    assert "SKIP" not in text and "--force" not in text and "FORCE" not in text


def test_deploy_sh_says_so_when_there_is_no_compose_file():
    text = DEPLOY_SH.read_text()
    body = text[text.index("# --- local"):]
    assert '[ "$PLAN_COMPOSE" = 1 ]' in body
    assert body.index('[ "$PLAN_COMPOSE" = 1 ]') < body.index("docker compose")


def test_deploy_sh_records_only_after_the_health_checks():
    text = DEPLOY_SH.read_text()
    assert text.index("for service in $PLAN_SERVICES") < text.index("for url in $PLAN_HEALTH") \
        < text.index('python3 "$PLAN" record')


def test_deploy_sh_names_no_product():
    text = DEPLOY_SH.read_text()
    assert "_PORT" not in text and "8495" not in text and "helm/" not in text


# ------------------------------------------------------------------------------------------------ git and the record

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                          cwd=root, check=True, capture_output=True, text=True).stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "app/backend/src").mkdir(parents=True)
    (root / "app/backend/src/main.py").write_text("x = 1\n")
    (root / "docker-compose.yml").write_text("services: {}\n")
    (root / "VERSION").write_text("0.1.0\n")
    (root / "CHANGELOG.md").write_text("## 0.1.0 — unreleased\n- first\n")
    (root / "crissp/deploy").mkdir(parents=True)
    (root / "crissp/deploy/deploy.json").write_text(json.dumps({"product": "shop", "compose": COMPOSE}))
    _git(root, "init", "-q")
    _git(root, "add", ".")
    _git(root, "commit", "-qm", "one")
    return root


def test_what_changed_since_the_deployed_commit(repo):
    first = _git(repo, "rev-parse", "HEAD").strip()
    assert dp.since_deployed(None, repo) == (None, "no deploy recorded yet (crissp/testsuite/results/deploy.json)")
    (repo / "app/backend/src/main.py").write_text("x = 2\n")
    _git(repo, "commit", "-qam", "two")
    assert dp.since_deployed({"commit": first}, repo) == (["app/backend/src/main.py"], "")
    assert dp.since_deployed({"commit": "0" * 40}, repo) == (None, f"the deployed commit {'0' * 8} is not in this checkout")


def test_collect_reads_the_settings_the_certificate_the_notes_and_git(repo):
    p = dp.collect(repo, repo / "deploy.json")
    assert p["version"] == "0.1.0" and p["commit"] == _git(repo, "rev-parse", "HEAD").strip()
    assert p["product"] == "shop" and p["compose"] is True
    assert p["stops"] == ["Release gate: No full run found: run crissp/check-all.sh on this code."]
    assert p["services"] == ["backend", "frontend"]  # nothing deployed yet: everything


def test_collect_without_a_compose_file(repo):
    (repo / "docker-compose.yml").unlink()
    _git(repo, "commit", "-qam", "no compose")
    p = dp.collect(repo, repo / "deploy.json")
    assert p["compose"] is False and p["services"] == []


def test_collect_in_a_repository_without_a_commit_or_a_version(tmp_path):
    _git(tmp_path, "init", "-q")
    p = dp.collect(tmp_path, tmp_path / "deploy.json")
    assert p["commit"] == "(no commit yet)" and p["version"] == "(no VERSION)"
    assert dp.render_text(p).startswith("Deploy the product (no VERSION) (commit (no commit yet))")
    assert "Release notes: VERSION is missing (it holds the current version, e.g. 0.1.0)" in p["stops"]


def test_a_healthy_deploy_is_recorded_and_the_next_plan_starts_from_it(repo):
    record = repo / "results/deploy.json"
    first = dp.record(["backend", "frontend"], repo, record)
    assert first["version"] == "0.1.0" and json.loads(record.read_text())["history"] == []
    p = dp.collect(repo, record)
    assert p["deployed"]["commit"] == first["commit"] and p["rebuild"] == {}
    (repo / "app/backend/src/main.py").write_text("x = 3\n")
    _git(repo, "commit", "-qam", "three")
    assert dp.collect(repo, record)["services"] == ["backend"]
    dp.record(["backend"], repo, record)
    data = json.loads(record.read_text())
    assert data["rebuilt"] == ["backend"] and data["history"][0]["commit"] == first["commit"]


def test_the_command_line(repo, monkeypatch, capsys):
    real = _module()
    monkeypatch.setattr(real, "ROOT", repo)
    monkeypatch.setattr(real.collect, "__defaults__", (repo, repo / "deploy.json"))
    monkeypatch.setattr(real.record, "__defaults__", (repo, repo / "deploy.json"))
    assert real.main(["deploy_plan.py", "plan"]) == 0
    assert capsys.readouterr().out.startswith("Deploy shop 0.1.0")
    assert real.main(["deploy_plan.py", "plan", "--format", "shell"]) == 0
    assert capsys.readouterr().out.startswith("PLAN_STOPS=1\n")
    assert real.main(["deploy_plan.py", "plan", "--format"]) == 0  # an option without its value: the default
    assert capsys.readouterr().out.startswith("Deploy shop")
    assert real.main(["deploy_plan.py", "record", "backend", "worker"]) == 2
    assert "unknown service worker (known: backend, frontend)" in capsys.readouterr().err
    assert real.main(["deploy_plan.py", "record", "backend"]) == 0
    assert capsys.readouterr().out.startswith("Deployed: shop 0.1.0 (commit ")
    assert real.main(["deploy_plan.py"]) == 2


def test_run_as_a_script_it_exits_with_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["deploy_plan.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB), run_name="__main__")
    assert stopped.value.code == 2


def test_the_compose_settings_are_deep_copied_never_shared():
    p = _plan()
    compose = copy.deepcopy(COMPOSE)
    dp.rebuilds(compose, ["docker-compose.yml"])
    assert compose == COMPOSE and p["version"] == "0.2.0"
