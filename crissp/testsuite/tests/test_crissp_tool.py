"""The crissp MCP server answers from the repository's own files, exactly: the brief, and the backlog by id, status or
what is open; it writes findings, decisions and items in the backlog's own format, under the next free number, and never
accepts work (done is the product owner's). A wrong question gets an answer that says so, never a crash; it speaks MCP
over stdio."""

import io
import json
import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[3] / "crissp" / "tool" / "server.py"
spec = __import__("importlib.util").util.spec_from_file_location("crissp_server_under_test", SERVER)
srv = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(srv)

EPIC = """# E1 · Quality

### E1-01 · The gate                                   [doing] [M]
Why        a reason
### E1-02 · Frontend tests                             [review] [S]
### E1-03 · Security suite                             [todo]
"""
FINDINGS = """| # | Seen | Observation | Goes to |
|---|---|---|---|
| F-01 | a scan | dumps in an image | E5-01 |
| F-02 | the frontend | only a smoke suite | otherproject |
"""
DECISIONS = """| # | Question | Options | Recommendation |
|---|---|---|---|
| D-04 | Admin kubeconfigs for scans? | a) keep · b) read-only | **b** |
| ~~D-01~~ | A private repository. | 2026-10-23 |
"""


def _repo(tmp_path: Path, version: str = "0.1.0\n", cert: str | None = None) -> Path:
    b = tmp_path / "crissp" / "backlog"
    (b / "done").mkdir(parents=True)
    (b / "E1-quality.md").write_text(EPIC)
    (b / "done" / "E0-baseline.md").write_text("### E0-01 · Baseline   [done] [S]\nall there\n")
    (b / "FINDINGS.md").write_text(FINDINGS)
    (b / "done" / "FINDINGS.md").write_text("| F-00 | old | fixed thing | fixed (0.1.0) |\n")
    (b / "DECISIONS.md").write_text(DECISIONS)
    (tmp_path / "VERSION").write_text(version)
    if cert is not None:
        (tmp_path / "crissp" / "testsuite" / "results").mkdir(parents=True)
        (tmp_path / "crissp" / "testsuite" / "results" / "release.json").write_text(cert)
    return tmp_path


def test_the_brief_says_where_the_work_stands(tmp_path):
    text = srv.brief(_repo(tmp_path))
    assert text.splitlines() == [
        f"{tmp_path.name} 0.1.0 · commit no commits yet · release certificate: none",
        "Doing: E1-01 The gate",
        "In review (waiting for the product owner): E1-02 Frontend tests",
        "Next (first todo): E1-03 Security suite",
        "Open decisions: D-04 Admin kubeconfigs for scans?",
        "Open findings: 2 (the backlog tool with open=findings lists them)",
        "Ask the backlog tool for any F-/D-/E- id instead of reading the backlog files."]
    assert "certificate: green full run on abcdef12" in srv.brief(_repo(tmp_path / "c", cert='{"commit": "abcdef123456"}'))
    assert "certificate: none" in srv.brief(_repo(tmp_path / "d", cert="not json"))
    empty = tmp_path / "e"
    empty.mkdir()
    assert srv.brief(empty).splitlines()[:2] == ["e no VERSION · commit no commits yet · release certificate: none", "Doing: none"]


def test_the_commit_is_named_once_there_is_one(tmp_path):
    root = _repo(tmp_path)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty",
                    "-m", "x"], check=True)
    assert "commit no commits yet" not in srv.brief(root)


def test_the_backlog_answers_exactly_what_is_asked(tmp_path):
    root = _repo(tmp_path)
    assert srv.backlog(root, {"id": "e1-01"}) == "crissp/backlog/E1-quality.md\n### E1-01 · The gate                                   [doing] [M]\nWhy        a reason"
    assert srv.backlog(root, {"id": "E0-01"}).startswith("crissp/backlog/done/E0-baseline.md\n### E0-01")
    assert srv.backlog(root, {"id": "F-02"}) == "crissp/backlog/FINDINGS.md\nF-02 | the frontend | only a smoke suite | otherproject"
    assert srv.backlog(root, {"id": "D-01"}).startswith("crissp/backlog/DECISIONS.md (taken)\nD-01 | A private repository.")
    assert srv.backlog(root, {"status": "todo"}) == "E1-03 · Security suite [todo] []"
    assert srv.backlog(root, {"status": "parked"}) == "no items parked"
    assert srv.backlog(root, {"open": "findings"}) == "F-01 → E5-01 · dumps in an image\nF-02 → otherproject · only a smoke suite"
    assert srv.backlog(root, {"open": "decisions"}) == "D-04 Admin kubeconfigs for scans? · recommendation: **b**"
    with pytest.raises(LookupError):
        srv.backlog(root, {"id": "F-99"})
    with pytest.raises(ValueError):
        srv.backlog(root, {})
    bare = tmp_path / "bare"
    bare.mkdir()
    assert srv.backlog(bare, {"open": "findings"}) == "no open findings"
    assert srv.backlog(bare, {"open": "decisions"}) == "no open decisions"


