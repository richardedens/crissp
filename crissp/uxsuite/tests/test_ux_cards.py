"""Personas and rules as files the project owns (ux_cards, E7-F1-01 and E7-F2-01): one Markdown file each, read and
checked with clear errors, written by the page, and the old places (team.json's personas, PRINCIPLES.md's sections)
still read until the first write moves them into files."""

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ux_cards
from ux_kit import PERSONAS, make_product, ux_config

PRINCIPLES = """# Design principles

How the team uses them: every round judges against them.

## 1. Nothing important behind a scroll

The primary action is visible without scrolling.

## 2. Three clicks

Within three clicks a person is where they need to be.
"""


@pytest.fixture
def suite(tmp_path):
    s = make_product(tmp_path)
    (s.here / "PRINCIPLES.md").write_text(PRINCIPLES)
    return s


def persona_file(suite, key, text):
    (suite.here / "personas").mkdir(exist_ok=True)
    (suite.here / "personas" / f"{key}.md").write_text(text)


SAM = """---
name: Sam
role: software engineer
device: desktop
---
Notices states.

## Jobs

- Find why a run is red
- Undo a change
"""
ADA = "---\nname: Ada\n\nrole: UX expert\ndevice: both\nmoderator: true\n---\nModerates.\n"


def test_a_persona_file_is_read_with_its_jobs_and_defaults(suite):
    persona_file(suite, "sam", SAM)
    persona_file(suite, "ada", ADA)
    conf = ux_config.load(suite)
    assert [p["key"] for p in conf["personas"]] == ["ada", "sam"]  # the files, in name order; team.json's are not read
    sam = conf["personas"][1]
    assert sam == {"key": "sam", "name": "Sam", "role": "software engineer", "device": "desktop", "moderator": False,
                   "on": True, "brief": "Notices states.", "jobs": ["Find why a run is red", "Undo a change"]}
    assert conf["personas"][0]["moderator"] is True and conf["personas"][0]["jobs"] == []
    assert conf["personas_from"] == "files"


def test_without_files_team_json_still_holds_the_personas(suite):
    conf = ux_config.load(suite)
    assert [p["key"] for p in conf["personas"]] == [p["key"] for p in PERSONAS] and conf["personas_from"] == "team.json"
    assert all(p["on"] and p["jobs"] == [] for p in conf["personas"])
    team = json.loads((suite.here / "team.json").read_text())
    team["personas"][0] = {**team["personas"][0], "on": False, "jobs": ["Pay"]}
    (suite.here / "team.json").write_text(json.dumps(team))
    first = ux_config.load(suite)["personas"][0]
    assert (first["on"], first["jobs"]) == (False, ["Pay"])
    team["personas"][0]["jobs"] = "Pay"
    (suite.here / "team.json").write_text(json.dumps(team))
    with pytest.raises(ux_config.ConfigError, match=re.escape("team.json: persona 1: jobs must be a list of texts")):
        ux_config.load(suite)


@pytest.mark.parametrize("name, text, says", [
    ("sam", "name: Sam\n", "personas/sam.md: it must start with a --- block (name, role, device …)"),
    ("sam", "---\nname: Sam\n", "personas/sam.md: the --- block is not closed"),
    ("sam", "---\nname Sam\n---\nx\n", "personas/sam.md: line 2 must be key: value"),
    ("sam", "---\nname: Sam\ncolour: red\n---\nx\n", "personas/sam.md: unknown field colour"),
    ("sam", "---\nrole: x\n---\nx\n", "personas/sam.md: name must be a text"),
    ("sam", "---\nname: Sam\nrole: x\ndevice: watch\n---\nx\n", "personas/sam.md: device must be one of"),
    ("sam", "---\nname: Sam\nrole: x\non: maybe\n---\nx\n", "personas/sam.md: on must be true or false"),
    ("sam", "---\nname: Sam\nrole: x\n---\n\n## Jobs\n- a\n", "personas/sam.md: the brief (the text under the --- block) is empty"),
    ("Sam Smith", SAM, "personas/Sam Smith.md: the file name must be lower case letters"),
])
def test_a_wrong_persona_file_is_named_with_what_is_wrong(suite, name, text, says):
    persona_file(suite, name, text)
    persona_file(suite, "ada", ADA)
    with pytest.raises(ux_config.ConfigError) as e:
        ux_config.load(suite)
    assert says in str(e.value)


