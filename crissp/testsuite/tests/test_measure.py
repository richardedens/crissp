"""How Claude worked is measured, never guessed: tokens and history come from the usage in the transcript, first time
right from the backlog's history in git, and every recommendation names the measurement behind it."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ms = _load("measure")


def _r(mid, hist, out=0, *uses, ts="2026-10-23T09:00:00Z", cwd=None):
    """One record of an API response: its id, the history it was sent with, and the tools it used."""
    return {"type": "assistant", "timestamp": ts, "cwd": cwd, "message": {"id": mid, "content": list(uses), "usage": {
        "input_tokens": 0, "cache_read_input_tokens": hist, "cache_creation_input_tokens": 0, "output_tokens": out}}}


def _u(text, ts="2026-10-23T08:00:00Z"):
    return {"type": "user", "timestamp": ts, "message": {"content": text}}


def _tool(name, given, id_="t"):
    return {"type": "tool_use", "id": id_, "name": name, "input": given}


def _write(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")


def _session(repo: Path, projects: Path) -> Path:
    path = ms.sv.project_dir(repo, projects) / "s1.jsonl"
    _write(path, [
        _r("m0", 5, 1),  # before any prompt: not a request
        _u("build the thing", "2026-10-23T08:00:00Z"),
        _r("m1", 400_000, 10, _tool("Bash", {"command": "ls"}), _tool("Agent", {"description": "helper"}, "ag")),
        _r("m1", 400_000, 10, _tool("Read", {"file_path": f"{repo}/a.py"})),  # same response, another record
        _r("m2", 450_000, 20, _tool("Write", {"file_path": f"{repo}/a.py"}), cwd=str(repo)),
        _r("m3", 30_000, 5),  # compacted
        _u("<task-notification><summary>done</summary></task-notification>"),
        _u("and a question", "2026-10-23T10:00:00Z"),
        _r("m4", 31_000, 3),
        _r("m4", 31_000, 3),  # the same response again, without tools: counted once
        {"type": "user", "isSidechain": True, "message": {"content": "agent talk"}},
        _u("unanswered", "2026-10-23T11:00:00Z"),
    ])
    sub = path.with_suffix("") / "subagents"
    _write(sub / "h.jsonl", [_r("h1", 100, 7)])
    (sub / "h.meta.json").write_text(json.dumps({"description": "helper", "toolUseId": "ag"}))
    return path


def test_each_request_is_measured_from_the_usage(tmp_path):
    repo = tmp_path / "repo"
    (repo).mkdir()
    build, question, unanswered = ms.requests_of(_session(repo, tmp_path / "p"), repo)
    assert [len(q["trips"]) for q in (build, question, unanswered)] == [3, 1, 0]
    assert build["tokens"] == (400_010 + 450_020 + 30_005) + 107  # its round trips plus the agent it started
    assert (build["start"], build["end"], build["agents"]) == (400_000, 30_000, 107)
    assert build["trips"][0]["tools"] == ["Agent", "Bash", "Read"]  # tools of a response split over two records
    assert build["grew_by"] == {"Agent + Bash + Read": 50_000} and build["compacted"]
    assert build["changed"] == ["a.py"] and question["grew_by"] == {} and not question["compacted"]
    assert (unanswered["tokens"], unanswered["start"], unanswered["end"]) == (0, 0, 0)


def test_numbers_read_as_people_say_them():
    assert (ms.words(940), ms.words(58_400), ms.words(12_600_000)) == ("940", "58 thousand", "12.6 million")
    assert ms.history({}) == 0


def _git(repo: Path, *args):
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True)


def _commit(repo: Path, msg: str, epic: str, date: str):
    (repo / "backlog").mkdir(exist_ok=True)
    (repo / "backlog" / "E1-x.md").write_text(epic)
    (repo / "backlog" / "notes.txt").write_text(msg)
    _git(repo, "add", "-A")
    subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", msg],
                   check=True, env={"GIT_COMMITTER_DATE": date, "GIT_AUTHOR_DATE": date, "PATH": "/usr/bin:/bin"})


def test_first_time_right_comes_from_the_backlog_in_git(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    assert ms.item_history(repo) == {} and ms.commits(repo) == []
    item = "### E1-0{n} · Thing [{s}] [S]\n"
    _commit(repo, "start", item.format(n=1, s="doing") + item.format(n=2, s="doing"), "2026-10-23T08:30:00+00:00")
    _commit(repo, "E1-01: built", item.format(n=1, s="review") + item.format(n=2, s="review"), "2026-10-23T09:30:00+00:00")
    _commit(repo, "E1-02: again", item.format(n=1, s="review") + item.format(n=2, s="doing"), "2026-10-23T10:30:00+00:00")
    _commit(repo, "accept", item.format(n=1, s="done") + item.format(n=2, s="review"), "2026-10-23T11:30:00+00:00")
    _commit(repo, "accept 2", item.format(n=1, s="done") + item.format(n=2, s="done"), "2026-10-23T12:30:00+00:00")
    history = ms.item_history(repo)
    assert history == {"E1-01": ["doing", "review", "done"], "E1-02": ["doing", "review", "doing", "review", "done"]}
    assert ms.first_time_right(history["E1-01"]) is True and ms.first_time_right(history["E1-02"]) is False
    assert ms.first_time_right(["doing", "done"]) is None and ms.first_time_right(["review"]) is None
    asked = [{"at": "2026-10-23T09:00:00Z", "tokens": 100}, {"at": "2026-10-23T10:00:00Z", "tokens": 5}, {"at": None, "tokens": 9}]
    assert ms.item_costs(repo, asked) == {"E1-01": 100, "E1-02": 5}
    assert ms.git(tmp_path / "nowhere", "log") == ""


def test_ways_of_working_are_read_with_their_start(tmp_path):
    assert ms.ways(tmp_path) == [{"name": "How we worked so far", "since": "", "what": ""}]
    (tmp_path / "crissp" / "testsuite").mkdir(parents=True)
    (tmp_path / "crissp" / "testsuite" / "ways-of-working.json").write_text(json.dumps([
        {"name": "New", "since": "2026-11-01", "what": "one session per feature"},
        {"name": "Old", "since": "2026-10-01", "what": "one long session"}]))
    listed = ms.ways(tmp_path)
    assert [w["name"] for w in listed] == ["Old", "New"]
    assert ms.way_of("2026-11-02T00:00:00Z", listed) == "New" and ms.way_of("2026-10-02", listed) == "Old"
    assert ms.way_of(None, listed) == "Old"  # before every start: counted with the first


def test_ways_are_compared_on_cost_and_first_time_right():
    listed = [{"name": "Old", "since": "2026-10-01", "what": ""}, {"name": "New", "since": "2026-11-01", "what": ""}]
    q = lambda at, tokens, start, trips: {"at": at, "tokens": tokens, "start": start, "trips": [{}] * trips}  # noqa: E731
    asked = [q("2026-10-05", 1000, 400_000, 3), q("2026-10-06", 3000, 500_000, 5), q("2026-11-05", 100, 20_000, 1),
             q("2026-11-06", 0, 0, 0)]
    old, new = ms.compare(asked, {"E1-01": ["review", "done"], "E1-02": ["doing"]}, {"E1-01": 50}, listed)
    assert (old["requests"], old["median"], old["start"], old["trips"], old["long"]) == (2, 2000, 450_000, 4, 2)
    assert (new["requests"], new["median"], new["long"], old["accepted"], old["right"], old["per_item"]) == (1, 100, 0, 1, 1, 50)
    empty = ms.compare([], {}, {}, listed[:1])[0]
    assert (empty["median"], empty["start"], empty["trips"], empty["per_item"]) == (0, 0, 0, 0)


def test_every_recommendation_names_its_measurement():
    trips = lambda n, tools=("Bash",): [{"tools": list(tools)}] * n  # noqa: E731
    asked = [{"start": 400_000, "tokens": 9_000_000, "trips": trips(30), "grew_by": {"Bash + Read": 1000}},
             {"start": 10, "tokens": 5, "trips": trips(1), "grew_by": {}}]
    recs = dict(ms.recommendations(asked, {}, [{"name": "only"}]))
    assert "1 of 2 requests carried a history longer than 300 thousand" in recs["Start a new session for each feature or question."]
    assert "(the most: 30)" in recs["Agree the plan first, then let Claude batch its steps."]
    assert any("Bash added the most" in f for f in recs.values())
    assert "No backlog item has gone from review to done" in recs[
        "Commit each item on its own and move it to review, so first time right can be measured."]
    shots = dict(ms.recommendations([{"start": 1, "tokens": 1, "trips": trips(1), "grew_by": {"mcp__claude-in-chrome__computer": 9}}],
                                    {"E1-01": ["review", "done"]}, [{"name": "a"}, {"name": "b"}]))
    assert list(shots) == ["Take browser screenshots small, and only when they decide something."]
    other = ms.recommendations([{"start": 1, "tokens": 1, "trips": trips(1), "grew_by": {"WebFetch": 9}}], {}, [{}, {}])
    assert other[0][0] == "Look at what WebFetch returns: it adds the most to the history."
    assert ms.recommendations([], {"E1-01": ["review", "done"]}, [{}]) == []
    assert "Nothing to recommend" in ms.recs_list([])


def test_the_report_and_the_details_read_in_plain_english(tmp_path, monkeypatch):
    """The pages are the dashboard's own (stylesheet, water, cards, rings), in plain words, with where they come from."""
    repo = tmp_path / "repo"
    (repo / "crissp" / "testsuite").mkdir(parents=True)
    (repo / "crissp" / "testsuite" / "suites.json").write_text('{"product": "Shop"}')
    monkeypatch.setattr(ms.sv, "ROOT", repo)  # the product's name comes from sessionview's root, not from build's repo
    (repo / "CLAUDE.md").write_text("x")
    (repo / "CRISSP.md").write_text("x")
    (repo / "AGENTS.md").write_text("x")
    _session(repo, tmp_path / "p")
    page = ms.build(repo, tmp_path / "p", tmp_path / "out").read_text()
    assert '<link rel=stylesheet href="../../look/look.css">' in page and 'src="../../look/water.js"' in page
    assert '<link rel=stylesheet href="../../dashboard/style.css">' in page and "<h1>Shop · Sessions</h1>" in page
    assert 'aria-current=page href="index.html">Sessions</a>' in page and '<a href="../../ux/">UX</a>' in page
    assert "You asked Claude <b>2</b> things in 1 session(s)" in page and 'class="card kpi row"' in page
    assert "Requests on a long history" in page and "--p:50" in page  # 1 of the 2 requests: half the ring
    assert "Start a new session for each feature or question." in page and "<b>Because:</b>" in page
    assert "not measured yet" in page and "it is the baseline" in page and '<a href="s1.html">' in page
    detail = (tmp_path / "out" / "s1.html").read_text()
    assert "Measured from Claude Code's record of this session: <code>" in detail and "MB · last written" in detail
    assert '<a href="#timeline">Timeline and numbers</a>' in detail and "section class=stab id=tab-advice" in detail
    assert '<span class="badge missing">long history</span>' in detail and '<span class="badge area">compacted</span>' in detail
    assert '<span class="badge passed">loaded at the start</span>' in detail and '<span class="badge missing">never read</span>' in detail
    assert "dashed line: where a long history starts" in detail and "class=pipe" in detail
    assert json.loads((tmp_path / "out" / "summary.json").read_text())["sessions"] == 1


