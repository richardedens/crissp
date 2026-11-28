"""The UX suite in the local server (api.handle): its page, its state, the team's files (a design in a sandbox of its
own), and writes only from its own page. A real HTTP server on 127.0.0.1, an example product, a team of stand-ins."""

import http.server
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PROPOSAL, REPO, ROUND, add_shots, finish, product, ux_config, ux_team  # noqa: F401

# isort: split
import api  # ux_kit put the uxsuite on sys.path
import ux_map


@pytest.fixture
def site(product, monkeypatch):
    monkeypatch.setattr(ux_config, "default_suite", lambda: product)

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            api.handle(self, "GET")

        def do_POST(self):
            api.handle(self, "POST")

        def log_message(self, *a):
            pass

    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    yield product, base
    httpd.shutdown()
    httpd.server_close()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def get(url):
    try:
        with urllib.request.build_opener(NoRedirect).open(url) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def post(base, path, body, origin=None, raw=None):
    data = raw if raw is not None else json.dumps(body).encode()
    req = urllib.request.Request(
        base + path,
        data=data,
        method="POST",
        headers={"Origin": base if origin is None else origin, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def test_the_page_is_served_in_the_shared_look(site):
    _, base = site
    code, headers, body = get(base + "/ux")
    assert code == 302 and headers["Location"] == "/ux/"
    code, headers, body = get(base + "/ux/")
    page = body.decode()
    assert code == 200 and headers["Content-Type"].startswith("text/html") and "Content-Security-Policy" not in headers
    assert "../../look/look.css" in page and "../../look/look.js" in page and "../../look/water.js" in page
    assert 'data-current="ux"></nav>' in page and 'id="theme"' in page and "http" not in page.replace("http-equiv", "")
    for name, kind in (("ux.js", "text/javascript"), ("ux.css", "text/css")):
        code, headers, body = get(base + "/ux/" + name)
        assert code == 200 and headers["Content-Type"].startswith(kind) and b"http" not in body
    assert get(base + "/ux/../api.py")[0] == 404 and get(base + "/ux/nothing.js")[0] == 404
    assert get(base + "/ux/team.json")[0] == 404  # only the page's own files


def test_the_state_holds_every_walk_with_its_rounds_designs_verdicts_and_pbi(site):
    suite, base = site
    add_shots(suite)
    finish(suite, "round", "first-visit", 1, ROUND)
    finish(suite, "proposal", "first-visit", 1, PROPOSAL)
    code, _, body = get(base + "/ux/api/state")
    s = json.loads(body)
    assert code == 200 and s["product"] == "Example Shop" and s["monogram"] == "E" and len(s["personas"]) == 3
    w = s["walks"][0]
    assert w["id"] == "first-visit" and w["steps"] == 6 and w["rounds"][0]["result"] == ROUND
    assert w["proposals"][0]["verdict"] is None and w["proposals"][0]["pbi"] is None
    assert s["team"]["text"] == "The team is free (up to 3 at once)." and s["queue"] == [] and s["verdicts"] == {}
    code, out = post(base, "/ux/api/verdict", {"id": "first-visit#v1", "verdict": "approve"})
    assert code == 200 and out["pbi"] == "E1-F1-01" and out["line"]["verdict"] == "approve"
    p = json.loads(get(base + "/ux/api/state")[2])["walks"][0]["proposals"][0]
    assert p["pbi"] == "E1-F1-01" and p["verdict"]["verdict"] == "approve"


def test_the_state_holds_the_map_once_the_product_was_mapped(site):
    suite, base = site
    assert json.loads(get(base + "/ux/api/state")[2])["map"] is None
    ux_map.build(suite, ux_config.load(suite))
    assert [s["key"] for s in json.loads(get(base + "/ux/api/state")[2])["map"]["screens"]] == ["/"]


def test_the_state_holds_the_discovery_rounds_with_the_verdicts_on_their_needs(site):
    suite, base = site
    assert json.loads(get(base + "/ux/api/state")[2])["discovery"] == []
    finish(suite, "discovery", "product", 1, {"summary": "s", "jobs": [], "needs": [{"title": "Pay", "detail": "d"}]})
    assert post(base, "/ux/api/verdict", {"id": "product/d1/n0", "verdict": "reject", "reason": "no"})[0] == 200
    d = json.loads(get(base + "/ux/api/state")[2])["discovery"][0]
    assert d["key"] == "product#d1" and d["result"]["needs"][0]["title"] == "Pay"
    assert d["needs"] == [
        {
            "id": "product/d1/n0",
            "verdict": {
                "id": "product/d1/n0",
                "level": "need",
                "verdict": "reject",
                "reason": "no",
                "title": "Pay",
                "at": d["needs"][0]["verdict"]["at"],
            },
        }
    ]


def test_the_state_says_when_a_walk_was_shot_and_what_was_built(site):
    suite, base = site
    w = json.loads(get(base + "/ux/api/state")[2])["walks"][0]
    assert w["shot_at"] is None and w["need"] is None
    add_shots(suite)
    finish(suite, "proposal", "first-visit", 1, PROPOSAL)
    w = json.loads(get(base + "/ux/api/state")[2])["walks"][0]
    assert w["shot_at"] == ux_team.shot_at(suite, "first-visit") and w["proposals"][0]["built"] is None


def test_a_broken_configuration_or_a_missing_tool_is_told_not_crashed(site):
    suite, base = site
    (suite.root / "crissp" / "tool" / "server.py").unlink()
    assert json.loads(get(base + "/ux/api/state")[2])["walks"][0]["proposals"] == []
    (suite.here / "team.json").write_text("{")
    assert json.loads(get(base + "/ux/api/state")[2])["error"].startswith("team.json is not valid JSON")


def test_the_team_s_files_are_served_and_a_design_only_in_a_sandbox(site):
    suite, base = site
    add_shots(suite)
    finish(suite, "proposal", "first-visit", 1, PROPOSAL)
    code, headers, body = get(base + "/ux/results/proposals/first-visit/v1/mockup.html")
    assert code == 200 and headers["Content-Security-Policy"].startswith("sandbox allow-scripts") and b"after" in body
    code, headers, body = get(base + "/ux/results/shots/first-visit/laptop/01-the-first-screen.png")
    assert code == 200 and headers["Content-Type"] == "image/png"
    crawl = suite.results / "map" / "crawl" / "laptop"
    crawl.mkdir(parents=True)
    (crawl / "01.png").write_bytes(b"\x89PNG stand-in")
    assert get(base + "/ux/results/map/crawl/laptop/01.png")[0] == 200
    for path in (
        "/ux/results/decisions.jsonl",
        "/ux/results/proposals/first-visit/v1/proposal.json",
        "/ux/results/../team.json",
        "/ux/results/queue.jsonl",
    ):
        assert get(base + path)[0] == 404, path


def test_a_write_only_from_the_suite_s_own_page(site):
    suite, base = site
    add_shots(suite)
    code, out = post(base, "/ux/api/request", {"kind": "round", "walk": "first-visit"}, origin="http://evil.example")
    assert code == 403 and "own page" in out["error"] and ux_team.popen.started == []
    assert post(base, "/ux/api/other", {})[0] == 404
    code, out = post(base, "/ux/api/request", {"kind": "round", "walk": "first-visit"})
    assert code == 200 and out["started"]["version"] == 1 and len(ux_team.popen.started) == 1


@pytest.mark.parametrize(
    "path, body, raw, says",
    [
        ("/ux/api/request", {"kind": "round", "walk": "nowhere"}, None, "unknown walk"),
        ("/ux/api/request", {"kind": "round", "walk": "first-visit", "focus": "x" * 1501}, None, "focus is too long"),
        ("/ux/api/request", None, b"[1]", "send one JSON object"),
        ("/ux/api/request", None, b"{", "Expecting"),
        ("/ux/api/request", None, b"x" * 20001, "too large"),
        ("/ux/api/verdict", {"id": "first-visit#v9", "verdict": "approve"}, None, "unknown design"),
        (
            "/ux/api/persona",
            {"persona": {"name": "Bo", "role": "x", "brief": "y", "device": "watch"}},
            None,
            "device must be one of",
        ),
        ("/ux/api/persona", {"remove": "nobody"}, None, "no persona 'nobody'"),
        ("/ux/api/persona", {"persona": "Bo"}, None, "send {persona: {…}} or {remove: <key>}"),
        ("/ux/api/rule", {"rule": {"title": "A", "text": ""}}, None, "text must be a text"),
        ("/ux/api/rule", {"remove": "nothing"}, None, "no rule 'nothing'"),
        ("/ux/api/rule", {}, None, "send {rule: {…}} or {remove: <id>}"),
    ],
)
def test_a_wrong_write_is_a_clear_400(site, path, body, raw, says):
    _, base = site
    code, out = post(base, path, body, raw=raw)
    assert code == 400 and says in out["error"]


def test_the_worker_takes_the_queue_and_survives_a_bad_moment(product, capsys):
    add_shots(product)
    ux_team.enqueue(product, "round", "first-visit")
    stop = api.start_worker(product, interval=0.01)
    deadline = time.time() + 5
    while not ux_team.popen.started and time.time() < deadline:
        time.sleep(0.01)
    assert ux_team.queue(product) == [] and len(ux_team.popen.started) == 1
    (product.here / "team.json").write_text("{")
    time.sleep(0.05)
    stop.set()
    assert "ux queue: team.json is not valid JSON" in capsys.readouterr().err


def test_by_default_it_is_the_suite_of_the_project_it_works_for(monkeypatch, tmp_path):
    """CRISSP_ROOT names the project (the scripts export it); without it, the current directory. Never api.py's place."""
    monkeypatch.setenv("CRISSP_ROOT", str(REPO))
    suite = ux_config.default_suite()
    assert suite.root == REPO.resolve() and suite.here == REPO.resolve() / "crissp" / "uxsuite"
    assert ux_config.load(suite)["product"] == "C.R.I.S.S.P."
    monkeypatch.delenv("CRISSP_ROOT")
    monkeypatch.chdir(tmp_path)
    assert ux_config.default_suite().root == tmp_path.resolve()
    assert ux_config.project_root({"CRISSP_ROOT": str(tmp_path / "x")}) == (tmp_path / "x").resolve()


def test_loaded_by_its_path_it_finds_its_own_modules(monkeypatch):
    """serve.py loads api.py by its path, and ux.sh runs cli.py isolated (python3 -I): neither has the suite on the path."""
    import importlib.util

    here = Path(api.__file__).resolve().parent
    for name in ("api", "cli"):
        monkeypatch.setattr(sys, "path", [p for p in sys.path if Path(p).resolve() != here])
        spec = importlib.util.spec_from_file_location(f"{name}_by_its_path", here / f"{name}.py")
        spec.loader.exec_module(importlib.util.module_from_spec(spec))
    assert str(here) in sys.path


def test_the_state_still_answers_when_no_crissp_tool_can_be_found(product, monkeypatch):
    """No tool in the project and none in the engine: the page still shows everything, only without board links."""
    import ux_backlog

    (product.root / "crissp" / "tool" / "server.py").unlink()
    monkeypatch.setattr(ux_backlog, "ENGINE_TOOL", product.root / "no-engine" / "server.py")
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    out = api.state(product)
    assert out["walks"][0]["proposals"][0]["pbi"] is None and "error" not in out


def test_the_page_edits_the_team_and_the_rules(site):
    """E7-F1-01 / E7-F2-01: the Team and Rules tabs write through the suite's own POSTs; the state carries both."""
    _, base = site
    s = json.loads(get(base + "/ux/api/state")[2])
    assert s["personas_from"] == "team.json" and s["rules"] == [] and s["rules_from"] == "none"  # no PRINCIPLES.md
    code, out = post(
        base,
        "/ux/api/persona",
        {"persona": {"name": "Gerda", "role": "retired", "brief": "Careful.", "jobs": "See the cost"}},
    )
    assert code == 200 and "gerda" in [p["key"] for p in out["personas"]]
    code, out = post(base, "/ux/api/persona", {"remove": "gerda"})
    assert code == 200 and "gerda" not in [p["key"] for p in out["personas"]]
    code, out = post(
        base, "/ux/api/rule", {"rule": {"title": "Prices first", "severity": "must", "text": "Cost first."}}
    )
    assert code == 200 and out["rules"][0]["id"] == "prices-first"
    s = json.loads(get(base + "/ux/api/state")[2])
    assert s["personas_from"] == "files" and s["rules"][0]["severity"] == "must" and s["rules_from"] == "files"
    assert post(base, "/ux/api/rule", {"remove": "prices-first"}) == (200, {"rules": []})
    code, out = post(base, "/ux/api/rule", {"rule": {"title": "A", "text": "b"}}, origin="http://evil.example")
    assert code == 403
