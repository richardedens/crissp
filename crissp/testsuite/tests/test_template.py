"""What a project gets when it is CRISSPified (crissp/template/): the testsuite's skeleton and the uxsuite's part are
valid configurations once {{PRODUCT}} is filled in, and name nothing but placeholders (test_generic_names reads them)."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATE = REPO / "crissp" / "template" / "crissp"
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import project  # noqa: E402


def filled(path: Path, product: str = "Example") -> dict:
    text = path.read_text()
    assert "{{PRODUCT}}" in text  # the one name a project fills in
    return json.loads(text.replace("{{PRODUCT}}", product))


def test_the_testsuite_skeleton_is_a_valid_configuration(tmp_path):
    root = tmp_path / "example"
    (root / "crissp" / "testsuite").mkdir(parents=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(json.dumps(filled(TEMPLATE / "testsuite" / "suites.json")))
    (root / "src").mkdir()
    conf = project.load(root)
    assert conf["product"] == "Example" and [s["key"] for s in project.steps(conf, root)] == ["unit", "gate", "lint"]
    assert all(s["label"].startswith("CRISSP: ") for s in conf["steps"])  # what the project fills in is marked


def test_the_testsuite_skeleton_starts_with_no_changes_an_honest_gap_and_no_accepted_risk():
    changes = filled(TEMPLATE / "testsuite" / "changes.json")
    assert changes["changes"] == [] and len(changes["gaps"]) == 1 and changes["gaps"][0].startswith("CRISSP: ")
    assert json.loads((TEMPLATE / "testsuite" / "accepted-risks.json").read_text()) == {"accepted": []}


def test_the_uxsuite_part_is_there_with_its_own_ignore_and_no_old_ux_team():
    ux = TEMPLATE / "uxsuite"
    rules = [x for x in (ux / ".gitignore").read_text().splitlines() if x.strip() and not x.startswith("#")]
    assert rules == ["results/"]  # what the suite makes stays local
    team = filled(ux / "team.json")
    assert team["product"] == "Example" and len(team["personas"]) == 5 and sum(p["moderator"] for p in team["personas"]) == 1
    assert sorted(p.name for p in (ux / "walks").glob("*.json")) == ["first-visit.json"]
    assert not (TEMPLATE / "uxteam").exists()