def test_the_building_blocks_say_what_they_show():
    assert "--p:0" in ms.ring(-5, "x", "--green") and "--p:100" in ms.ring(250, "x", "--green") and ms.pct(1, 0) == 0
    assert "No requests yet." in ms.bars([]) and ms.history_chart([]) == ""
    assert "Nothing to recommend" in ms.recs_list([]) and "No requests found" in ms.headline([], 0)
    right = ms.glance([], {"E1-01": ["review", "done"], "E1-02": ["review", "doing", "review", "done"]}, 0)
    assert "Right the first time" in right and "1<small class=muted> / 2</small>" in right
    two = [{"name": "a", "since": "", "what": ""}, {"name": "b", "since": "1", "what": "new"}]
    assert "baseline" not in ms.proof([], {}, {}, two)
    assert "<td class=num>1 of 1</td>" in ms.proof([], {"E1-01": ["review", "done"]}, {}, two[:1])
    empty = ms.report([], {}, {}, two[:1], [], {})
    assert "No requests found" in empty and "Claude sessions" in empty


def test_main_builds_it_and_runs_as_a_script(tmp_path, monkeypatch, capsys):
    repo = tmp_path / "repo"
    repo.mkdir()
    _session(repo, tmp_path / "p")
    monkeypatch.setattr(ms, "ROOT", repo)
    assert ms.main(["--projects", str(tmp_path / "p"), "--out", str(tmp_path / "o")]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "o" / "index.html")
    assert ms.main(["--bogus"]) == 2 and ms.main(["--out"]) == 2
    import runpy
    monkeypatch.setattr(sys, "argv", ["measure.py", "--bogus"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(LIB / "measure.py"), run_name="__main__")
    assert stop.value.code == 2