def test_it_speaks_mcp(tmp_path):
    root = _repo(tmp_path)
    init = srv.handle(root, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-03-26"}})
    assert init["result"]["protocolVersion"] == "2025-03-26" and init["result"]["serverInfo"]["name"] == "crissp"
    assert srv.handle(root, {"id": 2, "method": "initialize"})["result"]["protocolVersion"] == srv.PROTOCOL
    assert srv.handle(root, {"method": "notifications/initialized"}) is None
    assert [t["name"] for t in srv.handle(root, {"id": 3, "method": "tools/list"})["result"]["tools"]] == ["brief", "backlog", "finding", "decision", "epic", "feature", "item", "run", "status", "dashboard"]
    call = srv.handle(root, {"id": 4, "method": "tools/call", "params": {"name": "backlog", "arguments": {"id": "D-04"}}})
    assert "Admin kubeconfigs" in call["result"]["content"][0]["text"] and "isError" not in call["result"]
    assert srv.handle(root, {"id": 5, "method": "tools/call", "params": {"name": "brief"}})["result"]["content"][0]["text"]
    wrong = srv.handle(root, {"id": 6, "method": "tools/call", "params": {"name": "backlog", "arguments": {"id": "F-99"}}})
    assert wrong["result"] == {"content": [{"type": "text", "text": "F-99 is not in the backlog"}], "isError": True}
    assert srv.handle(root, {"id": 7, "method": "tools/call"})["result"]["isError"]  # no tool named: unknown tool
    assert srv.handle(root, {"id": 8, "method": "ping"})["result"] == {}
    assert srv.handle(root, {"id": 9, "method": "resources/list"})["error"]["code"] == -32601


def test_a_finding_is_written_under_the_next_number(tmp_path):
    root = _repo(tmp_path)
    answer = srv.finding(root, {"seen": "deploy.sh (2026-10-23)", "observation": "no\n  lock   file", "goes_to": "E1-01"})
    assert answer == "F-03 written to crissp/backlog/FINDINGS.md"
    lines = (root / "crissp/backlog/FINDINGS.md").read_text().splitlines()
    assert lines[-1] == "| F-03 | deploy.sh (2026-10-23) | no lock file | E1-01 |" and lines[-2].startswith("| F-02 ")
    assert srv.backlog(root, {"id": "F-03"}) == "crissp/backlog/FINDINGS.md\nF-03 | deploy.sh (2026-10-23) | no lock file | E1-01"
    assert srv.finding(root, {"seen": "a", "observation": "b", "goes_to": "c"}).startswith("F-04 ")
    with pytest.raises(ValueError, match="observation is missing"):
        srv.finding(root, {"seen": "a", "observation": "  ", "goes_to": "c"})
    with pytest.raises(ValueError, match="cannot hold a |"):
        srv.finding(root, {"seen": "a", "observation": "x | y", "goes_to": "c"})
    first = tmp_path / "first"
    (first / "crissp/backlog").mkdir(parents=True)
    (first / "crissp/backlog/FINDINGS.md").write_text("# Findings\n\n| # | Seen | Observation | Goes to |\n|---|---|---|---|\n<!-- note -->\n")
    assert srv.finding(first, {"seen": "a", "observation": "b", "goes_to": "c"}) == "F-01 written to crissp/backlog/FINDINGS.md"
    assert (first / "crissp/backlog/FINDINGS.md").read_text().endswith("|---|---|---|---|\n| F-01 | a | b | c |\n<!-- note -->\n")
    with pytest.raises(LookupError, match="FINDINGS.md is missing"):
        srv.finding(tmp_path / "nowhere", {"seen": "a", "observation": "b", "goes_to": "c"})
    (first / "crissp/backlog/FINDINGS.md").write_text("# Findings, no table yet\n")
    with pytest.raises(LookupError, match="no table"):
        srv.finding(first, {"seen": "a", "observation": "b", "goes_to": "c"})


DECISIONS_BOTH = """# Decisions

## Open — need the product owner

| # | Question | Options | Recommendation |
|---|---|---|---|
| D-04 | Admin kubeconfigs? | a) keep · b) read-only | **b** |

## Taken

| # | Decision | Date |
|---|---|---|
| ~~D-01~~ | A private repository. | 2026-10-23 |
"""


def test_a_decision_is_asked_and_then_taken(tmp_path):
    root = _repo(tmp_path)
    path = root / "crissp/backlog/DECISIONS.md"
    path.write_text(DECISIONS_BOTH)
    ask = {"question": "Version scheme?", "options": "a) semver · b) dates", "recommendation": "**a**"}
    assert srv.decision(root, ask) == "D-05 written to crissp/backlog/DECISIONS.md"
    assert "| D-04 | Admin kubeconfigs? | a) keep · b) read-only | **b** |\n| D-05 | Version scheme? | a) semver · b) dates | **a** |\n\n## Taken" \
        in path.read_text()
    assert srv.decision(root, {"id": "d-04", "decision": "A read-only ServiceAccount.", "date": "2026-10-24"}) \
        == "D-04 taken, in crissp/backlog/DECISIONS.md"
    text = path.read_text()
    assert "| D-04 |" not in text and text.endswith("| ~~D-01~~ | A private repository. | 2026-10-23 |\n"
                                                    "| ~~D-04~~ | A read-only ServiceAccount. | 2026-10-24 |\n")
    assert srv.backlog(root, {"open": "decisions"}).startswith("D-05 Version scheme?")
    assert srv.decision(root, {"id": "D-05", "decision": "Semver."}).startswith("D-05 taken")
    assert f"| ~~D-05~~ | Semver. | {srv.datetime.date.today().isoformat()} |" in path.read_text()
    with pytest.raises(ValueError, match="already taken"):
        srv.decision(root, {"id": "D-01", "decision": "again"})
    with pytest.raises(LookupError, match="D-99 is not in the backlog"):
        srv.decision(root, {"id": "D-99", "decision": "x"})
    with pytest.raises(ValueError, match="not YYYY-MM-DD"):
        srv.decision(root, {"id": "D-04", "decision": "x", "date": "tomorrow"})
    with pytest.raises(ValueError, match="decision is missing"):
        srv.decision(root, {"id": "D-04"})
    with pytest.raises(ValueError, match="question is missing"):
        srv.decision(root, {"options": "a", "recommendation": "b"})
    with pytest.raises(LookupError, match="DECISIONS.md is missing"):
        srv.decision(tmp_path / "nowhere", ask)


def test_a_decision_in_a_file_without_sections_still_lands_in_the_right_table(tmp_path):
    root = _repo(tmp_path)  # DECISIONS: one table, open and taken rows together, no headings
    assert srv.decision(root, {"question": "Q?", "options": "a · b", "recommendation": "a"}).startswith("D-05 ")
    assert srv.decision(root, {"id": "D-04", "decision": "b", "date": "2026-10-24"}).startswith("D-04 taken")
    text = (root / "crissp/backlog/DECISIONS.md").read_text()
    assert "| D-05 | Q? | a · b | a |" in text and text.endswith("## Taken\n\n| # | Decision | Date |\n|---|---|---|\n"
                                                                    "| ~~D-04~~ | b | 2026-10-24 |\n")
    with pytest.raises(LookupError, match="no section"):
        srv.add_row("no heading here\n", "| x |", "## Taken")


def test_an_epic_gets_its_own_file_under_the_next_number(tmp_path):
    root = _repo(tmp_path)
    b = root / "crissp/backlog"
    (b / "README.md").write_text("| File | What |\n|---|---|\n| [E1-quality.md](E1-quality.md) | Quality |\n\n## How an item looks\n")
    answer = srv.epic(root, {"title": "Repair: older C.R.I.S.S.P. projects!", "why": "The layout moved " * 10})
    assert answer == "E2 written to crissp/backlog/E2-repair-older-c-r-i-s-s-p-projects.md, listed in the README"
    text = (b / "E2-repair-older-c-r-i-s-s-p-projects.md").read_text()
    assert text.startswith("# E2 · Repair: older C.R.I.S.S.P. projects!\n\nWhy: The layout moved") and max(map(len, text.splitlines())) <= 120
    assert "| [E1-quality.md](E1-quality.md) | Quality |\n| [E2-repair-older-c-r-i-s-s-p-projects.md](E2-repair-older-c-r-i-s-s-p-projects.md)" \
        " | Repair: older C.R.I.S.S.P. projects! |\n\n## How" in (b / "README.md").read_text()
    assert srv.backlog(root, {"id": "e2"}).splitlines()[-2:] == ["Features:", "none yet"]
    (b / "README.md").write_text("no epics listed\n")
    assert srv.epic(root, {"title": "x" * 50, "why": "w"}) == "E3 written to crissp/backlog/E3-epic.md"  # numbers count done/ too
    assert srv.epic(root, {"title": "One two three four five six seven eight nine", "why": "w"}).endswith(
        "E4-one-two-three-four-five-six-seven-eight.md")
    with pytest.raises(ValueError, match="why is missing"):
        srv.epic(root, {"title": "t"})
    with pytest.raises(LookupError, match="backlog is missing"):
        srv.epic(tmp_path / "nowhere", {"title": "t", "why": "w"})


def test_features_and_their_pbis_are_three_levels(tmp_path):
    root = _repo(tmp_path)
    srv.epic(root, {"title": "Repair", "why": "the layout moved"})
    path = root / "crissp/backlog/E2-repair.md"
    assert srv.feature(root, {"epic": "e2", "title": "Detect and plan", "why": "see what would move"}) \
        == "E2-F1 written to crissp/backlog/E2-repair.md"
    assert srv.feature(root, {"epic": "E2", "title": "Move", "why": "the move itself"}).startswith("E2-F2 ")
    pbi = {"feature": "e2-f1", "title": "Which layout a project has", "size": "s", "why": "Nobody sees it " * 12,
           "what": "a check", "done_when": "it says old", "tests": "backend: fixtures"}
    assert srv.item(root, pbi) == "E2-F1-01 written to crissp/backlog/E2-repair.md"
    assert srv.item(root, {**pbi, "title": "The plan", "depends": "E2-F1-01"}).startswith("E2-F1-02 ")
    assert srv.item(root, {**pbi, "feature": "E2-F2", "title": "The move"}).startswith("E2-F2-01 ")
    text = path.read_text()
    order = [m.group(0).split(" · ")[0] for m in re.finditer(r"^#{1,3} E[\w-]+ · ", text, re.M)]
    assert order == ["# E2", "## E2-F1", "### E2-F1-01", "### E2-F1-02", "## E2-F2", "### E2-F2-01"]  # each PBI under its feature
    assert f"{'## E2-F1 · Detect and plan':<88} [todo]\nWhy        see what would move\n\n### E2-F1-01" in text
    block = srv.backlog(root, {"id": "E2-F1-01"}).splitlines()
    assert block[1] == f"{'### E2-F1-01 · Which layout a project has':<88} [todo] [S]" and block[1].index("[") == 89
    assert block[2].startswith("Why        Nobody sees it") and len(block[2]) <= 120 and block[3].startswith(" " * 11)
    assert block[-4:] == ["What       a check", "Done when  it says old", "Tests      backend: fixtures", "Depends    —"]
    assert srv.backlog(root, {"id": "E2-F1-02"}).endswith("Depends    E2-F1-01")  # a PBI ends where the next feature starts
    assert srv.backlog(root, {"id": "E2-F1"}).splitlines() == [
        "crissp/backlog/E2-repair.md", f"{'## E2-F1 · Detect and plan':<88} [todo]", "Why        see what would move", "PBIs:",
        "E2-F1-01 · Which layout a project has [todo] [S]", "E2-F1-02 · The plan [todo] [S]"]
    assert srv.backlog(root, {"id": "E2"}).splitlines() == [
        "crissp/backlog/E2-repair.md", "# E2 · Repair\n\nWhy: the layout moved".split("\n")[0], "", "Why: the layout moved",
        "Features:", "E2-F1 · Detect and plan [todo]", "E2-F2 · Move [todo]"]
    srv.feature(root, {"epic": "E2", "title": "Later", "why": "w"})
    assert srv.backlog(root, {"id": "E2-F3"}).endswith("PBIs:\nnone yet")
    assert srv.backlog(root, {"id": "E1"}).endswith("Features:\nnone yet")  # an epic from before features

    assert srv.item(root, {"id": "e2-f1", "status": "doing"}) == "E2-F1 [todo] → [doing], in crissp/backlog/E2-repair.md"
    assert srv.item(root, {"id": "E2-F1-01", "status": "review"}).startswith("E2-F1-01 [todo] → [review]")
    assert srv.backlog(root, {"status": "doing"}) == "E2-F1 · Detect and plan [doing] (feature)\nE1-01 · The gate [doing] [M]"
    assert "E2-F1-01 Which layout a project has" in srv.brief(root)  # in review, in the brief
    assert srv.item(root, {"id": "E1-03", "status": "parked"}).startswith("E1-03 [todo] → [parked]")  # items from before features
    with pytest.raises(ValueError, match="a PBI belongs to a feature"):
        srv.item(root, {"epic": "E2", "title": "no feature"})
    with pytest.raises(LookupError, match="E2-F9 is not a feature"):
        srv.item(root, {**pbi, "feature": "E2-F9"})
    with pytest.raises(LookupError, match="E0 is not an open epic"):
        srv.item(root, {**pbi, "feature": "E0-F1"})
    with pytest.raises(ValueError, match="an XL item is split"):
        srv.item(root, {**pbi, "size": "XL"})
    with pytest.raises(ValueError, match="done_when is missing"):
        srv.item(root, {**pbi, "done_when": ""})
    with pytest.raises(ValueError, match="give the epic"):
        srv.feature(root, {"title": "t", "why": "w"})
    with pytest.raises(LookupError, match="E9 is not an open epic"):
        srv.feature(root, {"epic": "E9", "title": "t", "why": "w"})
    with pytest.raises(ValueError, match="only the product owner accepts"):
        srv.item(root, {"id": "E2-F1", "status": "done"})
    with pytest.raises(ValueError, match="status must be one of todo, doing, review, parked"):
        srv.item(root, {"id": "E2-F1-01"})
    with pytest.raises(LookupError, match="E2-F1-99 is not in the backlog"):
        srv.item(root, {"id": "E2-F1-99", "status": "doing"})
    with pytest.raises(ValueError, match="E0-01 is done"):
        srv.item(root, {"id": "E0-01", "status": "todo"})
    assert srv.until("no newline", 0, srv.HEADING) == "no newline"


def test_the_writers_answer_over_mcp(tmp_path):
    root = _repo(tmp_path)
    call = lambda name, args: srv.handle(root, {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]  # noqa: E731
    assert call("finding", {"seen": "a", "observation": "b", "goes_to": "c"})["content"][0]["text"] == "F-03 written to crissp/backlog/FINDINGS.md"
    assert call("decision", {"question": "q", "options": "o", "recommendation": "r"})["content"][0]["text"].startswith("D-05 ")
    assert call("epic", {"title": "Repair", "why": "w"})["content"][0]["text"] == "E2 written to crissp/backlog/E2-repair.md"
    assert call("feature", {"epic": "E2", "title": "Plan", "why": "w"})["content"][0]["text"].startswith("E2-F1 ")
    assert call("item", {"id": "E1-03", "status": "parked"})["content"][0]["text"].startswith("E1-03 [todo] → [parked]")
    assert call("item", {"id": "E1-03", "status": "done"})["isError"]
    writers = {t["name"]: t for t in srv.TOOLS if t["name"] in ("finding", "decision", "epic", "feature", "item")}
    assert "Never to done" in writers["item"]["description"] and len(writers) == 5
    assert all("agents never edit the backlog" in t["description"] for t in writers.values())
    assert not list((root / "crissp/backlog").glob("*.tmp"))  # every write lands whole


def test_it_serves_line_by_line_over_stdio(tmp_path):
    root = _repo(tmp_path)
    out = io.StringIO()
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "ping"}), "", "not json",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})]
    assert srv.serve(root, io.StringIO("\n".join(lines) + "\n"), out) == 0
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert answers == [{"jsonrpc": "2.0", "id": 1, "result": {}},
                       {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "not JSON"}}]


