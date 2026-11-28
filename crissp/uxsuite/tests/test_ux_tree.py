"""Decide once (E7-F4-02): a verdict on a rule, an area or a screen holds for every piece of advice under it that has no
verdict of its own; agreed advice that keeps coming back on several screens is proposed as a rule, and an approved
proposal is a rule file."""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import ROUND, WALK, add_shots, finish, make_product, ux_config  # noqa: F401

# isort: split
import api  # ux_kit put the uxsuite on sys.path
import ux_cards
import ux_review
import ux_verdicts

SHOP = {"title": "Shop", "steps": [{"do": "goto", "path": "/shop"}, {"do": "shot", "title": "x"}]}
ADVICE = [{"title": "Bigger buttons", "detail": "Thumb reach.", "priority": "should", "rule": "08-accessible"},
          {"title": "Show prices", "detail": "Per day.", "priority": "must", "theme": "Prices up front"},
          {"title": "Plain words", "detail": "x", "priority": "could"}]
OTHER = [{"title": "Prices first", "detail": "Before the button.", "priority": "should", "theme": "prices up front!"}]


@pytest.fixture
def suite(tmp_path):
    s = make_product(tmp_path, walks={"first-visit": WALK, "shop": SHOP, "home-again": WALK})
    for w in ("first-visit", "shop", "home-again"):
        add_shots(s, w)
    finish(s, "round", "first-visit", 1, {**ROUND, "advice": ADVICE})
    finish(s, "round", "shop", 1, {**ROUND, "advice": OTHER})
    finish(s, "round", "home-again", 1, {**ROUND, "advice": [{**ADVICE[2]}]})
    ux_cards.save_rule(s, {"id": "08-accessible", "title": "Accessible", "text": "Big targets."})
    return s


def _say(suite, item, verdict, reason=""):
    conf = ux_config.load(suite)
    return ux_verdicts.after(suite, conf, ux_verdicts.record(suite, conf, {"id": item, "verdict": verdict, "reason": reason}))


def test_a_verdict_on_a_rule_holds_for_its_advice(suite):
    _say(suite, "rule/08-accessible", "agree")
    held = api.state(suite)["held"]
    assert held["first-visit/r1/a0"] == {"verdict": "agree", "reason": "", "by": "rule/08-accessible"}
    assert "first-visit/r1/a1" not in held
    screen = next(s for s in api.state(suite)["review"]["screens"] if s["walk"] == "first-visit")
    assert screen["open"] == ["first-visit/r1/a1", "first-visit/r1/a2"]


def test_the_nearest_verdict_holds_and_the_advice_s_own_wins(suite):
    _say(suite, "rule/08-accessible", "agree")
    _say(suite, "area/home", "later")
    _say(suite, "screen/first-visit", "disagree", "not this screen")
    held = api.state(suite)["held"]
    assert held["first-visit/r1/a0"]["by"] == "screen/first-visit" and held["first-visit/r1/a0"]["verdict"] == "disagree"
    assert held["home-again/r1/a0"] == {"verdict": "later", "reason": "", "by": "area/home"}
    assert "shop/r1/a0" not in held
    _say(suite, "first-visit/r1/a0", "agree")
    assert "first-visit/r1/a0" not in api.state(suite)["held"]


@pytest.mark.parametrize(("item", "verdict", "says"), [
    ("rule/nope", "agree", "unknown rule"),
    ("area/nowhere", "agree", "unknown area"),
    ("screen/nope", "agree", "unknown screen"),
    ("rule/08-accessible", "approve", "a verdict on a rule, an area or a screen is agree, disagree or later"),
    ("area/home", "disagree", "say why"),
    ("proposed/nope", "approve", "unknown proposal"),
    ("proposed/prices-up-front", "agree", "a verdict on a proposed rule is approve or reject")])
def test_a_wrong_verdict_up_the_tree_is_refused(suite, item, verdict, says):
    _say(suite, "first-visit/r1/a1", "agree")
    _say(suite, "shop/r1/a0", "agree")
    with pytest.raises(ValueError, match=re.escape(says)):
        _say(suite, item, verdict)


def test_agreed_advice_on_several_screens_is_proposed_as_a_rule(suite):
    assert api.state(suite)["proposed"] == []
    _say(suite, "first-visit/r1/a1", "agree")
    assert api.state(suite)["proposed"] == []  # one screen is not yet a pattern
    _say(suite, "shop/r1/a0", "agree")
    _say(suite, "first-visit/r1/a2", "agree")  # agreed, but on one screen only
    [p] = api.state(suite)["proposed"]
    assert p == {"id": "proposed/prices-up-front", "title": "Prices up front", "severity": "must",
                 "text": "Per day.\nBefore the button.", "walks": ["first-visit", "shop"],
                 "advice": ["first-visit/r1/a1", "shop/r1/a0"], "verdict": None}


def test_an_approved_proposal_is_a_rule_file_and_a_rejected_one_stays_away(suite):
    _say(suite, "first-visit/r1/a1", "agree")
    _say(suite, "shop/r1/a0", "agree")
    assert _say(suite, "proposed/prices-up-front", "approve") == {"rule": "prices-up-front"}
    rule = next(r for r in ux_cards.rules(suite) if r["id"] == "prices-up-front")
    assert rule["severity"] == "must" and rule["text"] == "Per day.\nBefore the button." and rule["title"] == "Prices up front"
    assert api.state(suite)["proposed"] == []  # a rule now: proposed no more
    (suite.here / "rules" / "prices-up-front.md").unlink()
    _say(suite, "proposed/prices-up-front", "reject", "too strict")
    assert api.state(suite)["proposed"][0]["verdict"]["verdict"] == "reject"
    assert _say(suite, "proposed/prices-up-front", "reject", "still") == {}


def test_a_theme_or_else_the_title_groups_advice():
    assert ux_review.theme({"title": "Show prices", "theme": "Prices up front"}) == "prices-up-front"
    assert ux_review.theme({"title": "Show prices!"}) == "show-prices"
    assert ux_review.theme({"title": "!!"}) == ""
