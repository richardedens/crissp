"""F-153: a project switches one lint rule off with a reason, as it accepts a risk: crissp/testsuite/lint-exceptions.json
({"exceptions": [{"rule", "why", "by", "since"}]}). Its findings are not counted, every run says how many there were,
and the dashboard lists the rules that are off: never silent. An incomplete entry is red and switches nothing off."""

import json
import sys
from pathlib import Path

import pytest
from test_lint_ratchet import lint

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "lib"))
import lint_ratchet

AUTOFOCUS = {
    "rule": "jsx-a11y/no-autofocus",
    "why": "a dialog focuses its first field on purpose",
    "by": "the product owner",
    "since": "2026-11-28",
}


@pytest.fixture
def shop(tmp_path):
    front = tmp_path / "app/frontend/src"
    front.mkdir(parents=True)
    (front / "dialog.jsx").write_text("x\n")
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    return tmp_path


def exceptions(root: Path, entries) -> None:
    (root / lint_ratchet.EXCEPTIONS).write_text(json.dumps({"exceptions": entries}))


FOUND = {"src/dialog.jsx": ["jsx-a11y/no-autofocus", "jsx-a11y/no-autofocus"]}


def test_a_rule_switched_off_with_a_reason_is_not_counted_and_the_run_says_so(shop, capsys):
    assert lint(shop, FOUND) == 1
    capsys.readouterr()
    exceptions(shop, [AUTOFOCUS])
    assert lint(shop, FOUND) == 0
    out = capsys.readouterr().out
    assert (
        "jsx-a11y/no-autofocus is off (crissp/testsuite/lint-exceptions.json): a dialog focuses its first field on "
        "purpose (the product owner, since 2026-11-28); 2 not counted"
    ) in out
    assert lint(shop, {"src/dialog.jsx": ["jsx-a11y/no-autofocus", "no-undef"]}) == 1  # the other rules still count


@pytest.mark.parametrize(
    "entries, problem",
    [
        ([{**AUTOFOCUS, "why": " "}], "exception 1 lacks why, so it switches nothing off"),
        (["jsx-a11y/no-autofocus"], "exception 1 lacks rule, why, by, since"),
        ([{**AUTOFOCUS, "since": "last week"}], "exception 1 (jsx-a11y/no-autofocus): since is a date, YYYY-MM-DD"),
    ],
)
def test_an_incomplete_exception_is_red_and_switches_nothing_off(shop, capsys, entries, problem):
    exceptions(shop, entries)
    assert lint(shop, FOUND) == 1
    out = capsys.readouterr().out
    assert problem in out and "Found 2 errors." in out


def test_a_broken_exceptions_file_is_red(shop, capsys):
    (shop / lint_ratchet.EXCEPTIONS).write_text("{")
    assert lint(shop, {}) == 1
    assert "lint-exceptions.json is not JSON" in capsys.readouterr().out
    (shop / lint_ratchet.EXCEPTIONS).write_text('{"exceptions": {}}')
    assert lint(shop, {}) == 1
    assert 'go in a list, "exceptions"' in capsys.readouterr().out
    assert lint_ratchet.exceptions(shop / "elsewhere") == ([], [])