def test_the_team_needs_someone_on_and_a_moderator_on(suite):
    persona_file(suite, "sam", SAM)
    with pytest.raises(ux_config.ConfigError, match="one persona that is on must be the moderator"):
        ux_config.load(suite)
    persona_file(suite, "ada", ADA.replace("moderator: true", "moderator: true\non: false"))
    with pytest.raises(ux_config.ConfigError, match="one persona that is on must be the moderator"):
        ux_config.load(suite)


def test_the_page_adds_a_persona_and_the_first_write_moves_team_json_s_into_files(suite):
    out = ux_cards.save_persona(suite, {"name": "Gerda", "role": "retired, 71", "device": "desktop",
                                        "brief": "Rarely uses a computer.", "jobs": "See what it costs\n\n Know what happens next "})
    files = sorted(p.stem for p in (suite.here / "personas").glob("*.md"))
    assert files == sorted([*(p["key"] for p in PERSONAS), "gerda"])
    assert [p["key"] for p in out["personas"]] == [*(p["key"] for p in PERSONAS), "gerda"]  # team.json's order, the new one last
    ux_cards.save_persona(suite, {"key": "phone", "name": "Mo", "role": "student", "device": "mobile", "brief": "Thumb."})
    assert [p["key"] for p in ux_config.load(suite)["personas"]][1] == "phone"  # an edit keeps its place
    assert "personas" not in json.loads((suite.here / "team.json").read_text())  # one place for the team from now on
    gerda = next(p for p in out["personas"] if p["key"] == "gerda")
    assert gerda["jobs"] == ["See what it costs", "Know what happens next"] and gerda["on"] is True
    assert ux_config.load(suite)["personas_from"] == "files"
    again = ux_cards.read_persona(suite.here / "personas" / "gerda.md")
    assert again == gerda  # what is written reads back the same


def test_the_page_edits_switches_off_and_removes_a_persona(suite):
    ux_cards.save_persona(suite, {"key": "tech", "name": "Sam", "role": "lead engineer", "device": "both",
                                  "brief": "Notices states.", "on": False})
    sam = next(p for p in ux_config.load(suite)["personas"] if p["key"] == "tech")
    assert (sam["role"], sam["device"], sam["on"], sam["jobs"]) == ("lead engineer", "both", False, [])
    out = ux_cards.remove_persona(suite, "phone")
    assert [p["key"] for p in out["personas"]] == ["tech", "ux"]
    with pytest.raises(LookupError, match="no persona 'phone'"):
        ux_cards.remove_persona(suite, "phone")


@pytest.mark.parametrize("body, says", [
    ({"name": "", "role": "x", "brief": "y"}, "name must be a text"),
    ({"name": "Bo", "role": "x", "brief": "y", "device": "watch"}, "device must be one of"),
    ({"name": "Bo", "role": "x", "brief": "y", "key": "Bo Bo"}, "key 'Bo Bo' must be lower case letters"),
    ({"name": "Bo", "role": "x", "brief": "y", "jobs": 7}, "jobs must be a text or a list of texts"),
    ({"name": "Bo", "role": "x\ny", "brief": "y"}, "role must be one line"),
    ({"name": "Bo", "role": "x", "brief": "y", "on": "yes"}, "on must be true or false"),
    ({"name": "!!!", "role": "x", "brief": "y"}, "give the persona a key"),
    ({"key": "ux", "name": "Ada", "role": "UX", "brief": "y", "moderator": False}, "one persona that is on must be the moderator"),
])
def test_a_wrong_persona_from_the_page_is_refused_and_nothing_is_written(suite, body, says):
    with pytest.raises(ValueError, match=says):
        ux_cards.save_persona(suite, body)
    assert not (suite.here / "personas").exists() and "personas" in json.loads((suite.here / "team.json").read_text())


def test_the_last_moderator_cannot_be_removed(suite):
    with pytest.raises(ValueError, match="one persona that is on must be the moderator"):
        ux_cards.remove_persona(suite, "ux")
    assert (suite.here / "personas").exists() is False


# ------------------------------------------------------------------------------------------------------- the rules

