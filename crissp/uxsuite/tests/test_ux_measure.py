"""Measured rules (E7-F2-02): a rule can name what the browser checks itself at every shoot (text that overflows, small
tap targets, the primary action below the fold, a see-through dialog, no visible focus). The shoot hands those checks to
the page (measure.js), each shot keeps what was found with the rule and where, and the team reads them as facts."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import add_shots, make_product, product, ux_config, ux_team  # noqa: F401

# isort: split
import ux_cards  # ux_kit put the uxsuite on sys.path
import ux_shoot

PRINCIPLES = """# Design principles

## 1. Nothing important behind a scroll

The primary action is visible without scrolling.
Measured by the browser: below-fold.

## 8. Accessible by default

Tap targets are big enough and focus shows.
Measured by the browser: tap-targets, focus-visible.

## 9. Plain words

No jargon.
"""

FOUND = [{"check": "overflow", "rule": "06-no-text-overflows", "where": {"x": 10, "y": 20, "w": 300, "h": 18},
          "detail": '"A very long name" is cut off'},
         {"check": "below-fold", "rule": "01-nothing", "where": None, "detail": '"Pay" starts 40 px below the first screen'}]


def test_a_principle_says_what_the_browser_measures(tmp_path):
    suite = make_product(tmp_path)
    (suite.here / "PRINCIPLES.md").write_text(PRINCIPLES)
    found = ux_cards.rules(suite)
    assert found[0] == {"id": "01-nothing-important-behind-a-scroll", "title": "Nothing important behind a scroll",
                        "severity": "should", "on": True, "measure": ["below-fold"],
                        "text": "The primary action is visible without scrolling."}
    assert found[1]["measure"] == ["tap-targets", "focus-visible"] and "measure" not in found[2]
    assert "## 08-accessible-by-default · Accessible by default (should, measured by the browser: tap-targets, " \
           "focus-visible)" in ux_cards.rules_for_a_run(found)
    # the first write keeps it, now as a field of the rule's file
    ux_cards.save_rule(suite, {"title": "Plain words", "text": "No jargon."})
    file = (suite.here / "rules" / "08-accessible-by-default.md").read_text()
    assert "measure: tap-targets, focus-visible\n" in file and "Measured by" not in file
    assert ux_cards.rules(suite)[1]["measure"] == ["tap-targets", "focus-visible"]


def test_the_page_sets_and_clears_what_a_rule_measures(tmp_path):
    suite = make_product(tmp_path)
    out = ux_cards.save_rule(suite, {"title": "Solid", "text": "Dialogs are solid.", "measure": ["dialog-opaque"]})
    assert out["rules"][0]["measure"] == ["dialog-opaque"]
    out = ux_cards.save_rule(suite, {"id": "solid", "title": "Solid", "text": "Dialogs are solid.", "measure": []})
    assert "measure" not in out["rules"][0] and "measure" not in (suite.here / "rules" / "solid.md").read_text()


@pytest.mark.parametrize(("measure", "says"), [
    (["colour"], "measure: colour is not a check the browser runs (overflow, tap-targets, below-fold, dialog-opaque, focus-visible)"),
    ("overflow", "measure must be a list of checks"),
    ([1], "measure must be a list of checks")])
def test_a_check_the_browser_does_not_run_is_refused(tmp_path, measure, says):
    suite = make_product(tmp_path)
    with pytest.raises(ValueError, match=re.escape(says)):
        ux_cards.save_rule(suite, {"title": "A", "text": "x", "measure": measure})


def test_a_rule_file_with_an_unknown_check_is_named(tmp_path):
    suite = make_product(tmp_path)
    (suite.here / "rules").mkdir()
    (suite.here / "rules" / "a.md").write_text("---\ntitle: A\nmeasure: overflow, colour\n---\nx\n")
    with pytest.raises(ux_config.ConfigError, match=re.escape("rules/a.md: measure: colour is not a check")):
        ux_cards.rules(suite)


def test_the_shoot_hands_the_checks_of_the_rules_that_hold_to_the_browser(tmp_path):
    suite = make_product(tmp_path)
    (suite.here / "PRINCIPLES.md").write_text(PRINCIPLES)
    p = ux_shoot.plan(suite, ux_config.load(suite), "first-visit")
    assert p["measure"] == [{"check": "below-fold", "rule": "01-nothing-important-behind-a-scroll"},
                            {"check": "tap-targets", "rule": "08-accessible-by-default"},
                            {"check": "focus-visible", "rule": "08-accessible-by-default"}]
    assert p["measure_js"] == str(ux_shoot.HERE / "measure.js") and Path(p["measure_js"]).is_file()
    ux_cards.save_rule(suite, {"id": "08-accessible-by-default", "title": "A", "text": "x", "on": False,
                               "measure": ["tap-targets"]})
    assert [m["check"] for m in ux_shoot.plan(suite, ux_config.load(suite), "first-visit")["measure"]] == ["below-fold"]


def test_the_shoot_says_how_much_was_measured(tmp_path):
    suite = make_product(tmp_path)

    def run(cmd, **kw):
        (Path(cmd[-1]).parent / "shots.json").write_text(json.dumps([
            {"device": "laptop", "n": 1, "title": "a", "file": "laptop/01-a.png", "measured": FOUND},
            {"device": "phone", "n": 1, "title": "a", "file": "phone/01-a.png", "measured": []}]))
        return type("Done", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    code, text = ux_shoot.shoot(suite, ux_config.load(suite), "first-visit", run)
    assert code == 0 and text.endswith("\n  measured by the browser: 2 finding(s) on 1 shot(s)")


def test_each_shot_brings_what_was_measured_and_the_team_reads_it_as_facts(product):
    add_shots(product)
    listed = product.results / "shots" / "first-visit" / "shots.json"
    shots = json.loads(listed.read_text())
    shots[0]["measured"] = FOUND
    listed.write_text(json.dumps(shots))
    seen = ux_team.shots(product, "first-visit")
    assert seen[0]["measured"] == FOUND and seen[1]["measured"] == []
    ux_team.request(product, ux_config.load(product), "round", "first-visit")
    prompt = ux_team.popen.started[0].cmd[2]
    assert "MEASURED BY THE BROWSER" in prompt
    assert '  laptop 1 · overflow (rule 06-no-text-overflows) at 10,20 300×18: "A very long name" is cut off' in prompt
    assert '  laptop 1 · below-fold (rule 01-nothing): "Pay" starts 40 px below the first screen' in prompt


def test_without_measured_findings_the_prompt_says_nothing_of_them(product):
    add_shots(product)
    ux_team.request(product, ux_config.load(product), "round", "first-visit")
    assert "MEASURED BY THE BROWSER" not in ux_team.popen.started[0].cmd[2]
