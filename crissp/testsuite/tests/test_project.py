"""The product's parts come from one configuration (crissp/testsuite/suites.json, lib/project.py): every guard reads it,
so a mistake in it is caught with a message that says where, never a confusing run. On small example products."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(LIB))
spec = importlib.util.spec_from_file_location("project_under_test", LIB / "project.py")
project = importlib.util.module_from_spec(spec)
spec.loader.exec_module(project)

SHOP = {"product": "Shop", "steps": [
    {"key": "backend", "label": "Backend", "dir": "app/backend", "run": "covered -q", "gate": True, "sources": ["app/backend/shop"],
     "omit": ["*/tests/*"], "fail_under": 90},
    {"key": "lint", "label": "Lint", "run": "ruff check ."},
    {"key": "e2e", "label": "Browser", "run": "pytest e2e", "full_only": True, "when": "e2e/run.sh", "tests": ["e2e"]}],
    "paths": [{"match": "app/backend/", "steps": ["backend", "lint"]}], "shared": [{"match": "*/Dockerfile", "why": "an image"}],
    "notes": ["design/"], "setup": {"venvs": ["app/backend"], "needs": [{"command": "initdb", "hint": "brew install postgresql"}]}}


def shop(tmp_path: Path, conf: dict | None = None) -> Path:
    root = tmp_path / "shop"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(json.dumps(SHOP if conf is None else conf))
    return root


def test_the_project_is_crissp_root_or_the_current_directory(tmp_path, monkeypatch):
    """Never the place of the code: the engine and the project's data may live apart."""
    assert project.root({"CRISSP_ROOT": str(tmp_path)}) == tmp_path.resolve()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CRISSP_ROOT", raising=False)
    assert project.root() == tmp_path.resolve() and project.results(tmp_path) == tmp_path / "crissp/testsuite/results"


def test_a_configuration_with_every_default_filled_in(tmp_path):
    conf = project.load(shop(tmp_path))
    backend, lint, e2e = conf["steps"]
    assert backend == {"key": "backend", "label": "Backend", "dir": "app/backend", "run": "covered -q", "seconds": 10,
                       "gate": True, "coverage": True, "full_only": False, "sources": ["app/backend/shop"],
                       "omit": ["*/tests/*"], "fail_under": 90, "when": None, "tests": ["app/backend/tests"]}
    assert lint["dir"] == "." and lint["tests"] == ["./tests"] and not lint["coverage"] and lint["fail_under"] is None
    assert e2e["tests"] == ["e2e"] and e2e["full_only"] and e2e["when"] == "e2e/run.sh"
    assert conf["product"] == "Shop" and conf["monogram"] == "S" and conf["notes"] == ["design/"]
    assert conf["setup"] == {"venvs": ["app/backend"], "npm": [], "needs": [{"command": "initdb", "hint": "brew install postgresql"}]}
    assert conf["audit"] is None and conf["texts"] == {}
    unnamed = project.load(shop(tmp_path / "x", {"steps": []}))
    assert unnamed["product"] == "shop" and unnamed["monogram"] == "S"  # named after its folder


def test_the_gate_follows_the_last_gated_step_and_a_step_exists_while_its_path_does(tmp_path):
    root = shop(tmp_path)
    conf = project.load(root)
    assert [s["key"] for s in project.steps(conf, root)] == ["backend", "gate", "lint"]  # e2e/run.sh is not there
    (root / "e2e").mkdir()
    (root / "e2e" / "run.sh").write_text("")
    steps = project.steps(conf, root)
    assert [s["key"] for s in steps] == ["backend", "gate", "lint", "e2e"] and steps[1]["suites"] == ["backend"]
    plain = project.load(shop(tmp_path / "plain", {"steps": [{"key": "lint", "label": "Lint", "run": "x"}]}))
    assert [s["key"] for s in project.steps(plain, tmp_path)] == ["lint"]  # nothing gated: no gate