def test_it_runs_as_a_script(monkeypatch):
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(SERVER), run_name="__main__")
    assert stop.value.code == 0


def test_claude_code_starts_it_from_the_repository_root():
    root = SERVER.parents[2]
    config = json.loads((root / ".mcp.json").read_text())["mcpServers"]["crissp"]
    assert config == {"command": "python3", "args": ["-I", "crissp/tool/server.py"]} and (root / config["args"][1]).is_file()
    assert "@crissp/CLAUDE.md" in (root / "CLAUDE.md").read_text()  # the agreement is always loaded, not only on request


def _scripts(root: Path, **bodies: str) -> None:
    """Stand-ins for crissp/<name>.sh: nothing real runs (no tests, no docker, no browser)."""
    for name, body in bodies.items():
        path = root / "crissp" / f"{name}.sh"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)


def _until(predicate, seconds: float = 10.0):
    end = srv.time.monotonic() + seconds
    while srv.time.monotonic() < end:
        if (got := predicate()):
            return got
        srv.time.sleep(0.05)
    raise AssertionError("waited in vain")


def test_plans_answer_at_once_and_a_deploy_is_never_run(tmp_path, monkeypatch):
    _scripts(tmp_path, check='echo "would run: tools ($1)"', deploy='echo "would rebuild: backend ($1)"; exit 3')
    assert srv.run(tmp_path, {"what": "check-plan"}) == "crissp/check.sh --plan (exit 0)\nwould run: tools (--plan)"
    assert srv.run(tmp_path, {"what": "deploy-plan"}) == "crissp/deploy.sh --plan (exit 3)\nwould rebuild: backend (--plan)"
    with pytest.raises(ValueError, match="a deploy stays in the product owner's terminal"):
        srv.run(tmp_path, {"what": "deploy"})
    assert "deploy" not in srv.RUNS and all(not a or a in (["--plan"], ["--status"]) for _, a, _ in srv.RUNS.values())
    assert not any("round" in name or "propose" in name for name in srv.RUNS)  # a UX round costs tokens: the owner asks
    monkeypatch.setattr(srv, "ENGINE", tmp_path / "no-engine")  # neither the project nor the engine has it
    with pytest.raises(LookupError, match="crissp/check-all.sh is missing"):
        srv.run(tmp_path, {"what": "check-all"})
    _scripts(tmp_path, check="sleep 5")
    monkeypatch.setattr(srv, "PLAN_TIMEOUT", 0.2)
    with pytest.raises(ValueError, match="took longer than 0.2s"):
        srv.run(tmp_path, {"what": "check-plan"})


