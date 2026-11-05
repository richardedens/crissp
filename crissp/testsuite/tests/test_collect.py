"""The dashboard's data (lib/collect.py) is what the product owner reads after a run: every test with what it proves and
where it is, coverage per file, each change with its proof and the code of its fix, threats and capabilities with their
tests, journeys with their state, the backlog with what came from the UX suite. Wrong data here would make a red run
look green, so it is tested on a small example product."""

import importlib.util
import json
import runpy
import sys
from pathlib import Path

import pytest

COLLECT = Path(__file__).resolve().parents[1] / "lib" / "collect.py"
REPO = Path(__file__).resolve().parents[3]
# an example product: an API with coverage, a web part and an admin part without, and a browser suite
SHOP = {"product": "Shop", "monogram": "S", "texts": {"e2e": "the shop in a browser"}, "steps": [
    {"key": "api", "label": "API", "dir": "api", "run": "covered", "coverage": True, "sources": ["api"]},
    {"key": "e2e", "label": "E2E", "dir": "crissp/testsuite/e2e", "run": "pytest", "tests": ["crissp/testsuite/e2e"]},
    {"key": "web", "label": "Web", "dir": "web", "run": "npm test", "coverage": True, "sources": ["web/src"]},
    {"key": "admin", "label": "Admin", "dir": "admin", "run": "true", "gate": True, "sources": ["admin"]}]}