def test_without_rule_files_the_principles_sections_are_the_rules(suite):
    assert ux_cards.rules(suite) == [
        {"id": "01-nothing-important-behind-a-scroll", "title": "Nothing important behind a scroll", "severity": "should",
         "on": True, "text": "The primary action is visible without scrolling."},
        {"id": "02-three-clicks", "title": "Three clicks", "severity": "should", "on": True,
         "text": "Within three clicks a person is where they need to be."}]
    assert ux_cards.rules_from(suite) == "PRINCIPLES.md"
    (suite.here / "PRINCIPLES.md").unlink()
    assert ux_cards.rules(suite) == [] and ux_cards.rules_from(suite) == "none"


def test_the_first_rule_written_moves_the_principles_into_files_and_keeps_their_intro(suite):
    out = ux_cards.save_rule(suite, {"title": "Prices before commitment", "severity": "must",
                                     "text": "A person sees what it costs before they commit."})
    assert [r["id"] for r in out["rules"]] == ["01-nothing-important-behind-a-scroll", "02-three-clicks",
                                               "prices-before-commitment"]
    left = (suite.here / "PRINCIPLES.md").read_text()
    assert "How the team uses them" in left and "## 1." not in left and "rules/" in left
    assert ux_cards.read_rule(suite.here / "rules" / "prices-before-commitment.md") == out["rules"][2]
    out = ux_cards.save_rule(suite, {"id": "02-three-clicks", "title": "Three clicks", "severity": "could", "on": False,
                                     "text": "Within three clicks."})
    assert out["rules"][1] == {"id": "02-three-clicks", "title": "Three clicks", "severity": "could", "on": False,
                               "text": "Within three clicks."}
    assert [r["id"] for r in ux_cards.remove_rule(suite, "02-three-clicks")["rules"]] == [
        "01-nothing-important-behind-a-scroll", "prices-before-commitment"]
    with pytest.raises(LookupError, match="no rule '02-three-clicks'"):
        ux_cards.remove_rule(suite, "02-three-clicks")


def test_without_principles_the_first_rule_is_simply_written(suite):
    (suite.here / "PRINCIPLES.md").unlink()
    out = ux_cards.save_rule(suite, {"title": "Plain words", "text": "No jargon."})
    assert out["rules"] == [{"id": "plain-words", "title": "Plain words", "severity": "should", "on": True, "text": "No jargon."}]
    assert not (suite.here / "PRINCIPLES.md").exists()


@pytest.mark.parametrize("body, says", [
    ({"title": "", "text": "x"}, "title must be a text"),
    ({"title": "A", "text": ""}, "text must be a text"),
    ({"title": "A", "text": "x", "severity": "nice"}, "severity must be one of must, should, could"),
    ({"title": "...", "text": "x"}, "give the rule an id"),
])
def test_a_wrong_rule_from_the_page_is_refused(suite, body, says):
    with pytest.raises(ValueError, match=says):
        ux_cards.save_rule(suite, body)
    assert not (suite.here / "rules").exists()


@pytest.mark.parametrize("text, says", [
    ("---\ntitle: A\nseverity: nice\n---\nx\n", "rules/a.md: severity must be one of must, should, could"),
    ("---\ntitle: A\n---\n\n", "rules/a.md: the rule's text (under the --- block) is empty"),
    ("---\ntitle: A\nwho: me\n---\nx\n", "rules/a.md: unknown field who"),
])
def test_a_wrong_rule_file_is_named(suite, text, says):
    (suite.here / "rules").mkdir()
    (suite.here / "rules" / "a.md").write_text(text)
    with pytest.raises(ux_config.ConfigError) as e:
        ux_cards.rules(suite)
    assert says in str(e.value)


def test_the_rules_that_hold_are_written_for_a_run(suite):
    ux_cards.save_rule(suite, {"id": "02-three-clicks", "title": "Three clicks", "severity": "must", "on": False, "text": "x"})
    text = ux_cards.rules_for_a_run(ux_cards.rules(suite))
    assert "## 01-nothing-important-behind-a-scroll · Nothing important behind a scroll (should)" in text
    assert "three-clicks" not in text
    assert ux_cards.rules_for_a_run([]) == "(no rules yet: judge by the principles alone)\n"
