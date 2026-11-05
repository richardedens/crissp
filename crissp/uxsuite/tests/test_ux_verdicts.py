"""The product owner's verdicts (ux_verdicts) and what they set going: an approved design becomes one PBI in the
backlog, written by the crissp tool in the backlog's own format (ux_backlog); a redo is the next design's focus."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PROPOSAL, ROUND, add_shots, finish, product, ux_config, ux_team  # noqa: E402,F401

import ux_backlog  # noqa: E402
import ux_verdicts  # noqa: E402


@pytest.fixture
def done(product):
    """A walk with a finished round and a finished design."""
    add_shots(product)
    finish(product, "round", "first-visit", 1, ROUND)
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    return product


def test_a_verdict_on_advice_is_one_line_and_the_latest_holds(done):
    conf = ux_config.load(done)
    line = ux_verdicts.record(done, conf, {"id": "first-visit/r1/a0", "verdict": "later"})
    assert line["level"] == "advice" and line["title"] == "Bigger buttons" and line["reason"] == ""
    ux_verdicts.record(done, conf, {"id": "first-visit/r1/a0", "verdict": "disagree", "reason": " too big "})
    assert ux_verdicts.latest(done)["first-visit/r1/a0"]["reason"] == "too big"
    assert len((done.results / "decisions.jsonl").read_text().splitlines()) == 2  # history kept
    assert ux_verdicts.after(done, conf, line) == {}


@pytest.mark.parametrize("body, says", [
    ({"id": "first-visit/r1/a5", "verdict": "agree"}, "unknown advice"),
    ({"id": "first-visit/r9/a0", "verdict": "agree"}, "unknown advice"),
    ({"id": "elsewhere/r1/a0", "verdict": "agree"}, "unknown advice"),
    ({"id": "first-visit/r1/a0", "verdict": "approve"}, "agree, disagree or later"),
    ({"id": "first-visit/r1/a0", "verdict": "disagree"}, "say why"),
    ({"id": "first-visit#v2", "verdict": "approve"}, "unknown design"),
    ({"id": "elsewhere#v1", "verdict": "approve"}, "unknown design"),
    ({"id": "first-visit#v1", "verdict": "agree"}, "approve, redo or reject"),
    ({"id": "first-visit#v1", "verdict": "reject"}, "say why"),
    ({"id": "../etc", "verdict": "agree"}, "unknown item"),
    ({"verdict": "agree"}, "unknown item"),
    ({"id": "first-visit/r1/a0", "verdict": "agree", "reason": "x" * 4001}, "too long"),
])
def test_a_wrong_verdict_is_refused_and_not_written(done, body, says):
    with pytest.raises(ValueError, match=says):
        ux_verdicts.record(done, ux_config.load(done), body)
    assert not (done.results / "decisions.jsonl").exists()


def test_an_approved_design_becomes_one_pbi_in_the_backlog_s_own_format(done):
    conf = ux_config.load(done)
    line = ux_verdicts.record(done, conf, {"id": "first-visit#v1", "verdict": "approve"})
    assert line["level"] == "design" and line["title"] == "Calmer start"
    assert ux_verdicts.after(done, conf, line) == {"pbi": "E1-F1-01"}
    epic = (done.root / "crissp" / "backlog" / "E1-ux-approved-designs.md").read_text()
    assert epic.startswith("# E1 · UX: approved designs") and "## E1-F1 · UX · First visit" in epic
    assert "### E1-F1-01 · Calmer start" in epic and "[todo] [S]" in epic
    assert "1. [must] One primary button" in epic and "UX proposal `first-visit#v1`" in epic
    crissp = ux_backlog.tool(done)
    assert crissp.backlog(done.root, {"id": "E1-F1-01"}).startswith("crissp/backlog/E1-ux-approved-designs.md")
    # approved again (or the results lost and approved anew): still the one PBI
    assert ux_verdicts.after(done, conf, line) == {"pbi": "E1-F1-01"}
    assert ux_backlog.pbis(done) == {"first-visit#v1": "E1-F1-01"}
    # a second design of the walk: the same epic and feature, the next PBI
    finish(done, "proposal", "first-visit", 2, {"changes": [{"what": f"c{i}"} for i in range(6)]})
    assert ux_backlog.file_pbi(done, conf, "first-visit", 2, ux_verdicts._result(done, "proposal", "first-visit", 2)) == "E1-F1-02"
    text = (done.root / "crissp" / "backlog" / "E1-ux-approved-designs.md").read_text()
    assert "### E1-F1-02 · First visit: approved design v2" in text and "[todo] [M]" in text and "[should] c0" in text


def test_the_epic_can_be_named_and_a_big_design_is_large(done):
    crissp = ux_backlog.tool(done)
    crissp.epic(done.root, {"title": "Shop", "why": "the shop"})
    crissp.feature(done.root, {"epic": "E1", "title": "Checkout", "why": "pay"})  # work that is not from the UX suite
    crissp.item(done.root, {"feature": "E1-F1", "title": "Pay", "size": "S", "why": "w", "what": "w", "done_when": "w",
                            "tests": "w"})
    conf = {**ux_config.load(done), "backlog": {"epic": "E1", "epic_title": "unused"}}
    pid = ux_backlog.file_pbi(done, conf, "first-visit", 1, {"title": "A | B", "changes": [{"what": "x"}] * 11, "summary": ""})
    text = (done.root / "crissp" / "backlog" / "E1-shop.md").read_text()
    assert pid == "E1-F2-01" and "A / B" in text and "[L]" in text
    with pytest.raises(LookupError, match="E7 is not an open epic"):
        ux_backlog.file_pbi(done, {**conf, "backlog": {"epic": "E7", "epic_title": ""}}, "first-visit", 2, {})


def test_an_existing_ux_epic_is_found_by_its_title(done):
    crissp = ux_backlog.tool(done)
    crissp.epic(done.root, {"title": "Other", "why": "w"})
    crissp.epic(done.root, {"title": "UX: approved designs", "why": "w"})
    assert ux_backlog.file_pbi(done, ux_config.load(done), "first-visit", 1, PROPOSAL) == "E2-F1-01"


def test_without_the_crissp_tool_no_pbi_is_written(done, monkeypatch):
    (done.root / "crissp" / "tool" / "server.py").unlink()
    monkeypatch.setattr(ux_backlog, "ENGINE_TOOL", done.root / "no-engine" / "server.py")
    with pytest.raises(LookupError, match="written by the crissp tool only"):
        ux_backlog.tool(done)


def test_a_redo_is_the_focus_of_the_next_design(done):
    conf = ux_config.load(done)
    line = ux_verdicts.record(done, conf, {"id": "first-visit#v1", "verdict": "redo", "reason": "keep the logo"})
    assert ux_verdicts.after(done, conf, line) == {"started": {"kind": "proposal", "walk": "first-visit", "version": 2}}
    assert "keep the logo" in ux_team.popen.started[0].cmd[2]
    assert "not_started" in ux_verdicts.after(done, conf, line)  # the team works on it already: the verdict stands
    reject = ux_verdicts.record(done, conf, {"id": "first-visit#v1", "verdict": "reject", "reason": "no"})
    assert ux_verdicts.after(done, conf, reject) == {}
    assert json.loads((done.results / "decisions.jsonl").read_text().splitlines()[-1])["verdict"] == "reject"


def test_an_installed_project_writes_with_the_engines_tool(done):
    """A project made with `crissp init` has no crissp/tool of its own: the package's tool writes its backlog."""
    (done.root / "crissp" / "tool" / "server.py").unlink()
    crissp = ux_backlog.tool(done)
    assert Path(crissp.__file__).resolve() == ux_backlog.ENGINE_TOOL.resolve()
    assert crissp.ROOT is not None and hasattr(crissp, "item")


def test_an_approval_with_a_remark_carries_the_remark_into_the_pbi(done):
    """Approve with a remark: the product owner's words are the first thing the builder reads in the PBI."""
    conf = ux_config.load(done)
    line = ux_verdicts.record(done, conf, {"id": "first-visit#v1", "verdict": "approve",
                                           "reason": "Yes, but keep the old logo and no pop-up."})
    assert line["reason"] == "Yes, but keep the old logo and no pop-up."
    assert ux_verdicts.after(done, conf, line) == {"pbi": "E1-F1-01"}
    epic = (done.root / "crissp" / "backlog" / "E1-ux-approved-designs.md").read_text()
    what = next(row for row in epic.splitlines() if row.startswith("What"))
    assert "The product owner's remark: Yes, but keep the old logo and no pop-up." in what
    assert what.index("remark") < what.index("1. [must] One primary button")  # the remark comes first


def test_an_approval_without_a_remark_says_nothing_extra(done):
    conf = ux_config.load(done)
    ux_verdicts.after(done, conf, ux_verdicts.record(done, conf, {"id": "first-visit#v1", "verdict": "approve"}))
    assert "remark" not in (done.root / "crissp" / "backlog" / "E1-ux-approved-designs.md").read_text()