def test_a_check_runs_in_the_background_and_status_follows_it(tmp_path):
    _scripts(tmp_path, check='echo "Backend … passed"; echo "Green: crissp/deploy.sh may go."',
             **{"check-all": 'echo "Coverage gate: RED"; exit 1'})
    assert srv.status(tmp_path) == "Lock: free\nNothing started with run yet."
    started = srv.run(tmp_path, {"what": "check"})
    assert started.startswith("check started (pid ") and "log: crissp/testsuite/results/mcp/check.log" in started
    text = _until(lambda: (lambda t: t if "finished" in t else None)(srv.status(tmp_path)))
    assert "check · started " in text and "finished, exit 0 (green)" in text and "  Green: crissp/deploy.sh may go." in text
    assert "[crissp] exit" not in text  # the exit marker is read, not shown
    srv.run(tmp_path, {"what": "check-all"})
    text = _until(lambda: (lambda t: t if "check-all · " in t and "exit 1" in t else None)(srv.status(tmp_path)))
    assert "finished, exit 1 · " in text and "(green)" not in text.split("check-all · ")[1] and "  Coverage gate: RED" in text


def test_one_run_at_a_time_and_a_run_that_died_is_said(tmp_path):
    lock = tmp_path / "crissp/testsuite/results/.run.lock"
    lock.mkdir(parents=True)
    (lock / "pid").write_text(str(srv.os.getpid()))  # this very test holds it: alive
    (lock / "what").write_text("check-all.sh")
    (lock / "since").write_text("14:02")
    _scripts(tmp_path, check="exit 0")
    with pytest.raises(ValueError, match=r"a run is in progress: check-all.sh \(pid \d+, since 14:02\)"):
        srv.run(tmp_path, {"what": "check"})
    assert srv.status(tmp_path).startswith("Lock: check-all.sh (pid ")
    (lock / "pid").write_text("999999999")  # a lock left behind by a run that was killed
    assert srv.held(tmp_path) == "" and srv.alive(999999999) is False
    (lock / "pid").write_text(str(srv.os.getpid()))
    (lock / "what").write_text("")
    (lock / "since").write_text("")
    assert srv.held(tmp_path) == f"a run (pid {srv.os.getpid()}, since ?)"
    (lock / "pid").unlink()
    mcp = tmp_path / "crissp/testsuite/results/mcp"
    mcp.mkdir(parents=True)
    (mcp / "runs.json").write_text(json.dumps({"check": {"pid": 999999999, "started": "13:00", "log": "crissp/testsuite/results/mcp/check.log"}}))
    (mcp / "check.log").write_text("Backend …\n")
    assert "check · started 13:00 · stopped without an exit code" in srv.status(tmp_path)
    (mcp / "runs.json").write_text(json.dumps({"check": {"pid": srv.os.getpid(), "started": "13:00", "log": "crissp/testsuite/results/mcp/check.log"}}))
    assert "check · started 13:00 · running" in srv.status(tmp_path)


