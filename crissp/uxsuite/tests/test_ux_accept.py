"""Accepting what was built (E7-F5-01): once an approved design is built and its walk shot again, the new screenshots sit
next to the design; accept moves its PBI to review, not good sends it back to doing with the reason as a finding."""

import json
import os
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PROPOSAL, add_shots, finish, product, ux_config, ux_team  # noqa: F401

# isort: split
import ux_backlog  # ux_kit put the uxsuite on sys.path
import ux_verdicts


@pytest.fixture
def approved(product):
    """A walk with an approved design and its PBI."""
    add_shots(product)
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    conf = ux_config.load(product)
    ux_verdicts.after(product, conf, ux_verdicts.record(product, conf, {"id": "first-visit#v1", "verdict": "approve"}))
    return product


def _shoot_again(suite, later=120):
    shots = suite.results / "shots" / "first-visit" / "shots.json"
    os.utime(shots, (time.time() + later, time.time() + later))


def _status(suite, pbi="E1-F1-01"):
    return next(i["status"] for i in ux_backlog.tool(suite).items(suite.root) if i["id"] == pbi)


def test_the_walk_knows_when_it_was_last_shot(product):
    assert ux_team.shot_at(product, "first-visit") is None
    add_shots(product)
    at = datetime.fromisoformat(ux_team.shot_at(product, "first-visit"))
    assert abs((at - datetime.now(UTC)).total_seconds()) < 5


def test_a_built_screen_is_judged_only_after_the_walk_was_shot_again(approved):
    conf = ux_config.load(approved)
    with pytest.raises(
        ValueError, match=re.escape("shoot the walk again once it is built: crissp/ux.sh --shoot first-visit")
    ):
        ux_verdicts.record(approved, conf, {"id": "first-visit#v1/built", "verdict": "accept"})
    _shoot_again(approved)
    line = ux_verdicts.record(approved, conf, {"id": "first-visit#v1/built", "verdict": "accept"})
    assert line["level"] == "built" and line["title"] == "Calmer start"
    assert ux_verdicts.after(approved, conf, line) == {
        "pbi": "E1-F1-01",
        "moved": "E1-F1-01 [todo] → [review], in crissp/backlog/E1-ux-approved-designs.md",
    }
    assert _status(approved) == "review"


def test_not_good_sends_the_pbi_back_with_the_reason(approved):
    conf = ux_config.load(approved)
    _shoot_again(approved)
    with pytest.raises(ValueError, match="say why"):
        ux_verdicts.record(approved, conf, {"id": "first-visit#v1/built", "verdict": "send-back"})
    line = ux_verdicts.record(
        approved,
        conf,
        {"id": "first-visit#v1/built", "verdict": "send-back", "reason": "The button | is still grey on a phone."},
    )
    out = ux_verdicts.after(approved, conf, line)
    assert out["pbi"] == "E1-F1-01" and out["moved"].endswith("[doing], in crissp/backlog/E1-ux-approved-designs.md")
    assert out["finding"].startswith("F-")
    findings = (approved.root / "crissp" / "backlog" / "FINDINGS.md").read_text()
    assert (
        "UX suite, built design first-visit#v1 (E1-F1-01)" in findings
        and "The button / is still grey on a phone." in findings
    )
    assert _status(approved) == "doing"


@pytest.mark.parametrize(
    ("item", "verdict", "says"),
    [
        ("first-visit#v2/built", "accept", "unknown design"),
        ("first-visit#v1/built", "approve", "a verdict on a built design is accept or send-back"),
    ],
)
def test_a_wrong_verdict_on_a_built_design_is_refused(approved, item, verdict, says):
    _shoot_again(approved)
    with pytest.raises(ValueError, match=says):
        ux_verdicts.record(approved, ux_config.load(approved), {"id": item, "verdict": verdict})


def test_only_an_approved_design_can_be_accepted(product):
    add_shots(product)
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    _shoot_again(product)
    with pytest.raises(ValueError, match="only an approved design is built and accepted"):
        ux_verdicts.record(product, ux_config.load(product), {"id": "first-visit#v1/built", "verdict": "accept"})


def test_a_pbi_that_cannot_move_is_told_and_the_verdict_stands(approved):
    conf = ux_config.load(approved)
    _shoot_again(approved)
    line = ux_verdicts.record(approved, conf, {"id": "first-visit#v1/built", "verdict": "accept"})
    epic = approved.root / "crissp" / "backlog" / "E1-ux-approved-designs.md"
    epic.write_text(epic.read_text().replace("UX proposal `first-visit#v1`", "nothing"))
    assert ux_verdicts.after(approved, conf, line) == {"not_moved": "first-visit#v1 has no PBI in the backlog"}
    epic.write_text(epic.read_text().replace("nothing", "UX proposal `first-visit#v1`").replace("[todo]", "[done]"))
    assert ux_verdicts.after(approved, conf, line) == {
        "pbi": "E1-F1-01",
        "not_moved": "E1-F1-01 is done; it does not move back",
    }
    assert json.loads((approved.results / "decisions.jsonl").read_text().splitlines()[-1])["verdict"] == "accept"
