"""E3-F1-01: one top bar on every page. The sections (Tests · Backlog · UX · Workers · Activity · Sessions) come from one list in
the shared look (crissp/look/look.js); every page has the same empty sections nav, which look.js fills and marks."""

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[2]
LOOK_JS = ENGINE / "look" / "look.js"
sys.path.insert(0, str(ENGINE / "testsuite" / "lib"))
import sessionview as sv  # noqa: E402

SECTIONS = ["tests", "backlog", "ux", "workers", "activity", "sessions"]
PAGES = {ENGINE / "testsuite" / "dashboard" / "index.html": "tests",
         ENGINE / "testsuite" / "dashboard" / "workers.html": "workers",
         ENGINE / "testsuite" / "dashboard" / "activity.html": "activity",
         ENGINE / "uxsuite" / "web" / "index.html": "ux"}
NAV = re.compile(r'<nav class="?sections"?[^>]*>(.*?)</nav>', re.S)


def nav_of(html: str) -> tuple[str, str]:
    m = NAV.search(html)
    assert m, "no sections nav"
    current = re.search(r'data-current="?(\w+)', m.group(0))
    return (current.group(1) if current else ""), m.group(1)


def test_every_page_has_the_same_empty_sections_nav_with_its_own_section():
    for page, section in PAGES.items():
        text = page.read_text(encoding="utf-8")
        assert nav_of(text) == (section, ""), page.name  # nothing hand-written: look.js fills it
        assert "look/look.js" in text, page.name
    assert nav_of(sv.top_bar("x")) == ("sessions", "")
    assert "look/look.js" in sv.page("t", "b")
    assert "TOGGLE" not in dir(sv)  # look.js switches the theme on every page; a second switch would undo it


def test_look_js_holds_the_sections_once_and_fills_and_marks_them():
    if not shutil.which("node"):
        pytest.skip("no node on this machine")
    stand_in = """
const navs = [{dataset: {current: "%s"}, innerHTML: ""}];
const h1 = {textContent: ""};
const handlers = {};
global.localStorage = {getItem: () => null, setItem: () => {}};
global.window = {addEventListener: (k, f) => { handlers[k] = f; }, dispatchEvent: () => {}};
global.CustomEvent = function () {};
global.location = {hash: "%s"};
global.document = {documentElement: {dataset: {}}, readyState: "complete", addEventListener: () => {},
  querySelectorAll: s => (s === "nav.sections[data-current]" ? navs : []), querySelector: s => (s === ".top h1" ? h1 : null)};
require(%s);
const first = navs[0].innerHTML;
window.Look.brand("Shop", "S", "Tests");
const titled = h1.textContent;
location.hash = "#tests"; handlers.hashchange && handlers.hashchange();
console.log(JSON.stringify({first, titled, sections: window.Look.SECTIONS.map(s => s[0]), after: navs[0].innerHTML,
                            retitled: h1.textContent}));
"""
    def run(current: str, hash_: str) -> dict:
        done = subprocess.run(["node", "-e", stand_in % (current, hash_, json.dumps(str(LOOK_JS)))],
                              capture_output=True, text=True, timeout=30)
        assert done.returncode == 0, done.stderr
        return json.loads(done.stdout)

    out = run("workers", "")
    assert out["sections"] == SECTIONS
    links = re.findall(r'<a href="([^"]+)"( aria-current="page")?>([^<]+)</a>', out["first"])
    assert [(h, t) for h, _, t in links] == [("/dashboard/", "Tests"), ("/dashboard/#board", "Backlog"), ("/ux/", "UX"),
                                             ("/dashboard/workers.html", "Workers"), ("/dashboard/activity.html", "Activity"),
                                             ("/results/sessions/index.html", "Sessions")]
    assert [t for _, cur, t in links if cur] == ["Workers"]
    board = run("tests", "#board")  # the board is the Tests page opened on its Backlog tab: Backlog is the open section
    assert 'aria-current="page">Backlog' in board["first"] and 'aria-current="page">Tests' in board["after"]
    assert len(re.findall(r"aria-current", board["after"])) == 1
    assert board["titled"] == "Shop · Backlog" and board["retitled"] == "Shop · Tests"  # the title follows the open section
    assert out["titled"] == "Shop · Workers"
