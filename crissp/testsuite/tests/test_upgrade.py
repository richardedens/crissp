"""crissp/testsuite/lib/upgrade.py (F-153): the steps a newer crissp brings, said and added, nothing else."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import upgrade

TEMPLATE = {
    "steps": [{"key": "sast"}, {"key": "quality"}, {"key": "licenses"}, {"key": "dast"}],
    "audit": {"quality": {"paths": ["app"]}, "dast": {"targets": ["http://127.0.0.1:8080"]}},
}


def test_the_gap_is_said_in_words():
    assert upgrade.said({"steps": [], "audit": ["dast"], "rules": []}) == "without audit.dast → added"
    assert upgrade.said({"steps": ["dast"], "audit": ["quality", "dast"], "rules": [0]}) == (
        "without the steps dast → added from the template, with audit.quality and audit.dast (quality where sast runs)"
    )


def test_a_step_the_project_has_is_never_added_again_nor_put_on_its_rules():
    data = {"steps": [{"key": "sast"}, {"key": "quality", "run": "own"}], "paths": [{"match": "a/", "steps": ["sast"]}]}
    gap = upgrade.add(data, TEMPLATE)
    assert gap == {"steps": ["licenses", "dast"], "audit": ["quality", "dast"], "rules": []}
    assert [s.get("run") for s in data["steps"]] == [None, "own", None, None]
    assert data["paths"] == [{"match": "a/", "steps": ["sast"]}]  # its own choice: quality runs elsewhere


def test_nothing_missing_changes_nothing():
    data = {"steps": [{"key": k} for k in upgrade.NEW], "audit": dict(TEMPLATE["audit"])}
    assert upgrade.add(data, TEMPLATE) == {"steps": [], "audit": [], "rules": []}
    assert data == {"steps": [{"key": k} for k in upgrade.NEW], "audit": TEMPLATE["audit"]}