def _serve(directory: Path):
    """A real local web server on a free port, serving directory (the dashboard's own folder in the real thing)."""
    import functools
    import http.server
    import threading
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    handler.log_message = lambda *a: None
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def _free_port() -> int:
    import socket
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_served_means_the_dashboard_itself_answers(tmp_path):
    (tmp_path / "dashboard").mkdir()
    (tmp_path / "dashboard" / "index.html").write_text('<a id="sessions"></a>')
    (tmp_path / "other.html").write_text("<p>another program</p>")
    httpd = _serve(tmp_path)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        assert srv.served(base + "/dashboard/") is True
        assert srv.served(base + "/other.html") is False  # something answers, but not the dashboard
        assert srv.served(base + "/gone/") is False  # a 404: a server from a folder that moved
    finally:
        httpd.shutdown()
    assert srv.served(f"http://127.0.0.1:{_free_port()}/dashboard/") is False  # nothing listens


def test_the_dashboard_is_served_and_its_address_answered(tmp_path, monkeypatch):
    (tmp_path / "web" / "dashboard").mkdir(parents=True)
    (tmp_path / "web" / "dashboard" / "index.html").write_text('<a id="sessions"></a>')
    httpd = _serve(tmp_path / "web")
    url = f"http://127.0.0.1:{httpd.server_address[1]}/dashboard/"
    try:
        _scripts(tmp_path, test=f'echo "dashboard data: 3 tests"; echo "Dashboard: {url}   (Ctrl-C to stop)"; sleep 30')
        assert srv.dashboard(tmp_path) == f"Dashboard: {url} (data rebuilt from the last runs)"
        pid = json.loads((tmp_path / "crissp/testsuite/results/mcp/runs.json").read_text())["dashboard"]["pid"]
        assert srv.alive(pid)  # it keeps serving after the answer
        srv.os.killpg(pid, 15)
    finally:
        httpd.shutdown()


