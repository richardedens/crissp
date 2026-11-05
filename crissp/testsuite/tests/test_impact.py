"""crissp/check.sh tests what a change touches: the steps the product's map names for each kind of change, and the full
run when it cannot vouch. On a small example product (a shop with a backend and a frontend), and on this repository."""

import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location("impact_under_test", LIB / "impact.py")
impact = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impact)

SHOP = {"product": "Shop", "steps": [
    {"key": "backend", "label": "Backend", "dir": "app/backend", "run": "covered", "seconds": 40, "gate": True,
     "sources": ["app/backend/shop"]},
    {"key": "ruff", "label": "Ruff", "dir": "app/backend", "run": "ruff check .", "seconds": 2},
    {"key": "web", "label": "Frontend", "dir": "app/frontend", "run": "npm test", "seconds": 15},
    {"key": "chart", "label": "Chart", "run": "helm lint chart", "seconds": 3, "when": "chart/Chart.yaml"}],
    "paths": [{"match": "app/backend/", "steps": ["backend", "ruff"]}, {"match": "app/frontend/src/", "steps": ["web"]},
              {"match": "chart/", "steps": ["chart"]}],
    "shared": [{"match": "*/Dockerfile", "why": "what goes into an image"}, {"match": "*/package-lock.json", "why": "the locked dependencies"}],
    "notes": ["design/", "*/screens.html"]}


@pytest.fixture
def shop(tmp_path):
    root = tmp_path / "shop"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps(SHOP))
    return root


def plan(shop: Path, files: list[str]) -> dict:
    return impact.plan(files, impact.project.load(shop), shop)


@pytest.mark.parametrize("path", ["crissp/backlog/E1-quality.md", "crissp/backlog/FINDINGS.md", "docs/stories/01/STORY.md",
                                  "README.md", "CLAUDE.md", "crissp/CRISSP.md", "app/backend/README.md",
                                  "crissp/testsuite/coverage-baseline.json", "design/home.html", "app/screens.html"])
def test_notes_and_the_generated_baseline_need_nothing(shop, path):
    p = plan(shop, [path])
    assert p["nothing"] == [path] and p["minutes"] == 0 and not p["full"] and not p["suites"] and not p["light"]


def test_the_release_notes_are_a_light_check(shop):
    p = plan(shop, ["CHANGELOG.md", "VERSION"])
    assert p["light"] == ["release-notes"] and not p["suites"] and not p["full"] and p["minutes"] == 1


def test_a_part_runs_the_steps_its_rule_names_and_a_gated_part_brings_the_gate(shop):
    assert plan(shop, ["app/backend/shop/prices.py"])["suites"] == ["backend", "gate", "ruff"]
    assert plan(shop, ["app/frontend/src/App.tsx"])["suites"] == ["web"]
    p = plan(shop, ["app/frontend/src/App.tsx", "app/backend/tests/test_x.py", "app/backend/shop/a.py"])
    assert p["suites"] == ["backend", "gate", "ruff", "web"] and p["minutes"] == 1  # 59 seconds, in run order, once each


def test_a_step_that_is_not_there_now_cannot_vouch(shop):
    """The chart step exists while chart/Chart.yaml does: without it, a change there needs the full run."""
    assert plan(shop, ["chart/values.yaml"])["full"] == ["step chart: named in suites.json but not there now (its `when` is missing)"]
    (shop / "chart").mkdir()
    (shop / "chart/Chart.yaml").write_text("name: shop\n")
    assert plan(shop, ["chart/values.yaml"])["suites"] == ["chart"]


@pytest.mark.parametrize("path", [
    ".gitignore", "crissp/testsuite/suites.json", "crissp/testsuite/requirements.txt", "crissp/check.sh",
    "crissp/check-all.sh", "crissp/test.sh", "crissp/testsuite/run.sh", "crissp/testsuite/setup.sh",
    "crissp/testsuite/lib/run.py", "crissp/testsuite/lib/steps.sh", "crissp/testsuite/lib/project.py",
    "crissp/testsuite/lib/check.py", "crissp/testsuite/lib/impact.py", "crissp/testsuite/lib/release.py",
    "crissp/testsuite/lib/gate.py", "app/backend/Dockerfile", "app/frontend/package-lock.json"])
def test_shared_ground_asks_for_the_full_run_and_says_why(shop, path):
    """The framework's own guards everywhere, and what the product calls shared: it wins over its folder's rule."""
    kind, why = impact.classify(path, impact.project.load(shop))
    assert kind == "full" and why.startswith(f"{path}: ") and plan(shop, [path])["full"] == [why]


@pytest.mark.parametrize("path", ["app/frontend/index.html", "app/worker/main.py", "Makefile", "crissp/testsuite/other.txt"])
def test_anything_unmapped_is_shared_ground(shop, path):
    """A part the map does not name: the full run, never a guess."""
    assert impact.classify(path, impact.project.load(shop)) == \
        ("full", f"{path}: not mapped to a part of Shop (crissp/testsuite/suites.json, paths)")


def test_a_file_name_rule_matches_the_exact_name_anywhere(shop):
    conf = impact.project.load(shop)
    assert impact.classify("Dockerfile", conf)[0] == "full" and impact.classify("app/frontend/src/Dockerfile.ts", conf)[0] == "suites"
    assert impact.classify("app/frontend/src/NOTES.md", conf) == ("nothing", "")