@pytest.mark.parametrize("conf, message", [
    ([], "suites.json must hold one JSON object"),
    ({"stpes": []}, "unknown field(s) stpes"),
    ({"steps": {}}, "steps must be a list"),
    ({"steps": [1]}, "steps[0] must be an object"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "colour": 1}]}, "steps[0]: unknown field(s) colour"),
    ({"steps": [{"key": "Big Step", "label": "A", "run": "x"}]}, "key must be a short name"),
    ({"steps": [{"key": "gate", "label": "A", "run": "x"}]}, "(not 'gate')"),
    ({"steps": [{"key": "a", "run": "x"}]}, "step a: label must be a text"),
    ({"steps": [{"key": "a", "label": "A", "run": " "}]}, "step a: run must be a text"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "seconds": 0}]}, "seconds must be a whole number"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "seconds": True}]}, "seconds must be a whole number"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "fail_under": 101}]}, "fail_under must be a percentage"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "fail_under": False}]}, "fail_under must be a percentage"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "gate": "yes"}]}, "gate must be true or false"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "gate": True}]}, "names its sources"),
    ({"steps": [{"key": "a", "label": "A", "run": "x", "sources": "src"}]}, "sources must be a list of texts"),
    ({"steps": [{"key": "a", "label": "A", "run": "x"}, {"key": "a", "label": "B", "run": "y"}]}, "step a is named twice"),
    ({"paths": {}}, "paths must be a list"),
    ({"paths": [{"steps": ["a"]}]}, "paths[0] needs a match"),
    ({"paths": [{"match": "src/", "steps": []}]}, "paths src/: steps must name at least one step"),
    ({"paths": [{"match": "src/", "steps": ["nope"]}]}, "paths src/: unknown step nope"),
    ({"shared": [{"match": "x"}]}, "shared x: why must say why"),
    ({"setup": []}, "setup must be an object"),
    ({"setup": {"needs": [{"command": "helm"}]}}, "setup.needs must be a list of {command, hint}"),
    ({"setup": {"venvs": [""]}}, "setup.venvs must be a list of texts"),
    ({"audit": []}, "audit must be an object"),
    ({"texts": []}, "texts must be an object"),
])
def test_a_mistake_says_where_and_what(conf, message):
    with pytest.raises(project.ConfigError) as wrong:
        project.parse(conf)
    assert message in str(wrong.value)


def test_a_missing_or_broken_file_says_how_to_start(tmp_path):
    with pytest.raises(project.ConfigError, match="suites.json is missing: describe the product's parts there"):
        project.load(tmp_path)
    (tmp_path / "crissp" / "testsuite").mkdir(parents=True)
    (tmp_path / "crissp" / "testsuite" / "suites.json").write_text("{")
    with pytest.raises(project.ConfigError, match="is not valid JSON"):
        project.load(tmp_path)


def test_this_repository_is_a_product_of_its_own():
    """The framework's own parts: its tests (100% lines and branches for what decides what is green), the deploy
    template's check when it is there, the CVE audit of the pinned tools."""
    conf = project.load(REPO)
    tools = conf["steps"][0]
    assert conf["product"] == "C.R.I.S.S.P." and tools["key"] == "tools" and tools["gate"] and tools["fail_under"] == 100
    assert tools["sources"] == ["crissp/testsuite/lib", "crissp/tool", "crissp/uxsuite"] and tools["omit"] == ["*/tests/*"]
    deploy = next(s for s in conf["steps"] if s["key"] == "deploy")
    assert deploy["run"] == "crissp/deploy/check.sh" and deploy["when"] == "crissp/deploy/check.sh"


def test_the_command_line_checks_the_configuration(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CRISSP_ROOT", str(shop(tmp_path)))
    assert project.main(["project.py", "check"]) == 0 and capsys.readouterr().out == "Shop: backend, gate, lint\n"
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path / "nowhere"))
    assert project.main(["project.py", "check"]) == 1 and "suites.json is missing" in capsys.readouterr().err
    assert project.main(["project.py"]) == 2


def test_run_as_a_script_it_says_how_to_use_it(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["project.py"])
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(LIB / "project.py"), run_name="__main__")
    assert stopped.value.code == 2


def test_the_guards_speak_the_crissp_command_when_they_run_as_it():
    """F-04: run by the `crissp` command (CRISSP_COMMAND), a guard names `crissp check-all`, not a script path."""
    import io
    said = "Run crissp/check-all.sh, then crissp/check.sh; crissp/deploy.sh --cluster; crissp/ux.sh --shoot w; crissp/test.sh --dashboard"
    assert project.speak(said, {}) == said  # in a repository that carries the scripts: as it is
    assert project.speak(said, {"CRISSP_COMMAND": "crissp"}) == (
        "Run crissp check-all, then crissp check; crissp deploy --cluster; crissp ux --shoot w; crissp dashboard")
    out = io.StringIO()
    stream = project.Speaking(out, {"CRISSP_COMMAND": "crissp"})
    assert stream.write("Green: crissp/deploy.sh may go.\n") == len("Green: crissp/deploy.sh may go.\n")
    stream.flush()
    assert out.getvalue() == "Green: crissp deploy may go.\n" and stream.getvalue() == out.getvalue()  # the rest passes through