def test_the_ux_view_is_the_same_server_opened_on_the_ux_suite(tmp_path):
    (tmp_path / "web" / "dashboard").mkdir(parents=True)
    (tmp_path / "web" / "dashboard" / "index.html").write_text('<a id="sessions"></a>')
    httpd = _serve(tmp_path / "web")
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    try:
        _scripts(tmp_path, test=f'[ "$1" = --ux ] || exit 9; echo "Dashboard: {base}/ux/"; sleep 30')
        assert srv.dashboard(tmp_path, {"view": "ux"}) == f"Dashboard: {base}/ux/ (data rebuilt from the last runs)"
        srv.os.killpg(json.loads((tmp_path / "crissp/testsuite/results/mcp/runs.json").read_text())["dashboard"]["pid"], 15)
    finally:
        httpd.shutdown()
    with pytest.raises(ValueError, match="view must be one of tests, ux"):
        srv.dashboard(tmp_path, {"view": "deploy"})


def test_ux_status_answers_at_once_what_the_ux_team_does(tmp_path):
    _scripts(tmp_path, ux='[ "$1" = --status ] && echo "The team is free (up to 3 at once). 0 round(s), 0 design(s)."')
    assert srv.run(tmp_path, {"what": "ux-status"}) == \
        "crissp/ux.sh --status (exit 0)\nThe team is free (up to 3 at once). 0 round(s), 0 design(s)."


