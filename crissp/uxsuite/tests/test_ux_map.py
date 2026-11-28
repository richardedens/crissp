"""Mapping the product (ux_map, E7-F3-01): one screen list from a read-only crawl, the project's own test screenshots
and the walks, with the gaps (a screen no link reaches, a screen no walk looks at). The browser is a stand-in."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import add_shots, make_product, ux_config

# isort: split
import ux_map  # ux_kit put the uxsuite on sys.path
import ux_shoot


@pytest.mark.parametrize(("path", "key"), [
    ("/", "/"), ("", "/"), ("/orders/", "/orders"), ("/Orders?page=2#top", "/orders"), ("/orders/42", "/orders/:id"),
    ("/u/3f2a9c1e-0b7d-4e1a-9c2b-1d2e3f4a5b6c/edit", "/u/:id/edit"), ("/blob/a1b2c3d4e5f6a7b8", "/blob/:id"),
    ("/blog/hello-world", "/blog/hello-world")])
def test_a_screen_is_its_path_without_query_and_with_ids_folded(path, key):
    assert ux_map.screen_key(path) == key


def test_the_area_is_the_first_part_of_the_path():
    assert ux_map.area("/") == "home" and ux_map.area("/orders/:id") == "orders"


def test_the_crawl_follows_only_the_product_s_own_pages():
    base = "http://127.0.0.1:5173"
    hrefs = ["http://127.0.0.1:5173/orders?x=1", "http://127.0.0.1:5173/orders/7", "http://127.0.0.1:5173/orders/8",
             "https://elsewhere.example/", "mailto:a@b.c", "http://127.0.0.1:5173/files/report.pdf",
             "http://127.0.0.1:5173/logout", "http://127.0.0.1:5173/sign-out", "http://127.0.0.1:5173/delete/3",
             "http://127.0.0.1:5173/page.html", "javascript:void(0)", "http://127.0.0.1:9999/other-port"]
    assert ux_map.follow(base, hrefs) == ["/orders?x=1", "/orders/7", "/page.html"]


def _crawl(pages=None, code=0, err=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        out = Path(cmd[-1]).parent
        for p in pages or []:
            if p.get("file"):
                (out / p["file"]).parent.mkdir(parents=True, exist_ok=True)
                (out / p["file"]).write_bytes(b"\x89PNG stand-in")
        if pages is not None:
            (out / "crawl.json").write_text(json.dumps(pages))
        return subprocess.CompletedProcess(cmd, code, "", err)
    return run, calls


PAGES = [
    {"path": "/", "title": "Home", "device": "laptop", "file": "laptop/01.png", "from": None, "links": ["/orders", "/help"]},
    {"path": "/orders", "title": "Orders", "device": "laptop", "file": "laptop/02.png", "from": "/", "links": ["/orders/1"]},
    {"path": "/orders/1", "title": "Order 1", "device": "laptop", "file": "laptop/03.png", "from": "/orders", "links": []},
    {"path": "/help", "title": "Help", "device": "laptop", "file": "", "from": "/", "error": "timed out"},
    {"path": "/", "title": "Home", "device": "phone", "file": "phone/01.png", "from": None, "links": []},
]


def test_the_plan_starts_at_home_and_every_walk_s_page_on_the_team_s_devices(tmp_path):
    suite = make_product(tmp_path, walks={"buy": {"title": "Buy", "steps": [
        {"do": "goto", "path": "/shop"}, {"do": "shot", "title": "Shop"}, {"do": "goto", "path": "/"},
        {"do": "shot", "title": "Home"}]}})
    p = ux_map.plan(suite, ux_config.load(suite))
    assert p["start"] == ["/", "/shop"] and list(p["devices"]) == ["laptop", "phone"] and p["max"] == 40
    assert p["url"] == "http://127.0.0.1:5173" and p["out"].endswith("results/map/crawl")
    team = json.loads((suite.here / "team.json").read_text())
    (suite.here / "team.json").write_text(json.dumps({**team, "map": {"max": 5}}))
    assert ux_map.plan(suite, ux_config.load(suite))["max"] == 5


@pytest.mark.parametrize(("value", "says"), [({"max": 0}, "map.max"), ({"max": "x"}, "map.max"), ("x", "map must be"),
                                              ({"tests": 3}, "map.tests")])
def test_a_wrong_map_setting_is_a_clear_error(tmp_path, value, says):
    suite = make_product(tmp_path)
    team = json.loads((suite.here / "team.json").read_text())
    (suite.here / "team.json").write_text(json.dumps({**team, "map": value}))
    with pytest.raises(ux_config.ConfigError, match=says):
        ux_config.load(suite)


def test_a_crawl_runs_the_browser_under_uv_and_builds_the_screen_list(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    add_shots(suite)
    run, calls = _crawl(PAGES)
    code, text = ux_map.crawl(suite, conf, run)
    assert code == 0 and calls[0][:6] == ["uv", "run", "--quiet", "--no-project", "--with", ux_shoot.PLAYWRIGHT]
    assert calls[0][-2].endswith("ux_map.py") and calls[0][-1].endswith("map/crawl.new/plan.json")
    assert json.loads((suite.results / "map" / "crawl" / "plan.json").read_text())["start"] == ["/"]
    assert text.splitlines()[0] == "4 screen(s) in 3 area(s), 1 gap(s): crissp/uxsuite/results/map/screens.json"
    assert "  /help: the crawl could not open it (timed out)" in text
    m = ux_map.load(suite)
    by = {s["key"]: s for s in m["screens"]}
    assert list(by) == ["/", "/help", "/orders", "/orders/:id"]
    home = by["/"]
    assert home["title"] == "Home" and home["area"] == "home" and home["found_by"] == ["crawl", "walk"]
    assert home["walks"] == ["first-visit"] and home["linked_from"] == []
    assert [(s["device"], s["source"]) for s in home["shots"]] == [("laptop", "crawl"), ("phone", "crawl"), ("laptop", "walk")]
    assert home["shots"][0]["url"] == "/ux/results/map/crawl/laptop/01.png"
    assert home["shots"][2]["url"] == "/ux/results/shots/first-visit/laptop/01-the-first-screen.png"
    assert by["/orders/:id"]["linked_from"] == ["/orders"] and by["/orders/:id"]["gaps"] == ["no walk looks at it"]
    assert by["/help"]["gaps"] == ["the crawl could not open it (timed out)", "no walk looks at it"]
    assert m["areas"] == {"help": 1, "home": 1, "orders": 2} and m["gaps"] == 1 and m["crawled"] is True


def test_a_crawl_that_fails_says_how_to_get_the_browser_and_keeps_the_last_map(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    ux_map.crawl(suite, conf, _crawl(PAGES)[0])
    code, text = ux_map.crawl(suite, conf, _crawl(None, code=1, err="net::ERR_CONNECTION_REFUSED")[0])
    assert code == 1 and "http://127.0.0.1:5173 must be running" in text and "playwright install chromium" in text
    assert len(ux_map.load(suite)["screens"]) == 4
    code, text = ux_map.crawl(suite, conf, _crawl(None)[0])
    assert code == 1 and "crawl.json" in text


def _test_shots(suite, entries, files=("orders.png",)):
    d = suite.results / "test-shots"
    d.mkdir(parents=True, exist_ok=True)
    for f in files:
        (d / f).write_bytes(b"\x89PNG stand-in")
    (d / "screens.json").write_text(json.dumps(entries))
    return d


def test_the_project_s_own_test_screenshots_are_screens_too(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    _test_shots(suite, [{"path": "/orders/12", "title": "An order", "device": "phone", "file": "orders.png", "test": "test_order"},
                        {"path": "/settings", "file": "missing.png"}, {"path": "/x", "file": "../../team.json"},
                        {"path": "/y", "file": "notes.txt"}, {"title": "no path"}, "not an object"])
    m = ux_map.build(suite, conf)
    by = {s["key"]: s for s in m["screens"]}
    assert set(by) == {"/", "/orders/:id"} and m["crawled"] is False
    order = by["/orders/:id"]
    assert order["found_by"] == ["test"] and order["tests"] == ["test_order"] and order["title"] == "An order"
    assert order["shots"] == [{"device": "phone", "url": "/ux/results/map/tests/01.png", "source": "test", "title": "An order"}]
    assert (suite.results / "map" / "tests" / "01.png").read_bytes() == b"\x89PNG stand-in"
    assert order["gaps"] == ["no walk looks at it"]  # no crawl ran: "no link reaches it" is not known yet
    assert m["skipped"] == ["/settings: missing.png is not there", "/x: ../../team.json is not a picture beside screens.json",
                            "/y: notes.txt is not a picture beside screens.json", "entry 5: needs a path and a file",
                            "entry 6: needs a path and a file"]


def test_after_a_crawl_a_screen_only_the_tests_reach_is_a_gap(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    _test_shots(suite, [{"path": "/admin/users", "file": "orders.png"}])
    ux_map.crawl(suite, conf, _crawl(PAGES)[0])
    admin = next(s for s in ux_map.load(suite)["screens"] if s["key"] == "/admin/users")
    assert admin["gaps"] == ["no link reaches it", "no walk looks at it"] and admin["title"] == "/admin/users"


def test_the_test_shots_can_live_elsewhere_and_a_broken_manifest_is_told(tmp_path):
    suite = make_product(tmp_path)
    team = json.loads((suite.here / "team.json").read_text())
    (suite.here / "team.json").write_text(json.dumps({**team, "map": {"tests": "app/frontend/e2e-shots/screens.json"}}))
    conf = ux_config.load(suite)
    d = suite.root / "app" / "frontend" / "e2e-shots"
    d.mkdir(parents=True)
    (d / "screens.json").write_text("{not json")
    assert ux_map.build(suite, conf)["skipped"] == ["app/frontend/e2e-shots/screens.json: not a JSON list"]
    (d / "a.png").write_bytes(b"x")
    (d / "screens.json").write_text(json.dumps([{"path": "/a", "file": "a.png"}]))
    assert [s["key"] for s in ux_map.build(suite, conf)["screens"]] == ["/", "/a"]


def test_no_map_yet_is_none():
    assert ux_map.load(ux_config.Suite(Path("/nonexistent-crissp-root"))) is None


def test_a_walk_s_shot_lands_on_the_screen_the_browser_was_on(tmp_path):
    suite = make_product(tmp_path, walks={"menu": {"title": "Menu", "steps": [{"do": "shot", "title": "Somewhere"}]},
                                          "deep": {"title": "Deep", "steps": [{"do": "goto", "path": "/a"},
                                                                              {"do": "click", "text": "B"},
                                                                              {"do": "shot", "title": "B"}]}})
    for walk, at in (("menu", None), ("deep", "/b/7")):
        d = suite.results / "shots" / walk
        (d / "laptop").mkdir(parents=True)
        (d / "laptop" / "01.png").write_bytes(b"x")
        (d / "shots.json").write_text(json.dumps([{"device": "laptop", "n": 1, "title": "B", "file": "laptop/01.png",
                                                   **({"path": at} if at else {})}]))
    by = {s["key"]: s for s in ux_map.build(suite, ux_config.load(suite))["screens"]}
    assert set(by) == {"/a", "/b/:id"}  # a walk without a goto and without a known page places its shot nowhere
    assert by["/b/:id"]["walks"] == ["deep"] and by["/b/:id"]["shots"][0]["source"] == "walk"
    assert by["/a"]["shots"] == [] and by["/a"]["walks"] == ["deep"]