def _module():
    sys.path.insert(0, str(COLLECT.parent))
    spec = importlib.util.spec_from_file_location("collect_under_test", COLLECT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def collect(tmp_path):
    """The module configured for a product in tmp_path/repo: it reads and writes only there."""
    module = _module()
    root = tmp_path / "repo"
    suite = root / "crissp" / "testsuite"
    (suite / "results").mkdir(parents=True)
    (suite / "suites.json").write_text(json.dumps(SHOP))
    module.configure(root)
    module.SUITE = suite  # where the tests write the product's own files (changes.json, threats.json)
    return module


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


API_XML = """<testsuites><testsuite>
<testcase classname="tests.test_billing" name="test_prorated" time="0.12345"/>
<testcase classname="tests.test_billing" name="test_refused" time="0.5"><failure message="assert 403 == 200">long trace</failure></testcase>
<testcase classname="tests.test_billing" name="test_param[a]" time="0.1"><error message="boom"/></testcase>
<testcase classname="tests.test_billing" name="test_later"><skipped message="not today"/></testcase>
<testcase classname="tests.test_broken" name="test_x" time="1"/>
<testcase classname="tests.test_absent" name="test_y" time="1"/>
</testsuite></testsuites>"""


def _api_tests(collect):
    root = collect.ROOT
    _write(root / "api" / "tests" / "test_billing.py", '"""Billing per day."""\n\n\ndef test_prorated():\n    """A third of the month costs a third."""\n\n\n'
                                                         'class Helper:\n    pass\n\n\ndef helper():\n    pass\n')
    _write(root / "api" / "tests" / "test_broken.py", "def test_x(:\n")
    _write(collect.RESULTS / "api.xml", API_XML)
    _write(collect.SUITE / "e2e" / "test_screens.py", 'def test_login():\n    """The sign-in screen."""\n')
    _write(collect.RESULTS / "e2e.xml", '<testsuite><testcase classname="test_screens" name="test_login" time="2"/></testsuite>')


def test_every_test_with_its_result_what_it_proves_and_where_it_is(collect):
    _api_tests(collect)
    assert collect.tests_of("web") == []  # a suite that did not run has no tests (not an error)
    tests = {t["name"]: t for t in collect.tests_of("api")}
    ok = tests["test_prorated"]
    assert ok["status"] == "passed" and ok["time"] == 0.123 and ok["doc"] == "A third of the month costs a third."
    assert ok["moduleDoc"] == "Billing per day." and ok["line"] == 4 and ok["file"] == "api/tests/test_billing.py" and ok["id"] == "test_billing::test_prorated"
    assert tests["test_refused"]["status"] == "failed" and tests["test_refused"]["detail"] == "assert 403 == 200\nlong trace"
    assert tests["test_param[a]"]["status"] == "failed" and tests["test_param[a]"]["detail"] == "boom"
    assert tests["test_later"]["status"] == "skipped" and tests["test_later"]["time"] == 0
    assert tests["test_x"]["doc"] == "" and tests["test_x"]["moduleDoc"] == ""  # a file that does not parse: no docs, still listed
    assert tests["test_y"]["line"] == 0  # a file that is gone
    e2e = collect.tests_of("e2e")
    assert e2e[0]["file"] == "crissp/testsuite/e2e/test_screens.py" and e2e[0]["doc"] == "The sign-in screen."


def test_a_test_file_is_found_in_the_step_s_test_folders(collect):
    _write(collect.ROOT / "crissp/testsuite/e2e/test_cart.py", "")
    assert collect._test_file("e2e", "test_cart.TestCart") == ("test_cart", collect.ROOT / "crissp/testsuite/e2e/test_cart.py")
    assert collect._test_file("e2e", "") == ("", collect.ROOT / "crissp/testsuite/e2e/.py")  # nothing to go on: still a place
    collect.SUITES["bare"] = ("Bare", [], collect.ROOT / "bare")
    assert collect._test_file("bare", "x.test_y") == ("test_y", collect.ROOT / "bare/test_y.py")  # no folders: its own
    assert collect._where(Path("/elsewhere/t.py")) == "/elsewhere/t.py"


def test_coverage_per_file_and_in_total(collect):
    assert collect.coverage("api") is None
    (collect.ROOT / "api").mkdir()
    _write(collect.RESULTS / "coverage-api.json", json.dumps({
        "files": {str(collect.ROOT / "api/b.py"): {"summary": {"num_statements": 10, "covered_lines": 9, "missing_lines": 1, "percent_covered": 90.0,
                                              "num_branches": 4, "covered_branches": 2}, "missing_lines": [7], "missing_branches": [[3, 5]]},
                  "a.py": {"summary": {"num_statements": 0, "covered_lines": 0, "missing_lines": 0, "percent_covered": 100.0}}},
        "totals": {"num_statements": 10, "covered_lines": 9, "percent_covered": 91.234}}))
    out = collect.coverage("api")
    assert [f["file"] for f in out["files"]] == ["api/a.py", "api/b.py"]  # sorted, by their path in the product (absolute or not)
    a, b = out["files"]
    assert a["linePercent"] == 100.0 and a["branchPercent"] == 100.0 and a["branches"] == 0  # nothing to cover is fully covered
    assert b["linePercent"] == 90.0 and b["branchPercent"] == 50.0 and b["missingLines"] == [7] and b["missingBranches"] == [[3, 5]]
    assert out["percent"] == 91.2 and out["linePercent"] == 90.0 and out["branchPercent"] == 100.0 and out["full"] == 1


def test_the_code_of_a_fix_is_shown_from_its_symbol(collect):
    _write(collect.ROOT / "shop" / "x.py", "import os\n\n\ndef fixed(a):\n    if a:\n        return (\n            1\n        )\n    return 2\n\n\ndef other():\n    pass\n")
    found = collect.locate("shop/x.py", "def fixed")
    assert found["found"] and found["line"] == 4 and found["code"] == "def fixed(a):\n    if a:\n        return (\n            1\n        )\n    return 2"
    assert collect.locate("shop/x.py", "def gone") | {"abs": ""} == {"file": "shop/x.py", "symbol": "def gone", "line": 0, "found": False, "code": "", "abs": ""}
    assert collect.locate("shop/none.py", "def fixed")["found"] is False
    _write(collect.ROOT / "shop" / "long.py", "def long():\n" + "    x = 1\n" * 60)
    assert collect.locate("shop/long.py", "def long")["code"].count("\n") == 35  # never more than a screen of code
    _write(collect.ROOT / "shop" / "end.py", "x = 1\ndef last():\n    pass")
    assert collect.locate("shop/end.py", "def last")["code"] == "def last():\n    pass"  # the file ends inside the block


def _journey(collect, jid, lang, level, order, status, caps=()):
    _write(collect.RESULTS / "journeys" / jid / lang / "journey.json",
           json.dumps({"id": jid, "lang": lang, "level": level, "order": order, "status": status, "capabilities": list(caps)}))


def test_journeys_in_learning_order_with_the_failure_screen(collect):
    _journey(collect, "pro", "nl", "professional", 1, "verified")
    _journey(collect, "start", "en", "beginner", 2, "failed")
    _journey(collect, "start", "nl", "beginner", 2, "verified")
    _journey(collect, "first", "nl", "beginner", 1, "failed")
    _write(collect.RESULTS / "journeys-run" / "start" / "en" / "failure.png", "png")
    _write(collect.RESULTS / "journeys-run" / "start" / "nl" / "failure.png", "png")  # left from an earlier run: it passed now
    out = collect._journeys()
    assert [(j["id"], j["lang"]) for j in out] == [("first", "nl"), ("start", "en"), ("start", "nl"), ("pro", "nl")]
    by = {(j["id"], j["lang"]): j for j in out}
    assert by[("start", "en")]["failure"] == "../results/journeys-run/start/en/failure.png"
    assert by[("start", "nl")]["failure"] is None and by[("first", "nl")]["failure"] is None  # no screen was kept
    assert by[("pro", "nl")]["base"] == "../results/journeys/pro/nl/" and "page" not in by[("pro", "nl")]


def test_capabilities_with_their_tests_journeys_and_threats(collect):
    assert collect._capabilities({}, {"boundaries": []}) == []  # no capability map yet
    _write(collect.RESULTS / "capabilities.json", json.dumps([
        {"id": "auth:api_key", "tests": ["test_keys"]},
        {"id": "endpoint:rest", "tests": ["test_rest", "test_rest_more"]},
        {"id": "table:rows", "tests": []}]))
    by_ref = {"test_keys": [{"id": "test_keys::a", "status": "passed"}],
              "test_rest": [{"id": "test_rest::a", "status": "passed"}, {"id": "test_rest::b", "status": "failed"}]}
    threats = {"boundaries": [{"threats": [{"id": "G01", "applies": ["auth:*", "endpoint:*"]}, {"id": "G02"}]}]}
    journeys = [{"id": "keys", "status": "verified", "capabilities": ["auth:api_key"]},
                {"id": "rest", "status": "verified", "capabilities": ["endpoint:rest"]},
                {"id": "rest", "status": "failed", "capabilities": ["endpoint:rest"]}]
    caps = {c["id"]: c for c in collect._capabilities(by_ref, threats, journeys)}
    assert caps["auth:api_key"].items() >= {"tested": "passed", "documented": "passed", "journeys": ["keys"], "threats": ["G01"], "testCount": 1}.items()
    assert caps["endpoint:rest"]["tested"] == "failed" and caps["endpoint:rest"]["failed"] == ["test_rest::b"]
    assert caps["endpoint:rest"]["documented"] == "failed"  # one language of its journey failed
    assert caps["table:rows"].items() >= {"tested": "untested", "documented": "missing", "threats": [], "journeys": []}.items()


def _world(collect):
    _api_tests(collect)
    suite = collect.SUITE
    _write(collect.ROOT / "api" / "billing.py", "def fixed():\n    return 1\n")
    _write(suite / "changes.json", json.dumps({"gaps": ["one known gap"], "changes": [
        {"id": "c-green", "tests": ["test_billing::test_prorated"], "e2e": ["test_login"], "screenshots": ["login", "absent"],
         "sources": [{"file": "api/billing.py", "symbol": "def fixed"}]},
        {"id": "c-red", "tests": ["test_billing"], "e2e": [], "sources": [{"file": "api/billing.py", "symbol": "def renamed"}]},
        {"id": "c-param", "tests": ["test_billing::test_param"], "e2e": [], "sources": []},
        {"id": "c-missing", "tests": ["test_nowhere"], "e2e": ["test_nowhere_either"], "sources": []},
        {"id": "c-none", "tests": [], "e2e": [], "sources": []}]}))
    _write(collect.RESULTS / "e2e" / "shots" / "login.png", "png")


def test_the_dashboard_data_from_a_whole_run(collect, capsys):
    _world(collect)
    _write(collect.RESULTS / "steps.json", json.dumps([{"name": "api", "status": "failed"}, {"name": "web", "status": "passed"}]))
    _write(collect.RESULTS / "gate.json", json.dumps({"ok": True}))
    _write(collect.SUITE / "threats.json", json.dumps({"boundaries": [{"threats": [
        {"id": "T1", "tests": ["test_billing::test_prorated"]}, {"id": "T2", "tests": ["test_billing::test_refused"]},
        {"id": "T3", "tests": ["test_nowhere"]}, {"id": "T4", "tests": []}]}]}))
    assert collect.main(collect.ROOT) == 0
    text = (collect.RESULTS / "data.js").read_text()
    assert text.startswith("window.SUITE = ") and text.endswith(";\n")
    data = json.loads(text[len("window.SUITE = "):-2])
    changes = {c["id"]: c for c in data["changes"]}
    assert changes["c-green"]["verdict"] == "passed" and changes["c-green"]["screenshots"] == ["login.png"]  # only shots that exist
    assert changes["c-green"]["proof"][1] == {"ref": "test_login", "tests": ["test_screens::test_login"], "status": "passed", "e2e": True}
    assert changes["c-green"]["sources"][0]["code"] == "def fixed():\n    return 1"
    assert changes["c-red"]["verdict"] == "failed"  # a module reference: every test in it counts, and one failed
    assert changes["c-param"]["verdict"] == "failed"  # a parametrised test answers to its base name
    assert changes["c-missing"]["verdict"] == "missing" and changes["c-none"]["verdict"] == "missing"  # no proof is no green
    assert [t["status"] for t in data["threats"]["boundaries"][0]["threats"]] == ["passed", "failed", "missing", "untested"]
    api = data["suites"]["api"]
    assert (api["tests"], api["passed"], api["failed"], api["skipped"]) == (6, 3, 2, 1) and data["suites"]["web"]["tests"] == 0
    assert data["gate"] == {"ok": True} and data["gaps"] == ["one known gap"] and data["screenshots"] == ["login.png"]
    assert data["coverage"] == {"api": None, "web": None, "admin": None} and data["capabilities"] == []
    assert data["product"] == "Shop" and data["unitSuites"] == ["api", "web", "admin"] and data["texts"] == {"e2e": "the shop in a browser"}
    out = capsys.readouterr().out
    assert "7 tests, 5 changes, 3 failures" in out  # two failed tests and one failed step
    assert "source not found: c-red: api/billing.py · def renamed" in out


def test_a_first_run_without_steps_gate_threats_or_shots(collect, capsys):
    assert collect.main(collect.ROOT) == 0  # no changes.json yet either
    data = json.loads((collect.RESULTS / "data.js").read_text()[len("window.SUITE = "):-2])
    assert data["steps"] == [] and data["gate"] is None and data["threats"] == {"boundaries": []} and data["screenshots"] == []
    assert data["gaps"] == [] and data["tests"] == [] and "0 tests, 0 changes, 0 failures" in capsys.readouterr().out


def test_the_product_comes_from_suites_json(collect, capsys):
    """The product names itself, its steps and which measure coverage; the same dashboard then shows it."""
    assert collect.SUITES["e2e"] == ("E2E", [collect.ROOT / "crissp/testsuite/e2e"], collect.ROOT / "crissp/testsuite/e2e")
    assert collect.COVERAGE == ["api", "web", "admin"]  # a gated step measures coverage too
    assert collect._product() == {"product": "Shop", "monogram": "S", "texts": {"e2e": "the shop in a browser"},
                                  "coverageKeys": ["api", "web", "admin"], "unitSuites": ["api", "web", "admin"]}
    _write(collect.RESULTS / "sessions" / "summary.json", json.dumps({"sessions": 2, "tokens": "1.2M"}))
    assert collect._product()["sessions"] == {"href": "../results/sessions/index.html", "sessions": 2, "tokens": "1.2M"}
    (collect.ROOT / "crissp/testsuite/suites.json").write_text("{")
    assert collect.main(collect.ROOT) == 1 and "dashboard data: crissp/testsuite/suites.json is not valid JSON" in capsys.readouterr().err


def test_this_repository_s_dashboard_names_it_and_its_steps():
    module = _module()
    module.configure(REPO)
    assert module.CONFIG["product"] == "C.R.I.S.S.P." and module.COVERAGE == ["tools"]
    assert module.SUITES["tools"][1] == [REPO / "crissp/testsuite/tests", REPO / "crissp/uxsuite/tests"]


def test_this_testsuite_s_steps_come_from_the_step_log(collect):
    """steps.json as a list with the logs (a product's own runner), or run.py's {step: status} with steps.jsonl."""
    assert collect._steps() == []
    _write(collect.RESULTS / "steps.json", json.dumps({"tools": "passed"}))
    assert collect._steps() == []
    _write(collect.RESULTS / "steps.jsonl", json.dumps({"key": "tools", "status": "passed"}) + "\n\n"
           + json.dumps({"key": "lint", "status": "failed", "log": "kept"}) + "\n" + json.dumps({"key": "tsc"}))
    _write(collect.RESULTS / "tools.log", "x" * 30000)
    tools, lint, tsc = collect._steps()
    assert len(tools["log"]) == 20000 and lint["log"] == "kept" and tsc["log"] == ""
    _write(collect.RESULTS / "steps.json", json.dumps([{"key": "api", "log": "l"}]))
    assert collect._steps() == [{"key": "api", "log": "l"}]


def test_a_change_without_e2e_refs_is_proven_by_its_tests(collect):
    _api_tests(collect)
    _write(collect.SUITE / "changes.json", json.dumps({"changes": [{"id": "x", "sources": [], "tests": [
        "test_billing::test_prorated", "test_billing.py::test_prorated", "test_billing.py"]}],
                                                         "gaps": []}))
    assert collect.main(collect.ROOT) == 0
    data = json.loads((collect.RESULTS / "data.js").read_text().removeprefix("window.SUITE = ").rstrip(";\n"))
    assert data["changes"][0]["verdict"] == "failed"  # test_billing as a whole has a failing test
    assert [p["status"] for p in data["changes"][0]["proof"]] == ["passed", "passed", "failed"]


def test_it_runs_as_a_script_for_the_project_it_is_given(tmp_path, monkeypatch):
    """Run as a script it writes the dashboard data of the project CRISSP_ROOT names (here a throwaway one)."""
    root = tmp_path / "repo"
    (root / "crissp/testsuite").mkdir(parents=True)
    (root / "crissp/testsuite/suites.json").write_text(json.dumps({"product": "Tiny"}))
    monkeypatch.setenv("CRISSP_ROOT", str(root))
    monkeypatch.setattr(sys, "argv", ["collect.py"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(COLLECT), run_name="__main__")
    assert stop.value.code == 0 and (root / "crissp/testsuite/results/data.js").read_text().startswith("window.SUITE = ")


def test_the_backlog_board_reads_epics_features_and_pbis_through_the_crissp_tool(collect, monkeypatch, tmp_path):
    root = collect.ROOT
    tool = collect.TOOL
    monkeypatch.setattr(collect, "TOOL", tmp_path / "no-tool.py")
    assert collect._backlog() is None  # without the crissp tool there is no board
    monkeypatch.setattr(collect, "TOOL", tool)
    b = root / "crissp" / "backlog"
    _write(b / "E1-quality.md", "# E1 · Quality\n\nWhy: w\n\n### E1-01 · The gate   [doing] [M]\nWhy        x\n")
    _write(b / "E8-repair.md", "# E8 · Repair\n\nWhy: w\n\n## E8-F1 · Detect   [todo]\nWhy        y\n\n"
                               "### E8-F1-01 · Layout   [review] [S]\nWhy        z\nDepends    UX\n           proposal `home#v2` (approved 2026-11-05)\n\n## E8-F2 · Move   [todo]\nWhy        v\n")
    _write(b / "done" / "E0-baseline.md", "# E0 · Baseline\n\n### E0-01 · All there   [done] [S]\n")
    _write(b / "notes.md", "not an epic\n")
    _write(b / "E9-draft.md", "no heading yet\n")  # a file without its epic heading is not on the board
    board = collect._backlog()
    assert board["statuses"] == ["todo", "doing", "review", "done", "parked"]
    assert [(e["id"], e["title"], e["done"]) for e in board["epics"]] == [("E1", "Quality", False), ("E8", "Repair", False), ("E0", "Baseline", True)]
    e1, e8, e0 = board["epics"]
    assert e1["features"] == [] and [i["id"] for i in e1["items"]] == ["E1-01"] and e1["file"] == "crissp/backlog/E1-quality.md"
    assert [(f["id"], [p["id"] for p in f["pbis"]]) for f in e8["features"]] == [("E8-F1", ["E8-F1-01"]), ("E8-F2", [])]
    assert e8["items"] == [] and e8["features"][0]["pbis"][0]["status"] == "review"
    assert e8["features"][0]["pbis"][0]["ux"] == "home#v2" and "ux" not in e1["items"][0]  # from an approved UX design
    assert [i["id"] for i in e0["items"]] == ["E0-01"]
    _write(collect.SUITE / "changes.json", '{"changes": []}')
    collect.main(root)
    assert '"backlog": {"epics": [{"id": "E1"' in (collect.RESULTS / "data.js").read_text()
