"""The UX suite's configuration (ux_config): defaults filled in, and every mistake named with where it is."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PERSONAS, REPO, WALK, make_product, ux_config  # noqa: E402


def test_a_minimal_team_gets_its_defaults(tmp_path):
    conf = ux_config.load(make_product(tmp_path))
    assert conf["product"] == "Example Shop" and conf["monogram"] == "E" and conf["url"] == "http://127.0.0.1:5173"
    assert (conf["rounds"], conf["parallel"], conf["ui_language"], conf["report_language"]) == (2, 3, "English", "English")
    assert conf["backlog"] == {"epic": None, "epic_title": "UX: approved designs"}
    assert [p["key"] for p in conf["personas"]] == ["tech", "phone", "ux"]
    assert conf["personas"][0]["moderator"] is False and conf["personas"][2]["moderator"] is True
    assert list(conf["walks"]) == ["first-visit"] and conf["walks"]["first-visit"]["title"] == "First visit"


def _team(**changes):
    team = {"product": "Example Shop", "url": "http://127.0.0.1:5173", "personas": PERSONAS}
    team.update(changes)
    return {k: v for k, v in team.items() if v is not None}


@pytest.mark.parametrize("team, says", [
    (_team(product=None), "team.json: product must be a text"),
    (_team(url="localhost:5173"), "url must start with http"),
    (_team(monogram=""), "monogram must be a text (or left out)"),
    (_team(rounds=9), "rounds must be a whole number from 1 to 5"),
    (_team(rounds=True), "rounds must be a whole number"),
    (_team(parallel=0), "parallel must be a whole number from 1 to 12"),
    (_team(backlog={"epic": "seven"}), 'backlog must be {"epic": "E<n>"}'),
    (_team(backlog=["E1"]), "backlog must be"),
    (_team(personas=[]), "personas must be a list with at least one persona"),
    (_team(personas=["Sam"]), "persona 1 must be an object"),
    (_team(personas=[{**PERSONAS[0], "key": "Sam Smith"}]), "key 'Sam Smith' must be unique"),
    (_team(personas=[PERSONAS[2], PERSONAS[2]]), "persona 2: key 'ux' must be unique"),
    (_team(personas=[{**PERSONAS[2], "device": "tablet"}]), "device must be one of desktop, mobile, both"),
    (_team(personas=[{**PERSONAS[2], "brief": " "}]), "persona 1: brief must be a text"),
    (_team(personas=PERSONAS[:2]), "one persona must be the moderator"),
])
def test_a_wrong_team_is_named(tmp_path, team, says):
    with pytest.raises(ux_config.ConfigError, match=says.replace("(", r"\(").replace(")", r"\)").replace("{", r"\{")
                       .replace("}", r"\}")):
        ux_config.load(make_product(tmp_path, team=team))


@pytest.mark.parametrize("text, says", [("", "team.json is not valid JSON"), ("[1]", "team.json must hold one JSON object")])
def test_a_broken_team_file_is_named(tmp_path, text, says):
    suite = make_product(tmp_path)
    (suite.here / "team.json").write_text(text)
    with pytest.raises(ux_config.ConfigError, match=says):
        ux_config.load(suite)
    (suite.here / "team.json").unlink()
    with pytest.raises(ux_config.ConfigError, match="team.json is missing"):
        ux_config.load(suite)


@pytest.mark.parametrize("name, walk, says", [
    ("First Visit", WALK, "the file name must be lower case"),
    ("w", {"title": "t", "steps": []}, "steps must be a list with at least one step"),
    ("w", {"title": "t", "steps": ["goto"]}, "step 1: do must be one of"),
    ("w", {"title": "t", "steps": [{"do": "fly"}]}, "step 1: do must be one of"),
    ("w", {"title": "t", "steps": [{"do": "goto"}]}, r"step 1 \(goto\) needs path"),
    ("w", {"title": "t", "steps": [{"do": "click"}]}, r"step 1 \(click\) needs text or selector"),
    ("w", {"title": "t", "steps": [{"do": "fill", "selector": "#a"}]}, r"needs value"),
    ("w", {"title": "t", "steps": [{"do": "goto", "path": "/"}]}, "at least one shot step"),
    ("w", {"steps": WALK["steps"]}, "walks/w.json: title must be a text"),
])
def test_a_wrong_walk_is_named(tmp_path, name, walk, says):
    with pytest.raises(ux_config.ConfigError, match=says):
        ux_config.load(make_product(tmp_path, walks={name: walk}))


def test_this_repository_s_own_suite_is_configured_for_its_own_pages():
    """The framework is a C.R.I.S.S.P. product too: its UX team walks the Tests dashboard and the UX suite."""
    conf = ux_config.load(ux_config.Suite(REPO))
    assert conf["product"] == "C.R.I.S.S.P." and conf["url"] == "http://127.0.0.1:8766"
    keys = {p["key"]: p for p in conf["personas"]}
    assert {"engineer", "offline", "student", "po", "ux"} <= set(keys) and keys["ux"]["moderator"]
    paths = {w: [s.get("path") for s in conf["walks"][w]["steps"] if s["do"] == "goto"] for w in conf["walks"]}
    assert paths == {"tests-overview": ["/dashboard/#overview"], "backlog-board": ["/dashboard/#board"], "ux-suite": ["/ux/"]}


def test_the_template_config_loads_once_the_product_is_filled_in(tmp_path):
    """CRISSPify copies the template and fills in {{PRODUCT}}: what it copies must load as it is."""
    template = REPO / "crissp" / "template" / "crissp" / "uxsuite"
    here = tmp_path / "crissp" / "uxsuite"
    (here / "walks").mkdir(parents=True)
    for f in [template / "team.json", *template.glob("walks/*.json")]:
        (here / f.relative_to(template)).write_text(f.read_text().replace("{{PRODUCT}}", "Example Shop"))
    conf = ux_config.load(ux_config.Suite(tmp_path))
    assert conf["product"] == "Example Shop" and len(conf["personas"]) == 5 and "first-visit" in conf["walks"]
    assert "{{PRODUCT}}" in (template / "team.json").read_text()
    for name in ("README.md", "PRINCIPLES.md", ".gitignore"):
        assert (template / name).is_file(), name
    assert "results/" in (template / ".gitignore").read_text()
    assert not (REPO / "crissp" / "template" / "crissp" / "uxteam").exists()
    assert json.loads((template / "team.json").read_text())["personas"][-1]["moderator"] is True
