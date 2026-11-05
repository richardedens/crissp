"""The one local server (lib/serve.py): the Tests dashboard and the UX suite in one look. The dashboard's data is rebuilt
when the backlog, changes.json or a run's results are newer than it, the page learns that from /dashboard/stamp, and a
failed rebuild keeps the last good data; /ux goes to the UX suite; nothing else of the repository is served."""

import importlib.util
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

SERVE = Path(__file__).resolve().parents[1] / "lib" / "serve.py"
REPO = SERVE.parents[3]
sys.path.insert(0, str(SERVE.parent))
spec = importlib.util.spec_from_file_location("serve_under_test", SERVE)
sv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sv)


@pytest.fixture
def world(tmp_path):
    """A product (its backlog, changes.json, results) and an engine (the dashboard page, the look) apart from it."""
    root = tmp_path / "repo"
    (root / "crissp" / "backlog" / "done").mkdir(parents=True)
    (root / "crissp" / "backlog" / "E1-quality.md").write_text("# E1 · Quality\n")
    (root / "crissp" / "testsuite").mkdir()
    (root / "crissp" / "testsuite" / "changes.json").write_text('{"changes": []}')
    engine = tmp_path / "engine"
    (engine / "dashboard").mkdir(parents=True)
    (engine / "dashboard" / "index.html").write_text('<a id="sessions"></a>')
    (engine / "lib").mkdir()
    (engine / "lib" / "serve.py").write_text("secret = 1\n")
    (tmp_path / "look").mkdir()
    (tmp_path / "look" / "look.css").write_text(":root{}")
    (tmp_path / "secret.txt").write_text("not served")
    return root, engine, tmp_path / "look"


def _age(path: Path, seconds: float) -> None:
    t = time.time() - seconds
    os.utime(path, (t, t))


def _builder(root: Path, calls: list):
    def rebuild():
        calls.append(1)
        data = root / "crissp" / "testsuite" / "results" / "data.js"
        data.parent.mkdir(parents=True, exist_ok=True)
        data.write_text(f"window.SUITE = {{\"build\": {len(calls)}}};\n")
    return rebuild


def test_what_the_dashboard_shows_is_watched(world):
    root, _, _ = world
    assert [p.name for p in sv.watched(root)] == ["E1-quality.md", "changes.json", "threats.json", "suites.json"]
    results = root / "crissp" / "testsuite" / "results"
    (results / "sessions").mkdir(parents=True)
    (results / "gate.json").write_text("{}")
    (results / "sessions" / "a.html").write_text("")  # only the results themselves, not the pages made from them
    (root / "crissp" / "backlog" / "done" / "FINDINGS.md").write_text("")
    names = [str(p.relative_to(root)) for p in sv.watched(root)]
    assert "crissp/testsuite/results/gate.json" in names and "crissp/backlog/done/FINDINGS.md" in names
    assert not any("sessions" in n for n in names)
    assert sv.newest([]) == 0.0 and sv.newest([root / "missing"]) == 0.0


def test_the_data_is_rebuilt_only_when_what_it_shows_changed(world):
    root, _, _ = world
    calls = []
    live = sv.Live(root, _builder(root, calls))
    assert live.built() == 0.0
    first = live.stamp()
    assert calls == [1] and first > 0  # no data yet: built
    assert live.stamp() == first and calls == [1]  # nothing changed (the data itself is a result, but not a reason)
    _age(live.data, 60)
    (root / "crissp" / "backlog" / "E1-quality.md").write_text("# E1 · Quality\n### E1-01 · The gate   [review] [M]\n")
    assert live.stamp() != first and calls == [1, 1]  # a story moved: rebuilt, a new stamp


def test_a_failed_rebuild_keeps_the_last_good_data(world, capsys):
    root, _, _ = world
    live = sv.Live(root, None)
    live.data.parent.mkdir(parents=True)
    live.data.write_text("window.SUITE = {};\n")
    _age(live.data, 60)

    def broken():
        raise ValueError("changes.json is not JSON")
    live.rebuild = broken
    before = live.built()
    assert live.stamp() == before and live.data.read_text() == "window.SUITE = {};\n"
    assert "dashboard data not rebuilt: changes.json is not JSON" in capsys.readouterr().err


class FakeUx:
    """The UX suite's handler, stood in: answers every request with what it was asked."""

    def __init__(self):
        self.seen, self.started = [], 0

    def handle(self, handler, method):
        self.seen.append((method, handler.path))
        body = json.dumps({"ux": method, "path": handler.path}).encode()
        handler.send_response(200)
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def start_worker(self):
        self.started += 1


def _serve(world, ux):
    root, engine, look = world
    calls = []
    httpd = sv.server(0, root, engine, _builder(root, calls), ux=ux, look=look)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}", calls


