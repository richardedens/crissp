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
NAV = re.compile(r'<nav class="?sections"?[^>]*>(.*?)</nav>', re.DOTALL)


def nav_of(html: str) -> tuple[str, str]:
    m = NAV.search(html)
    assert m, "no sections nav"
    current = re.search(r'data-current="?(\w+)', m.group(0))
    return (current.group(1) if current else ""), m.group(1)


def test_every_page_has_the_same_empty_sections_nav_with_its_own_section():
    for page, section in PAGES.items():
        text = page.read_text(encoding="utf-8")
        assert nav_of(text) == (section, ""), page.name  # nothing hand-written: look.js fills it
        assert "look/look.js" in text and "look/water.js" in text, page.name  # the same ground under every page
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
                              capture_output=True, text=True, timeout=30, check=False)
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


def test_a_page_s_own_tabs_get_a_row_of_their_own_on_one_line():
    """E3-F1-01, found in review: with six sections the Tests page's tabs wrapped (1280, 1440 wide) or were cut off.
    Row one is the same on every page (brand, sections, theme); a page's own tabs are row two, scrolling when narrow."""
    css = (ENGINE / "look" / "look.css").read_text(encoding="utf-8")
    top = re.search(r"^\.top \{([^}]*)\}", css, re.MULTILINE).group(1)
    tabs = re.search(r"^\.tabs \{([^}]*)\}", css, re.MULTILINE).group(1)
    assert "flex-wrap: wrap" in top
    assert "flex: 1 0 100%" in tabs and "order: 3" in tabs and "flex-wrap: nowrap" in tabs and "overflow-x: auto" in tabs
    assert re.search(r"^\.top #theme \{[^}]*margin-left: auto", css, re.MULTILINE)
    assert re.search(r"^\.brand \{[^}]*flex: 0 0 300px", css, re.MULTILINE)  # the sections start at the same place on every page
    assert re.search(r"^\.tabs button \{[^}]*white-space: nowrap", css, re.MULTILINE)


def _luminance(hex_: str) -> float:
    rgb = [int(hex_.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def test_text_on_the_accent_is_readable_in_both_themes():
    """F-72: the primary button was white on the dark theme's light purple, 3.2:1; WCAG AA asks 4.5:1 for its 13 px text."""
    css = (ENGINE / "look" / "look.css").read_text(encoding="utf-8")
    for theme in (r"^:root \{([^}]*)\}", r'^:root\[data-theme="light"\] \{([^}]*)\}'):
        tokens = dict(re.findall(r"--([\w-]+): (#[0-9a-fA-F]{6})", re.search(theme, css, re.MULTILINE).group(1)))
        assert contrast(tokens["accent"], tokens["on-accent"]) >= 4.5, theme
    assert re.search(r"^\.primary \{[^}]*color: var\(--on-accent\)", css, re.MULTILINE)
    assert contrast("#9b7bff", "#ffffff") < 4.5  # the old pair, so the check can fail


def test_on_a_phone_the_sections_scroll_in_their_own_row_and_the_page_never_sideways():
    """F-72: on a 390 px phone the six sections made the top bar 31 px wider than the screen, so the page scrolled."""
    css = (ENGINE / "look" / "look.css").read_text(encoding="utf-8")
    phone = css.split("@media (max-width: 800px) {", 1)[1].split("@media", 1)[0]
    rule = re.search(r"\.sections \{([^}]*)\}", phone)
    assert rule and "flex: 1 0 100%" in rule.group(1) and "overflow-x: auto" in rule.group(1) and "min-width: 0" in rule.group(1)
