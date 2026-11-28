"""F-130: where the work is in the six stages of the agentic SDLC (Discover, Plan, Build, Verify, Review, Release),
read from what the repository says: the backlog (through the crissp tool), the release certificate, git, VERSION and
CHANGELOG.md, and the UX suite's state. Per stage what is in it, whose move it is, and how Claude or Vibe helps with
it; the stage the work is in now; the same as text for the crissp tool `stage`."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
sys.path.insert(0, str(LIB))
import stages

SERVER = LIB.parents[1] / "tool" / "server.py"
spec = importlib.util.spec_from_file_location("crissp_tool_for_stages", SERVER)
crissp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(crissp)

EPIC = """# E1 · Quality

## E1-F1 · The gate                                        [doing]

### E1-F1-01 · The gate                                   [{one}] [M]
### E1-F1-02 · Frontend tests                             [{two}] [S]
### E1-F1-03 · Security suite                             [{three}] [S]
"""
FINDINGS = """| # | Seen | Observation | Goes to |
|---|---|---|---|
| F-01 | a scan | dumps in an image | E1-F1-03 |
| F-02 | the board | a long observation that goes on and on about what was seen on the board, far past what one line \
of the page can hold | the product owner |
| F-03 | a run | it was red | fixed (0.1.0) |
| F-04 | a lint | an old rule | removed, with the lint step |
"""
DECISIONS = """| # | Question | Options | Recommendation |
|---|---|---|---|
| D-04 | Admin kubeconfigs for scans? | a) keep · b) read-only | **b** |
"""
NOTES = "# Release notes\n\n## 0.2.0 — 2026-11-28\n\n- a change\n"


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def repo(
    tmp_path: Path,
    one: str = "doing",
    two: str = "review",
    three: str = "todo",
    findings: str = FINDINGS,
    decisions: str = DECISIONS,
    notes: str = NOTES,
    commit: bool = True,
) -> Path:
    root = tmp_path / "repo"
    b = root / "crissp" / "backlog"
    (b / "done").mkdir(parents=True)
    (b / "E1-quality.md").write_text(EPIC.format(one=one, two=two, three=three))
    (b / "FINDINGS.md").write_text(findings)
    (b / "DECISIONS.md").write_text(decisions)
    (root / "VERSION").write_text("0.2.0\n")
    (root / "CHANGELOG.md").write_text(notes)
    git(root, "init", "-q")
    if commit:
        git(root, "add", "-A")
        git(root, "commit", "-qm", "first")
    return root


def certify(root: Path, commit: str | None = None, steps: dict | None = None) -> None:
    results = root / "crissp" / "testsuite" / "results"
    results.mkdir(parents=True, exist_ok=True)
    cert = {
        "commit": commit or git(root, "rev-parse", "HEAD"),
        "changes": [],
        "changed_during_run": False,
        "steps": steps or {"tools": "passed"},
    }
    (results / "release.json").write_text(json.dumps(cert))


def design(version: int, verdict=None, pbi=None, done=True) -> dict:
    return {
        "version": version,
        "key": f"home#v{version}",
        "status": {"phase": "done" if done else "working"},
        "result": {"title": f"design {version}"} if done else None,
        "verdict": verdict,
        "pbi": pbi,
    }


def ux(walks=None, **extra) -> dict:
    return {
        "product": "Shop",
        "monogram": "S",
        "walks": walks if walks is not None else [],
        "team": {"running": []},
        **extra,
    }


def walk(rounds=1, proposals=()) -> dict:
    return {
        "id": "home",
        "title": "The home page",
        "rounds": [{"version": n + 1} for n in range(rounds)],
        "proposals": list(proposals),
    }


def by(state: dict) -> dict:
    return {s["key"]: s for s in state["stages"]}


def test_the_six_stages_in_their_order_each_with_whose_move_it_is_and_help_from_claude_or_vibe(tmp_path):
    state = stages.state(repo(tmp_path), crissp, ux=ux([walk()]))
    assert [(s["key"], s["name"]) for s in state["stages"]] == [
        ("discover", "Discover"),
        ("plan", "Plan"),
        ("build", "Build"),
        ("verify", "Verify"),
        ("review", "Review"),
        ("release", "Release"),
    ]
    for s in state["stages"]:
        assert s["status"] in stages.STATUSES
        assert s["summary"]
        assert s["ask"] == f"crissp: help me with {s['name']}"
        assert s["claude"] == f'claude "{s["ask"]}"'
        assert s["vibe"] == f'vibe "{s["ask"]}"'
        assert s["prompt"].startswith(f"C.R.I.S.S.P. stage {s['name']}")
    assert (state["product"], state["monogram"]) == ("repo", "R")  # no suites.json: the folder's name
    root = tmp_path / "repo"
    (root / "crissp" / "testsuite").mkdir(exist_ok=True)
    (root / "crissp" / "testsuite" / "suites.json").write_text(
        json.dumps({"product": "Shop", "monogram": "S", "steps": []})
    )
    assert stages.state(root, crissp, ux=ux())["product"] == "Shop"


def test_build_holds_the_pbi_in_doing_and_the_next_todo_and_is_where_the_work_is(tmp_path):
    state = stages.state(repo(tmp_path), crissp, ux=ux([walk()]))
    build = by(state)["build"]
    assert build["status"] == "work"
    assert "E1-F1-01 The gate (doing)" in build["items"]
    assert "Next: E1-F1-03 Security suite" in build["items"]
    assert state["current"] == "build"
    assert "E1-F1-01" in state["why"]


def test_verify_says_how_far_head_is_from_the_last_green_state(tmp_path):
    root = repo(tmp_path, one="todo", two="todo")
    assert by(stages.state(root, crissp, ux=ux()))["verify"]["summary"].startswith("No green run yet")
    certify(root)
    verify = by(stages.state(root, crissp, ux=ux()))["verify"]
    assert verify["status"] == "clear"
    assert verify["summary"] == f"Green on {git(root, 'rev-parse', '--short', 'HEAD')}, this commit."
    first = git(root, "rev-parse", "HEAD")
    (root / "app.py").write_text("x = 1\n")
    git(root, "add", "app.py")
    git(root, "commit", "-qm", "two")
    state = stages.state(root, crissp, ux=ux())
    assert by(state)["verify"]["status"] == "work"
    assert by(state)["verify"]["summary"] == "1 commit since the last green state: crissp/check.sh tests what changed."
    assert state["current"] == "verify"
    (root / "app.py").write_text("x = 2\n")
    assert (
        "Uncommitted changes: commit first, the checks test what is committed."
        in by(stages.state(root, crissp, ux=ux()))["verify"]["items"]
    )
    certify(root, first, {"tools": "failed", "lint": "passed"})
    assert "Red in the last full run: tools." in by(stages.state(root, crissp, ux=ux()))["verify"]["items"]


def test_a_repository_without_commits_has_nothing_to_verify_or_release_yet(tmp_path):
    state = by(stages.state(repo(tmp_path, commit=False), crissp, ux=ux()))
    assert state["verify"]["status"] == "setup"
    assert state["verify"]["summary"] == "No commits yet: the checks test what is committed."
    assert state["release"]["status"] == "setup"


def test_review_lists_what_waits_for_the_product_owner_and_comes_after_a_green_build(tmp_path):
    root = repo(tmp_path, one="done", two="review")
    certify(root)
    designs = [design(1, verdict={"verdict": "approve"}, pbi="E1-F1-03"), design(2), design(3, done=False)]
    state = stages.state(root, crissp, ux=ux([walk(proposals=designs)]))
    review = by(state)["review"]
    assert review["status"] == "yours"
    assert review["items"] == [
        "E1-F1-02 Frontend tests (in review)",
        "Design home#v2 “design 2” waits for your verdict on the UX page",
    ]
    assert state["current"] == "review"
    # the UX suite's review of every screen, once it has one: what waits for the product owner there
    screens = by(stages.state(root, crissp, ux=ux(review={"waiting": 2, "screens": []})))["review"]
    assert "2 screens wait for you on the UX page's Review tab (/ux/#review)" in screens["items"]
    assert by(stages.state(root, crissp, ux=ux(review={"waiting": 0})))["review"]["items"] == [
        "E1-F1-02 Frontend tests (in review)"
    ]


def test_plan_holds_the_open_findings_decisions_and_approved_designs_without_a_pbi(tmp_path):
    root = repo(tmp_path, one="todo", two="todo")
    state = by(stages.state(root, crissp, ux=ux([walk(proposals=[design(1, verdict={"verdict": "approve"})])])))
    plan = state["plan"]
    assert plan["status"] == "yours"  # an open decision is the product owner's to take
    # a finding that names a backlog item has its place, one that was fixed or removed is done: neither is to plan
    assert plan["items"] == [
        "F-02 a long observation that goes on and on about what was seen on the board, far past what one line of "
        "the page ca… → the product owner",
        "D-04 Admin kubeconfigs for scans? (your decision)",
        "Design home#v1 “design 1” is approved and has no PBI yet",
    ]
    calm = by(stages.state(repo(tmp_path / "b", one="todo", two="todo", decisions=""), crissp, ux=ux()))["plan"]
    assert calm["status"] == "work"
    assert calm["summary"] == "Findings and approved designs to turn into PBIs."
    empty = by(stages.state(repo(tmp_path / "c", one="todo", two="todo", findings="", decisions=""), crissp, ux=ux()))
    assert (empty["plan"]["status"], empty["plan"]["summary"]) == (
        "clear",
        "Nothing to plan: every finding has its place.",
    )


def test_discover_without_a_ux_suite_offers_to_set_it_up(tmp_path):
    root = repo(tmp_path)
    discover = by(stages.state(root, crissp, ux=None))["discover"]
    assert discover["status"] == "setup"
    assert "crissp/uxsuite/team.json" in discover["summary"]
    broken = by(stages.state(root, crissp, ux={"error": "team.json: url is required"}))["discover"]
    assert (broken["status"], broken["summary"]) == (
        "setup",
        "The UX suite's configuration is wrong: team.json: url is required",
    )


def test_discover_says_what_the_team_has_not_looked_at_and_what_waits_for_a_verdict(tmp_path):
    root = repo(tmp_path)
    fresh = by(stages.state(root, crissp, ux=ux([walk(rounds=0)])))["discover"]
    assert fresh["status"] == "work"
    assert fresh["items"] == ["Walk home “The home page”: no round yet"]
    assert fresh["actions"] == [{"label": "Start a round on “The home page”", "kind": "round", "walk": "home"}]
    # the map and the discovery round (the uxsuite's Map and Jobs): read when the UX suite says them
    mapped = ux([walk()], map=None, discovery=[])
    unmapped = by(stages.state(root, crissp, ux=mapped))["discover"]
    assert "The product is not mapped yet: crissp ux --map" in unmapped["items"]
    needs = ux(
        [walk()],
        map={"screens": [{"gaps": ["no walk looks at it"]}, {"gaps": []}], "gaps": 1},
        discovery=[
            {
                "version": 1,
                "needs": [
                    {"id": "product/d1/n0", "verdict": None},
                    {"id": "product/d1/n1", "verdict": {"verdict": "approve"}},
                ],
            }
        ],
    )
    waiting = by(stages.state(root, crissp, ux=needs))["discover"]
    assert waiting["status"] == "yours"
    assert waiting["items"] == [
        "2 screens mapped: 1 no walk looks at, 1 no link reaches",
        "1 need from the discovery round waits for your verdict on the UX page",
    ]
    assert waiting["actions"] == [{"label": "Start a discovery round", "kind": "discovery", "walk": "product"}]
    unfilled = by(stages.state(root, crissp, ux=ux([walk()], placeholders=["about", "audience"])))["discover"]
    assert (unfilled["status"], unfilled["summary"]) == (
        "setup",
        "The UX suite is not filled in yet: team.json still says what belongs in about, audience.",
    )
    busy = by(stages.state(root, crissp, ux=ux([walk()], team={"running": ["round:home"]})))["discover"]
    assert busy["items"] == ["The UX team works on round:home"]
    assert busy["status"] == "work"
    calm = by(stages.state(root, crissp, ux=ux([walk()])))["discover"]
    assert calm["status"] == "clear"


def test_release_is_ready_for_the_product_owner_once_green_on_head_with_notes_and_no_tag(tmp_path):
    root = repo(tmp_path, one="todo", two="todo")
    certify(root)
    state = stages.state(root, crissp, ux=ux())
    release = by(state)["release"]
    assert release["status"] == "yours"
    assert (
        release["summary"] == "0.2.0 is green and has its release notes: yours to tag (git tag v0.2.0, then push it)."
    )
    no_notes = repo(tmp_path / "b", one="todo", two="todo", notes="# Release notes\n\n## 0.1.0 — old\n")
    certify(no_notes)
    assert "CHANGELOG.md has no entry for 0.2.0 yet" in by(stages.state(no_notes, crissp, ux=ux()))["release"]["items"]
    git(root, "tag", "v0.2.0")
    assert by(stages.state(root, crissp, ux=ux()))["release"]["status"] == "clear"
    (root / "app.py").write_text("x = 1\n")
    git(root, "add", "app.py")
    git(root, "commit", "-qm", "after")
    after = by(stages.state(root, crissp, ux=ux()))["release"]
    assert after["status"] == "work"
    assert (
        after["summary"]
        == "0.2.0 is tagged; 1 commit since: the next version needs its number in VERSION and its notes."
    )


def test_the_stage_the_work_is_in_follows_the_flow(tmp_path):
    root = repo(tmp_path, one="todo", two="todo", findings="", decisions="")
    certify(root)
    git(root, "tag", "v0.2.0")
    assert stages.state(root, crissp, ux=ux([walk()]))["current"] == "build"  # the next todo
    done = repo(tmp_path / "b", one="done", two="done", three="done", decisions="")
    certify(done)
    git(done, "tag", "v0.2.0")
    state = stages.state(done, crissp, ux=ux([walk(rounds=0)]))
    assert (state["current"], by(state)["build"]["status"]) == ("plan", "clear")
    calm = repo(tmp_path / "c", one="done", two="done", three="done", findings="", decisions="")
    certify(calm)
    git(calm, "tag", "v0.2.0")
    assert stages.state(calm, crissp, ux=ux([walk(rounds=0)]))["current"] == "discover"
    release = repo(tmp_path / "d", one="done", two="done", three="done", findings="", decisions="")
    certify(release)
    assert stages.state(release, crissp, ux=ux([walk()]))["current"] == "release"


def test_every_stage_prompt_keeps_the_product_owner_s_rules(tmp_path):
    for key, prompt in stages.PROMPTS.items():
        assert "never" in prompt.lower(), key
    assert "test that fails without the change" in stages.PROMPTS["build"]
    assert "never move anything to done" in stages.PROMPTS["review"]
    assert "never tag, push or publish" in stages.PROMPTS["release"]
    assert "crissp ux --map" in stages.PROMPTS["discover"]
    assert "check-all" in stages.PROMPTS["verify"]


def test_the_text_for_the_crissp_tool_says_where_the_work_is_and_how_to_help(tmp_path):
    state = stages.state(repo(tmp_path), crissp, ux=ux([walk()]))
    text = stages.text(state)
    lines = text.splitlines()
    assert lines[0] == f"The work is in Build: {state['why']}"
    assert any(line.startswith("→ Build · work") for line in lines)
    assert any(line.startswith("  Review · yours") for line in lines)
    assert "  - E1-F1-02 Frontend tests (in review)" in lines
    assert lines[-1].startswith("To help with a stage: call stage with stage: <discover")
    one = stages.text(state, "plan")
    assert one.splitlines()[0].startswith("Plan · ")
    assert stages.PROMPTS["plan"] in one
    with pytest.raises(ValueError, match="stage is one of discover, plan, build, verify, review, release"):
        stages.text(state, "deploy")


def test_the_ux_suite_s_state_is_read_from_the_project_when_it_has_one(tmp_path, monkeypatch):
    root = repo(tmp_path)
    assert stages.ux_state(root) is None  # no crissp/uxsuite/team.json
    here = root / "crissp" / "uxsuite"
    (here / "walks").mkdir(parents=True)
    (here / "team.json").write_text(
        json.dumps(
            {
                "product": "Shop",
                "url": "http://127.0.0.1:5173",
                "personas": [
                    {
                        "key": "mod",
                        "name": "Mo",
                        "role": "moderator",
                        "device": "desktop",
                        "moderator": True,
                        "brief": "leads",
                    }
                ],
            }
        )
    )
    (here / "walks" / "home.json").write_text(json.dumps({"title": "Home", "steps": [{"do": "shot", "title": "home"}]}))
    got = stages.ux_state(root)
    assert [w["id"] for w in got["walks"]] == ["home"] and got["placeholders"] == []
    team = json.loads((here / "team.json").read_text())
    (here / "team.json").write_text(
        json.dumps(
            {
                **team,
                "about": "CRISSP: what the product is",
                "rounds": 2,
                "_note": "CRISSP: a note for whoever fills it in",
            }
        )
    )
    assert stages.ux_state(root)["placeholders"] == ["about"]  # what crissp init left for the product owner to fill in
    (here / "team.json").write_text(json.dumps({"product": "Shop"}))
    assert "error" in stages.ux_state(root) and "placeholders" not in stages.ux_state(root)
    monkeypatch.setattr(stages, "UX_API", tmp_path / "missing.py")
    assert stages.ux_state(root) is None
    state = stages.state(root, crissp)  # read from the project itself when not given
    assert by(state)["discover"]["status"] == "setup"


def test_the_crissp_tool_is_loaded_from_the_project_or_the_engine(tmp_path):
    root = repo(tmp_path)
    assert stages.tool(root).__name__ == "crissp_tool_for_the_stages"
    state = stages.state(root, ux=ux())
    assert by(state)["build"]["status"] == "work"