@pytest.mark.parametrize("path, steps", [
    ("crissp/testsuite/lib/collect.py", ["tools", "gate"]), ("crissp/testsuite/tests/test_gate.py", ["tools", "gate"]),
    ("crissp/testsuite/dashboard/app.js", ["tools", "gate"]), ("crissp/testsuite/changes.json", ["tools", "gate"]),
    ("crissp/uxsuite/ux_team.py", ["tools", "gate"]), ("crissp/uxsuite/web/ux.js", ["tools", "gate"]),
    ("crissp/ux.sh", ["tools", "gate"]), ("crissp/tool/server.py", ["tools", "gate"]), ("crissp/look/look.css", ["tools", "gate"]),
    ("crissp/template/crissp/uxsuite/team.json", ["tools", "gate"]), ("crissp/testsuite/accepted-risks.json", ["audit"]),
    ("crissp/deploy/helm/app/values.yaml", ["deploy"]), ("crissp/deploy/check.sh", ["deploy"]), ("crissp/deploy.sh", ["deploy"]),
])
def test_this_repository_maps_its_own_parts(path, steps):
    """The framework is a product of its own: its tests, its deploy template, the audit of its pinned tools."""
    conf = impact.project.load(REPO)
    p = impact.plan([path], conf, REPO)
    assert not p["full"] and sorted(p["suites"]) == sorted(steps), p


def test_this_repository_s_mcp_registration_is_shared_ground():
    assert impact.classify(".mcp.json", impact.project.load(REPO))[0] == "full"


# ------------------------------------------------------------------------------------------------ the release notes

def _notes(tmp_path, version: str | None, changelog: str | None) -> list[str]:
    if version is not None:
        (tmp_path / "VERSION").write_text(version)
    if changelog is not None:
        (tmp_path / "CHANGELOG.md").write_text(changelog)
    return impact.check_release_notes(tmp_path)


def test_release_notes_that_name_the_version_and_say_what_changed_pass(tmp_path):
    assert _notes(tmp_path, "0.1.0\n", "# Changelog\n\n## 0.1.0 — unreleased\n\n- The test guards.\n\n## 0.0.9 — 2026-10-01\n- x\n") == []


def test_release_notes_problems_are_named(tmp_path):
    assert _notes(tmp_path, None, None) == ["VERSION is missing (it holds the current version, e.g. 0.1.0)"]
    assert _notes(tmp_path, "one", None) == ["VERSION: 'one' is not a version like 0.1.0",
                                            "CHANGELOG.md is missing (its top section is the release notes of VERSION)"]
    assert _notes(tmp_path, "0.2.0", "# Changelog\nnothing yet\n") == [
        "CHANGELOG.md has no section (## <version> — <date or unreleased>)"]
    why = _notes(tmp_path, "0.2.0", "## 0.1.0 — 2026-10-23\n\nwords, no bullet\n")
    assert why == ["CHANGELOG.md: the top section is '0.1.0 — 2026-10-23', it should name the version in VERSION (0.2.0)",
                   "CHANGELOG.md: the top section (0.1.0 — 2026-10-23) has no bullet: say what changed"]
    assert len(_notes(tmp_path, "0.2.0", "## unreleased\n* one\n")) == 1  # a title without a version


# ------------------------------------------------------------------------------------------------ git and the command line

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args], cwd=root,
                          check=True, capture_output=True, text=True).stdout


def test_the_plan_is_made_for_the_files_changed_since_the_certificate(shop, capsys):
    _git(shop, "init", "-q")
    _git(shop, "add", ".")
    _git(shop, "commit", "-qm", "one")
    first = _git(shop, "rev-parse", "HEAD").strip()
    (shop / "app/backend/shop").mkdir(parents=True)
    (shop / "app/backend/shop/x.py").write_text("x = 1\n")
    _git(shop, "add", ".")
    _git(shop, "commit", "-qm", "two")
    (shop / "crissp/testsuite/results").mkdir()
    (shop / "crissp/testsuite/results/release.json").write_text(json.dumps({"commit": first}))
    assert impact.main(["impact.py", "plan"], shop) == 0
    p = json.loads(capsys.readouterr().out)
    assert p["files"] == ["app/backend/shop/x.py"] and p["suites"] == ["backend", "gate", "ruff"]
    assert impact.main(["impact.py", "plan", "HEAD"], shop) == 0 and json.loads(capsys.readouterr().out)["files"] == []


def test_the_release_notes_command_and_the_usage(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path))
    assert impact.main(["impact.py", "release-notes"]) == 1 and "VERSION is missing" in capsys.readouterr().out
    (tmp_path / "VERSION").write_text("1.0.0")
    (tmp_path / "CHANGELOG.md").write_text("## 1.0.0 — unreleased\n- yes\n")
    assert impact.main(["impact.py", "release-notes"]) == 0 and capsys.readouterr().out == "release notes: ok\n"
    assert impact.main(["impact.py"]) == 2 and "impact.py plan" in capsys.readouterr().err


def test_run_as_a_script_it_exits_with_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["impact.py", "nonsense"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB / "impact.py"), run_name="__main__")
    assert stopped.value.code == 2