def test_it_works_for_the_project_it_is_started_in():
    """CRISSP_ROOT, or the current directory (Claude Code starts it in the project's root): never its own place."""
    assert srv.ROOT == Path(srv.os.environ.get("CRISSP_ROOT") or srv.os.getcwd()).resolve()


def test_a_dashboard_that_says_its_address_but_does_not_serve_is_reported(tmp_path, monkeypatch):
    # what happened on 2026-10-23: test.sh says "Dashboard: …" before it starts the server, the port was held by an old
    # server from a moved folder (404s), the new server failed: the tool must not answer the address as if it worked
    url = f"http://127.0.0.1:{_free_port()}/dashboard/"
    _scripts(tmp_path, test=f'echo "Dashboard: {url}   (Ctrl-C to stop)"; echo "OSError: Address already in use" >&2; exit 1')
    with pytest.raises(ValueError, match="the dashboard did not start:\nDashboard: .*\nOSError: Address already in use"):
        srv.dashboard(tmp_path)
    _scripts(tmp_path, test='echo "usage: crissp/test.sh --dashboard" >&2; exit 2')
    with pytest.raises(ValueError, match="the dashboard did not start:\nusage: crissp/test.sh --dashboard"):
        srv.dashboard(tmp_path)
    _scripts(tmp_path, test="sleep 5")
    monkeypatch.setattr(srv, "DASHBOARD_WAIT", 0.3)
    with pytest.raises(ValueError, match="said nothing in 0.3s"):
        srv.dashboard(tmp_path)
    monkeypatch.setattr(srv, "ENGINE", tmp_path / "no-engine")
    with pytest.raises(LookupError, match="crissp/test.sh is missing"):
        srv.dashboard(tmp_path / "nowhere")


