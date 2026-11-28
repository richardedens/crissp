"""A discovery round (E7-F3-02): every persona tries their own jobs on the mapped screens and says done, hard or
impossible and where they gave up; the moderator turns what cannot be done into needs, and a need the product owner
approves becomes a design request: a walk with a brief whose first design starts at once. The team is a stand-in."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import add_shots, finish, product, ux_config, ux_team  # noqa: F401

# isort: split
import ux_cards  # ux_kit put the uxsuite on sys.path
import ux_discovery
import ux_map
import ux_verdicts

FOUND = {"summary": "Mo cannot pay on a phone.", "jobs": [
    {"persona": "phone", "job": "Pay for an order", "verdict": "impossible", "screens": ["/"], "gave_up_at": "/",
     "why": "No pay button on the phone."},
    {"persona": "tech", "job": "Find an order", "verdict": "done", "screens": ["/"], "gave_up_at": "", "why": ""}],
    "needs": [{"title": "Pay on a phone", "detail": "A checkout that fits a thumb, with the price before paying.",
               "personas": ["phone"], "jobs": ["Pay for an order"], "screens": ["/checkout"]}]}


def _mapped(product):
    add_shots(product)
    ux_cards.save_persona(product, {"key": "phone", "name": "Mo", "role": "student", "device": "mobile",
                                    "brief": "Uses a thumb.", "jobs": ["Pay for an order"]})
    conf = ux_config.load(product)
    ux_map.build(product, conf)
    return ux_config.load(product)


def test_a_discovery_round_needs_a_map_first(product):
    conf = ux_config.load(product)
    with pytest.raises(ValueError, match=re.escape("map the product first: crissp/ux.sh --map")):
        ux_team.request(product, conf, "discovery", "product")
    with pytest.raises(ValueError, match="a discovery round is about the whole product"):
        ux_team.request(product, _mapped(product), "discovery", "first-visit")


def test_a_discovery_round_gives_every_persona_their_jobs_and_every_screen(product):
    conf = _mapped(product)
    assert ux_team.request(product, conf, "discovery", "product") == {"started": {"kind": "discovery", "walk": "product", "version": 1}}
    vdir = product.results / "discovery" / "product" / "d1"
    prompt = ux_team.popen.started[0].cmd[2]
    assert "DISCOVERY" in prompt and '"explore tech", "explore phone"' in prompt and "explore ux" not in prompt
    assert "jobs: Pay for an order" in prompt and "no jobs written" in prompt  # tech has none: two inferred from the brief
    assert "/ · The first screen (area home)" in prompt and str(product.results / "shots" / "first-visit" / "laptop") in prompt
    assert '"verdict": "done|hard|impossible"' in prompt.replace("{{", "{") and str(vdir / "discovery.json") in prompt
    screens = json.loads((vdir / "inputs" / "screens.json").read_text())
    assert screens[0]["key"] == "/" and screens[0]["pictures"][0]["file"].endswith("01-the-first-screen.png")
    assert json.loads((vdir / "inputs" / "context.json").read_text()) == {"discovery": [], "decisions": []}
    ux_team.popen.started[0].end(0)
    finish(product, "discovery", "product", 1, FOUND)
    assert ux_team.versions(product, "discovery", "product")[0]["result"]["needs"][0]["title"] == "Pay on a phone"
    ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "reject", "reason": "not now"})
    ux_team.request(product, conf, "discovery", "product")
    context = json.loads((product.results / "discovery" / "product" / "d2" / "inputs" / "context.json").read_text())
    assert context["discovery"] == [FOUND] and context["decisions"][0]["verdict"] == "reject"


def test_an_approved_need_is_a_design_request_that_starts_a_design(product):
    conf = _mapped(product)
    finish(product, "discovery", "product", 1, FOUND)
    line = ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "approve"})
    assert line["level"] == "need" and line["title"] == "Pay on a phone"
    out = ux_verdicts.after(product, conf, line)
    assert out["walk"] == "need-pay-on-a-phone" and out["started"]["kind"] == "proposal"
    walk = json.loads((product.here / "walks" / "need-pay-on-a-phone.json").read_text())
    assert walk["need"] == "product/d1/n0" and "A checkout that fits a thumb" in walk["brief"] and "Mo" in walk["brief"]
    assert walk["steps"] == [{"do": "goto", "path": "/checkout"}, {"do": "shot", "title": "Pay on a phone"}]
    loaded = ux_config.load(product)["walks"]["need-pay-on-a-phone"]
    assert loaded["brief"] == walk["brief"] and loaded["need"] == "product/d1/n0"
    prompt = ux_team.popen.started[0].cmd[2]
    assert "THE DESIGN REQUEST" in prompt and "A checkout that fits a thumb" in prompt
    # approved again: the same request, no second walk
    ux_team.popen.started[0].end(0)
    again = ux_verdicts.after(product, ux_config.load(product), line)
    assert again["walk"] == "need-pay-on-a-phone" and len(list((product.here / "walks").glob("need-*.json"))) == 1


def test_a_need_s_walk_gets_its_own_name_and_a_screen_to_start_from(product):
    conf = _mapped(product)
    (product.here / "walks" / "need-pay-on-a-phone.json").write_text(json.dumps(
        {"title": "Other", "steps": [{"do": "shot", "title": "x"}]}))
    found = {**FOUND, "needs": [{"title": "Pay on a phone", "detail": "x", "screens": []}]}
    finish(product, "discovery", "product", 1, found)
    out = ux_verdicts.after(product, conf, ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "approve"}))
    assert out["walk"] == "need-pay-on-a-phone-2"
    walk = json.loads((product.here / "walks" / "need-pay-on-a-phone-2.json").read_text())
    assert walk["steps"][0] == {"do": "goto", "path": "/"} and "Who needs it" not in walk["brief"]


def test_a_design_request_that_cannot_start_now_still_stands(product):
    conf = _mapped(product)
    finish(product, "discovery", "product", 1, FOUND)
    product.lock.parent.mkdir(parents=True, exist_ok=True)
    product.lock.write_text("check")
    out = ux_verdicts.after(product, conf, ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "approve"}))
    assert out["walk"] == "need-pay-on-a-phone" and out["queued"] == 1


@pytest.mark.parametrize(("body", "says"), [
    ({"id": "product/d1/n5", "verdict": "approve"}, "unknown need"),
    ({"id": "product/d9/n0", "verdict": "approve"}, "unknown need"),
    ({"id": "product/d1/n0", "verdict": "agree"}, "a verdict on a need is approve or reject"),
    ({"id": "product/d1/n0", "verdict": "reject"}, "say why")])
def test_a_wrong_verdict_on_a_need_is_refused(product, body, says):
    conf = _mapped(product)
    finish(product, "discovery", "product", 1, FOUND)
    with pytest.raises(ValueError, match=says):
        ux_verdicts.record(product, conf, body)


def test_a_rejected_need_sets_nothing_going(product):
    conf = _mapped(product)
    finish(product, "discovery", "product", 1, FOUND)
    line = ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "reject", "reason": "later"})
    assert ux_verdicts.after(product, conf, line) == {}


def test_a_brief_s_first_line_names_who_and_which_jobs():
    assert ux_discovery.brief({"title": "T", "detail": "D", "personas": ["phone"], "jobs": ["Pay"]},
                              {"phone": "Mo"}) == "D\nWho needs it: Mo. For: Pay."


def test_one_discovery_round_at_a_time_and_none_during_a_check_run(product):
    conf = _mapped(product)
    ux_team.request(product, conf, "discovery", "product")
    with pytest.raises(ux_team.Busy, match="already working on this"):
        ux_team.request(product, conf, "discovery", "product")
    ux_team.popen.started[0].end(0)
    product.lock.parent.mkdir(parents=True, exist_ok=True)
    product.lock.write_text("check")
    assert ux_team.request(product, conf, "discovery", "product")["queued"] == 1


def test_a_need_approved_while_its_design_runs_keeps_its_request(product):
    conf = _mapped(product)
    finish(product, "discovery", "product", 1, FOUND)
    line = ux_verdicts.record(product, conf, {"id": "product/d1/n0", "verdict": "approve"})
    ux_verdicts.after(product, conf, line)
    out = ux_verdicts.after(product, ux_config.load(product), line)
    assert out == {"walk": "need-pay-on-a-phone", "not_started": "the team is already working on this"}
