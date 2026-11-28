"""The review screen (E7-F4-01): every screen has a status on the way from seen to accepted, the product owner sees how
far the product is, and the screens that wait for them come first, each with what they must decide next."""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PROPOSAL, ROUND, WALK, add_shots, finish, make_product, product, ux_config, ux_team  # noqa: F401

# isort: split
import api  # ux_kit put the uxsuite on sys.path
import ux_map
import ux_review
import ux_verdicts

TWO = {
    **ROUND,
    "advice": [
        {"title": "Plain words", "detail": "x", "priority": "could"},
        {
            "title": "Bigger buttons",
            "detail": "Thumb reach.",
            "priority": "must",
            "shot": "laptop 1",
            "where": {"x": 10, "y": 20, "w": 100, "h": 40},
        },
    ],
}


def _screen(suite, walk="first-visit"):
    return next(s for s in api.state(suite)["review"]["screens"] if s["walk"] == walk)


def _say(suite, item, verdict, reason=""):
    conf = ux_config.load(suite)
    ux_verdicts.after(suite, conf, ux_verdicts.record(suite, conf, {"id": item, "verdict": verdict, "reason": reason}))


def test_a_screen_goes_from_new_to_accepted(product):
    assert _screen(product) == {
        "walk": "first-visit",
        "title": "First visit",
        "area": "home",
        "status": "new",
        "step": 0,
        "waits": "team",
        "next": "shoot it: crissp/ux.sh --shoot first-visit",
        "open": [],
        "must": 0,
        "design": None,
    }
    add_shots(product)
    assert _screen(product)["status"] == "seen" and _screen(product)["next"] == "ask the team for a round"
    finish(product, "round", "first-visit", 1, TWO)
    s = _screen(product)
    assert s["status"] == "discussed" and s["waits"] == "you" and s["next"] == "decide 2 piece(s) of advice"
    assert s["open"] == ["first-visit/r1/a1", "first-visit/r1/a0"]  # must first
    _say(product, "first-visit/r1/a1", "agree")
    _say(product, "first-visit/r1/a0", "later")
    s = _screen(product)
    assert (
        s["status"] == "decided"
        and s["open"] == []
        and s["waits"] == "team"
        and s["next"] == "ask the team for a design"
    )
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    s = _screen(product)
    assert (
        s["status"] == "designed"
        and s["waits"] == "you"
        and s["next"] == "judge design 1"
        and s["design"] == "first-visit#v1"
    )
    _say(product, "first-visit#v1", "approve")
    s = _screen(product)
    assert (
        s["status"] == "approved"
        and s["waits"] == "team"
        and s["next"] == "build it, then shoot it again: crissp/ux.sh --shoot first-visit"
    )
    shots = product.results / "shots" / "first-visit" / "shots.json"
    os.utime(shots, (time.time() + 120, time.time() + 120))
    s = _screen(product)
    assert s["status"] == "built" and s["waits"] == "you" and s["next"] == "accept what was built, or send it back"
    _say(product, "first-visit#v1/built", "accept")
    s = _screen(product)
    assert s["status"] == "accepted" and s["waits"] is None and s["next"] == "done"


def test_a_design_that_was_rejected_or_is_redone_waits_for_the_team(product):
    add_shots(product)
    finish(product, "round", "first-visit", 1, {**ROUND, "advice": []})
    s = _screen(product)
    assert s["status"] == "decided" and s["next"] == "ask the team for a design"
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    _say(product, "first-visit#v1", "reject", "not this")
    assert _screen(product)["waits"] == "team" and _screen(product)["next"] == "ask the team for a design"


def test_a_running_round_is_the_team_s_turn(product):
    add_shots(product)
    vdir = ux_team.folder(product, "round", "first-visit") / "r1"
    vdir.mkdir(parents=True)
    (vdir / "status.json").write_text(json.dumps({"phase": "debate", "note": "x"}))
    s = _screen(product)
    assert s["status"] == "seen" and s["waits"] == "team" and s["next"] == "the team is at it (debate)"


def test_progress_counts_every_screen_and_those_that_wait_for_you_come_first(tmp_path, monkeypatch):
    suite = make_product(tmp_path, walks={"a-walk": WALK, "b-walk": WALK, "c-walk": WALK})
    add_shots(suite, "b-walk")
    add_shots(suite, "c-walk")
    finish(suite, "round", "c-walk", 1, TWO)
    review = api.state(suite)["review"]
    assert [s["walk"] for s in review["screens"]] == ["c-walk", "b-walk", "a-walk"]
    assert review["progress"] == {
        "new": 1,
        "seen": 1,
        "discussed": 1,
        "decided": 0,
        "designed": 0,
        "approved": 0,
        "built": 0,
        "accepted": 0,
    }
    assert review["waiting"] == 1 and review["total"] == 3 and review["steps"] == list(ux_review.STEPS)


def test_a_mapped_screen_takes_the_status_of_the_walks_that_look_at_it(product):
    add_shots(product)
    conf = ux_config.load(product)
    ux_map.build(product, conf)
    finish(product, "round", "first-visit", 1, TWO)
    state = api.state(product)
    assert state["review"]["map"] == {"/": "discussed"}
    assert ux_review.map_status({"screens": [{"key": "/x", "walks": []}]}, {}) == {"/x": "seen"}
    assert ux_review.map_status(None, {}) == {}


def test_the_area_of_a_screen_comes_from_its_walk_s_first_page(tmp_path):
    suite = make_product(
        tmp_path,
        walks={
            "pay": {"title": "Pay", "steps": [{"do": "goto", "path": "/checkout/12"}, {"do": "shot", "title": "x"}]},
            "none": {"title": "None", "steps": [{"do": "shot", "title": "x"}]},
        },
    )
    areas = {s["walk"]: s["area"] for s in api.state(suite)["review"]["screens"]}
    assert areas == {"pay": "checkout", "none": "home"}


def test_the_team_is_asked_to_pin_advice_to_a_place_on_the_shot(product):
    add_shots(product)
    ux_team.request(product, ux_config.load(product), "round", "first-visit")
    assert '"where": {"x", "y", "w", "h"}' in ux_team.popen.started[0].cmd[2].replace("{{", "{").replace("}}", "}")