def _get(url: str, data: bytes | None = None) -> tuple[int, dict, bytes]:
    class Stay(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            return None
    try:
        with urllib.request.build_opener(Stay).open(urllib.request.Request(url, data=data)) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_one_server_serves_the_dashboard_its_data_the_look_and_the_ux_suite(world):
    root, _, _ = world
    ux = FakeUx()
    httpd, base, calls = _serve(world, ux)
    try:
        code, headers, body = _get(base + "/results/data.js")  # a first load builds the data first
        assert code == 200 and body == b'window.SUITE = {"build": 1};\n' and headers["Cache-Control"] == "no-store"
        code, headers, body = _get(base + "/dashboard/stamp?t=1")
        first = json.loads(body)["stamp"]
        assert headers["Content-Type"] == "application/json" and calls == [1]
        _age(root / "crissp/testsuite/results/data.js", 60)
        (root / "crissp/testsuite/changes.json").write_text('{"changes": [{"id": "F-27"}]}')  # a change recorded
        assert json.loads(_get(base + "/dashboard/stamp")[2])["stamp"] != first and calls == [1, 1]
        assert b'id="sessions"' in _get(base + "/dashboard/")[2]  # the page itself, from the engine
        code, headers, _ = _get(base + "/")
        assert code == 302 and headers["Location"] == "/dashboard/"
        code, headers, body = _get(base + "/look/look.css")
        assert code == 200 and body == b":root{}" and headers["Content-Type"] == "text/css"
        assert _get(base + "/ux/api/state?x=1")[2] == b'{"ux": "GET", "path": "/ux/api/state?x=1"}'
        assert json.loads(_get(base + "/ux/api/verdict", b"{}")[2]) == {"ux": "POST", "path": "/ux/api/verdict"}
        assert _get(base + "/ux")[0] == 200 and ux.seen[-1] == ("GET", "/ux")
    finally:
        httpd.shutdown()
        httpd.server_close()
    assert httpd.server_address[0] == "127.0.0.1"  # never on another interface


@pytest.mark.parametrize("path", ["/lib/serve.py", "/../secret.txt", "/look/../secret.txt", "/look/missing.css",
                                  "/dashboard/../lib/serve.py", "/results/../suites.json", "/crissp/backlog/E1-quality.md"])
def test_nothing_else_of_the_repository_is_served(world, path):
    httpd, base, _ = _serve(world, FakeUx())
    try:
        code, _, body = _get(base + path)
        assert code == 404 and b"secret" not in body
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_without_a_ux_suite_ux_is_not_found_and_other_posts_are_refused(world):
    httpd, base, _ = _serve(world, False)
    try:
        code, _, body = _get(base + "/ux/")
        assert code == 404 and b"has no UX suite" in body
        assert _get(base + "/ux/api/verdict", b"{}")[0] == 404
        assert _get(base + "/dashboard/stamp", b"{}")[0] == 404
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_the_ux_suite_is_the_one_beside_this_engine(tmp_path):
    assert sv.load_ux(tmp_path / "none.py") is None
    real = sv.load_ux()
    assert sv.UX_API == REPO / "crissp/uxsuite/api.py" and callable(real.handle) and callable(real.start_worker)


def test_by_default_it_rebuilds_with_collect_for_the_project_it_is_given(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    (lib / "collect.py").write_text("from pathlib import Path\n\ndef main():\n    (Path(__file__).parent / 'ran').write_text('yes')\n")
    monkeypatch.setattr(sv, "SUITE", tmp_path)
    sv.collect()
    assert (lib / "ran").read_text() == "yes"
    monkeypatch.setenv("CRISSP_ROOT", str(tmp_path))
    httpd = sv.server(0, ux=False)
    try:
        live = httpd.RequestHandlerClass.func.live
        assert live.rebuild is sv.collect and live.root == tmp_path.resolve()
    finally:
        httpd.server_close()


def test_main_serves_until_stopped_and_starts_the_ux_queue(monkeypatch):
    seen = {}
    ux = FakeUx()

    class Fake:
        RequestHandlerClass = type("H", (), {"func": type("F", (), {"ux": ux})})

        def serve_forever(self):
            raise KeyboardInterrupt

        def server_close(self):
            seen["closed"] = True

    monkeypatch.setattr(sv, "server", lambda port: seen.setdefault("port", port) and Fake())
    assert sv.main(["--port", "9123"]) == 0 and seen == {"port": 9123, "closed": True} and ux.started == 1
    Fake.RequestHandlerClass.func.ux = None
    assert sv.main([]) == 0 and seen["port"] == 9123  # no UX suite: nothing to start