def test_test_sh_names_a_port_held_by_something_else(tmp_path):
    import shutil
    import socket
    import subprocess
    root = tmp_path / "repo"
    (root / "crissp/testsuite/lib").mkdir(parents=True)
    shutil.copy(SERVER.parents[1] / "test.sh", root / "crissp" / "test.sh")
    for name in ("measure.py", "collect.py"):  # stand-ins: no sessions, no results to read
        (root / "crissp/testsuite/lib" / name).write_text("")
    with socket.socket() as held:
        held.bind(("127.0.0.1", 0))
        held.listen()
        port = held.getsockname()[1]
        done = subprocess.run([str(root / "crissp" / "test.sh"), "--dashboard"], capture_output=True, text=True, timeout=30,
                              env={**srv.os.environ, "CRISSP_DASHBOARD_PORT": str(port)})
    assert done.returncode == 1 and f"Port {port} is in use" in done.stderr and "does not serve this dashboard" in done.stderr
    assert "Dashboard:" not in done.stdout  # it no longer claims an address it cannot serve


def test_run_status_and_dashboard_answer_over_mcp(tmp_path, monkeypatch):
    monkeypatch.setattr(srv, "ENGINE", tmp_path / "no-engine")  # never the real dashboard from a test
    _scripts(tmp_path, check='echo "plan"')
    call = lambda name, args=None: srv.handle(tmp_path, {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": args or {}}})["result"]  # noqa: E731
    assert call("run", {"what": "check-plan"})["content"][0]["text"].endswith("plan")
    assert call("status")["content"][0]["text"].startswith("Lock: free")
    assert call("dashboard")["isError"]  # no crissp/test.sh here
    assert [t["name"] for t in srv.TOOLS][-3:] == ["run", "status", "dashboard"]


def test_an_installed_project_runs_the_engines_own_scripts(tmp_path, monkeypatch):
    """A project made with `crissp init` has no crissp/check.sh of its own: the tool runs the engine's, for the project."""
    engine = tmp_path / "engine"
    engine.mkdir()
    (engine / "check.sh").write_text('#!/usr/bin/env bash\necho "engine plan for $CRISSP_ROOT"\n')
    (engine / "check.sh").chmod(0o755)
    project = tmp_path / "project"
    (project / "crissp").mkdir(parents=True)
    monkeypatch.setattr(srv, "ENGINE", engine)
    assert srv.script(project, "check.sh") == engine / "check.sh"
    (project / "crissp" / "check.sh").write_text("echo own\n")
    assert srv.script(project, "check.sh") == project / "crissp" / "check.sh"  # a project's own script wins
