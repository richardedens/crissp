"""The session view shows what Claude did — asked, agents, work, findings, decisions — from a transcript, never its output
and never a secret, and never the real ~/.claude (every test builds its own transcripts)."""

import importlib.util
import json
from collections import Counter
from pathlib import Path

LIB = Path(__file__).resolve().parents[1] / "lib"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"{name}_under_test", LIB / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sv = _load("sessionview")


def _use(name, given, id_="t"):
    return {"type": "tool_use", "id": id_, "name": name, "input": given}


def _assistant(*uses, ts="2026-10-23T09:00:00Z", cwd=None, **extra):
    return {"type": "assistant", "timestamp": ts, "cwd": cwd, "message": {"content": list(uses)}, **extra}


def _user(content, ts="2026-10-23T08:59:00Z", **extra):
    return {"type": "user", "timestamp": ts, "message": {"content": content}, **extra}


def _write(path: Path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in records) + "\nnot json\n")


def _repo(tmp_path) -> Path:
    repo = tmp_path / "shop"
    for f in ("CLAUDE.md", "crissp/CRISSP.md", "crissp/backlog/FINDINGS.md", "crissp/backlog/DECISIONS.md", "app/x.py"):
        (repo / f).parent.mkdir(parents=True, exist_ok=True)
        (repo / f).write_text("x")
    return repo


def _session(tmp_path, repo: Path) -> Path:
    """A session with a prompt, reads, edits, a finding, a decision, a subagent and its report."""
    projects = tmp_path / "projects"
    path = sv.project_dir(repo, projects) / "s1.jsonl"
    old = str(tmp_path / "planner")  # the folder's name when the session ran
    _write(path, [
        _assistant(_use("Read", {"file_path": f"{repo}/CRISSP.md"}), cwd=old, ts="2026-10-23T08:58:00Z"),
        _user("<system-reminder>noise</system-reminder>look at the findings"),
        _user([{"type": "tool_result", "content": "out"}]),
        _user("meta", isMeta=True),
        _assistant(_use("Bash", {"command": "cat backlog/FINDINGS.md CLAUDE.md", "description": "Read findings"}),
                   _use("Bash", {"command": "curl -H 'Authorization: Bearer abc123' x", "description": ""}),
                   _use("Edit", {"file_path": f"{old}/backlog/FINDINGS.md", "old_string": "| F-01 | a | b | c |",
                                 "new_string": "| F-01 | a | b | c |\n| F-02 | seen | no tests | E1 |"}),
                   _use("Write", {"file_path": f"{repo}/backlog/DECISIONS.md",
                                  "content": "| D-01 | q | a/b | a |\n| ~~D-02~~ | taken | 2026 |"}),
                   _use("Bash", {"command": "cat >> backlog/FINDINGS.md <<EOF\n| F-02 | again | dup | x |\nEOF"}),
                   _use("Agent", {"description": "Build the backend", "subagent_type": "fork"}, id_="ag1"),
                   _use("Agent", {"description": "Lost agent"}, id_="ag2"),
                   _use("AskUserQuestion", {"questions": [{"question": "Which?"}]}),
                   _use("ToolSearch", {}), cwd=str(repo)),
        _user("<task-notification><summary>Agent \"Build the backend\" completed</summary></task-notification>"),
        _user("<task-notification>no summary</task-notification>"),
        _assistant(_use("Read", {"file_path": "/elsewhere/file"}), isSidechain=True),
        _user("x" * 400, ts="2026-10-23T10:00:00Z"),
    ])
    sub = path.with_suffix("") / "subagents"
    _write(sub / "a1.jsonl", [_assistant(_use("Agent", {}, id_="ag1")),
                              _assistant(_use("Edit", {"file_path": f"{repo}/app/x.py"}), cwd=str(repo))])
    (sub / "a1.meta.json").write_text(json.dumps({"description": "Build the backend", "agentType": "fork",
                                                  "toolUseId": "ag1", "finished": True}))
    (sub / "a2.meta.json").write_text("{broken")
    return path


def test_the_transcripts_are_found_where_claude_code_keeps_them(tmp_path):
    assert sv.project_dir(Path("/Users/me/A.b/shop"), tmp_path) == tmp_path / "-Users-me-A-b-shop"


def test_secrets_in_a_command_are_masked():
    assert sv.mask("curl -H 'Authorization: Bearer abc123' --token=xyz") == \
        "curl -H 'Authorization: Bearer •••' --token=•••"


def test_only_what_the_person_typed_is_a_prompt():
    assert sv.prompt(_user("<ide_opened_file>f</ide_opened_file> hi")) == "hi"
    assert sv.prompt(_user([{"type": "text", "text": "a"}, {"type": "text", "text": "b"}, "odd"])) == "a\nb"
    assert sv.prompt(_user("<system-reminder>only</system-reminder>")) is None
    assert sv.prompt(_user([{"type": "tool_result"}])) is None
    assert sv.prompt(_user(None)) is None
    assert sv.prompt(_user("s", isCompactSummary=True)) is None
    assert sv.prompt({"type": "assistant", "message": {"content": "x"}}) is None


def test_a_renamed_folder_still_counts_as_the_repository(tmp_path):
    repo = _repo(tmp_path)
    r = sv.Repo(repo, str(tmp_path / "planner"))
    assert r.rel(f"{tmp_path}/planner/app/x.py") == "app/x.py" and r.rel(f"{repo}/app/x.py") == "app/x.py"
    assert r.rel("/elsewhere") is None
    assert sv.Repo(repo, str(repo)).roots == [repo] and sv.Repo(repo).roots == [repo]
    assert r.mentioned(f"cat app/x.py {repo}/CLAUDE.md missing.md plain /etc/hosts", None) == {"app/x.py", "CLAUDE.md"}
    assert r.mentioned("cat x.py", str(repo / "app")) == {"app/x.py"}


def test_finding_and_decision_rows_are_read_from_what_is_written():
    assert sv.rows("| F-03 | seen | what | to |\n| D-01 | q | o | r |", "F") == \
        [{"id": "F-03", "text": "what", "taken": False}]
    assert sv.rows("| ~~D-02~~ | decided | date |", "D") == [{"id": "D-02", "text": "decided", "taken": True}]
    assert sv.written_rows("Edit", {"file_path": "x/FINDINGS.md", "old_string": "| F-1 | a | b | c |",
                                    "new_string": "| F-1 | a | b | c |\n| F-2 | a | b | c |"}) == \
        {"F": [{"id": "F-2", "text": "b", "taken": False}]}
    assert sv.written_rows("Edit", {"file_path": "x/FINDINGS.md", "old_string": "| F-1 | a | b | c |",
                                    "new_string": "| F-1 | a | changed | c |"}) == {}
    assert sv.written_rows("Bash", {"command": "echo '| D-9 | q | o | r |' >> DECISIONS.md"})["D"][0]["id"] == "D-9"
    assert sv.written_rows("Bash", {"command": "ls"}) == {}
    assert sv.written_rows("Write", {"file_path": "README.md", "content": "| F-1 | a | b | c |"}) == {}


def test_each_tool_call_becomes_one_step(tmp_path):
    repo = sv.Repo(_repo(tmp_path))
    assert sv.action(_use("Read", {"file_path": "/elsewhere/f"}), repo, None)["text"] == "/elsewhere/f"
    assert sv.action(_use("Bash", {"command": "ls -la 2>/dev/null"}), repo, None)["kind"] == "read"
    wrote = sv.action(_use("Bash", {"command": f"cat x > {repo.root}/app/y.md && echo a >> /tmp/z"}), repo, None)
    assert wrote["kind"] == "change" and wrote["files"] == {"app/y.md"}
    assert sv.action(_use("Bash", {"command": "echo a > out.txt"}), repo, str(repo.root))["files"] == {"out.txt"}
    code = "cat > app/z.ts <<'EOF'\nconst f = (x) => dict;\nlet r: A<B> > r.name;\necho > app/q.md\nEOF"
    assert sv.action(_use("Bash", {"command": code}), repo, str(repo.root))["files"] == {"app/z.ts"}
    assert sv.action(_use("Bash", {"command": "x=1 => dict; f -> g.py; a 2>err.log"}), repo, None)["kind"] == "run"
    run = sv.action(_use("Bash", {"command": ""}), repo, None)
    assert run["kind"] == "run" and run["text"] == ""
    assert sv.action(_use("Bash", {"command": "make\nmore"}), repo, None)["text"] == "make"
    assert sv.action(_use("AskUserQuestion", {"questions": [{"question": "a"}, {}]}), repo, None)["text"] == "a · "
    assert sv.action({"name": "Monitor"}, repo, None)["kind"] == "other"
    assert sv.tool_uses({"type": "assistant", "message": {"content": "text"}}) == []
    assert sv.tool_uses({"type": "user", "message": {"content": [_use("Read", {})]}}) == []


def test_a_session_becomes_columns_with_agents_findings_and_decisions(tmp_path):
    repo = _repo(tmp_path)
    s = sv.summary(_session(tmp_path, repo), repo)
    first, second, third = s["turns"]
    assert first["prompt"] == "(before the first prompt)" and first["acts"][0]["text"] == "crissp/CRISSP.md"  # read at its old place
    assert second["prompt"] == "look at the findings" and third["prompt"] == "x" * 400
    assert [a["kind"] for a in second["acts"]] == ["read", "run", "change", "change", "change", "ask", "other"]
    assert second["acts"][1]["text"] == "curl -H 'Authorization: Bearer •••' x"
    assert [x["id"] for x in second["F"]] == ["F-02"]  # F-01 was there already; the second F-02 is the same row
    assert [(x["id"], x["taken"]) for x in second["D"]] == [("D-01", False), ("D-02", True)]
    built, lost = second["agents"]
    assert built["name"] == "Build the backend" and built["done"] and built["changed"] == ["app/x.py"]
    assert built["kinds"] == Counter({"change": 1})  # the call that started it is not its own work
    assert lost == {"name": "Lost agent", "type": "agent", "kinds": Counter(), "changed": [], "acts": [], "done": False,
                    "tokens": Counter()}
    assert second["reports"] == ['Agent "Build the backend" completed', "an agent reported"]
    assert s["read"] == Counter({"crissp/CRISSP.md": 1, "crissp/backlog/FINDINGS.md": 1, "CLAUDE.md": 1})
    assert s["changed"] == Counter({"crissp/backlog/FINDINGS.md": 2, "crissp/backlog/DECISIONS.md": 1})
    assert (s["agents"], s["F"], s["D"]) == (2, 1, 2) and s["first"] == "2026-10-23T08:58:00Z"


def test_a_session_without_subagents_or_cwd(tmp_path):
    path = tmp_path / "s.jsonl"
    _write(path, [_user("hi", ts=None), {"type": "summary"}])
    assert sv.subagents(path, sv.Repo(tmp_path)) == {} and sv.session_root(path) is None
    s = sv.summary(path, tmp_path)
    assert s["first"] is None and len(s["turns"]) == 1
    sub = tmp_path / "s" / "subagents"
    sub.mkdir(parents=True)
    (sub / "a.meta.json").write_text("{}")
    assert sv.subagents(path, sv.Repo(tmp_path)) == {"a.meta.json": {
        "name": "a", "type": "agent", "kinds": Counter(), "changed": [], "acts": [], "done": False, "tokens": Counter()}}


def test_times_are_shown_locally_or_not_at_all():
    assert sv.when("2026-10-23T09:00:00Z")
    assert sv.when(None) == "" and sv.when("yesterday") == ""


def test_the_page_shows_the_timeline_and_what_was_never_read(tmp_path):
    repo = _repo(tmp_path)
    page = sv.render(sv.summary(_session(tmp_path, repo), repo), repo)
    assert "<code>CLAUDE.md</code><span>loaded at start, read 1×</span>" in page
    assert "<code>crissp/CRISSP.md</code><span>read 1×</span>" in page
    assert '<li class="never"><code>crissp/backlog/DECISIONS.md</code><span>never read, written 1×</span>' in page
    assert "agent · fork" in page and "<b>Build the backend</b>" in page and "not finished" in page
    assert "<span class=id>F-02</span>no tests" in page and 'class="row taken"><span class=id>D-02' in page
    assert "abc123" not in page and "Bearer •••" in page
    assert "<details class=full><summary>prompt</summary>" in page  # a long prompt folds
    assert "agent reported" in page and "class=pipe" in page
    assert page.count("class=top") == 1  # only the top bar: its sticky flex row must not catch the content


def test_the_small_pieces_of_the_page():
    assert sv.files(Counter()) == "<p class=muted>none</p>"
    assert "… and 1 more" in sv.files(Counter({"a": 2, "b": 1}), limit=1)
    assert sv.file_list([]) == "" and "… 1 more" in sv.file_list(["a", "b"], limit=1)
    assert "<details open>" in sv.branch("F", "findings", "1", "body", open_=True)
    assert sv.branch("rep", "k", "t") == '<li><div class="node rep"><span class=kind>k</span><b>t</b></div></li>'
    empty = {"ts": None, "prompt": "hi", "acts": [], "agents": [], "reports": [], "F": [], "D": []}
    assert "class=tree" not in sv.column(1, empty)
    only_findings = {**empty, "F": [{"id": "F-1", "text": "t", "taken": False}]}
    assert "Claude · main session" in sv.column(1, only_findings)


def test_the_index_lists_every_session_or_says_there_is_none(tmp_path):
    repo = _repo(tmp_path)
    s = sv.summary(_session(tmp_path, repo), repo)
    assert '<a href="s1.html">' in sv.render_index([s], repo)
    assert "No sessions found" in sv.render_index([], repo)
    bare = {**s, "turns": [], "first": None}
    assert '<a href="s1.html">s1</a>' in sv.render_index([bare], repo)


def test_build_writes_a_page_per_session_and_main_opens_the_index(tmp_path, monkeypatch, capsys):
    repo = _repo(tmp_path)
    _session(tmp_path, repo)
    monkeypatch.setattr(sv, "ROOT", repo)
    out, opened = tmp_path / "out", []
    assert sv.main(["--projects", str(tmp_path / "projects"), "--out", str(out), "--open"],
                   run=lambda cmd, check: opened.append(cmd)) == 0
    assert (out / "s1.html").is_file() and opened == [["open", str(out / "index.html")]]
    assert json.loads((out / "summary.json").read_text()) == {"sessions": 1, "tokens": "0"}  # for the dashboard
    assert capsys.readouterr().out.strip() == str(out / "index.html")
    assert sv.main(["--projects", str(tmp_path / "projects"), "--out", str(out)], run=None) == 0
    assert sv.main(["--bogus"]) == 2 and sv.main(["--out"]) == 2
    assert "usage:" in capsys.readouterr().err


def test_it_runs_as_a_script(monkeypatch):
    import runpy
    import sys

    import pytest
    monkeypatch.setattr(sys, "argv", ["sessionview.py", "--bogus"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(LIB / "sessionview.py"), run_name="__main__")
    assert stop.value.code == 2


def _costly(mid, out, ts="2026-10-23T09:00:00Z", *uses):
    return {"type": "assistant", "timestamp": ts, "message": {"id": mid, "content": list(uses), "usage": {
        "input_tokens": 1, "output_tokens": out, "cache_read_input_tokens": 100, "cache_creation_input_tokens": 10}}}


def test_tokens_are_counted_once_per_response_and_per_step(tmp_path):
    repo = _repo(tmp_path)
    path = sv.project_dir(repo, tmp_path / "p") / "s.jsonl"
    _write(path, [_costly("m0", 5), _user("first"), _costly("m1", 50), _costly("m1", 50),  # one response, two records
                  _costly("m2", 20, "2026-10-23T09:01:00Z", _use("Agent", {"description": "helper"}, id_="ag")),
                  _user("second"), {"type": "assistant", "message": {"content": []}}])
    sub = path.with_suffix("") / "subagents"
    _write(sub / "h.jsonl", [_costly("m2", 20, "x", _use("Agent", {}, id_="ag")), _costly("h1", 7), _costly("h1", 7)])
    (sub / "h.meta.json").write_text(json.dumps({"description": "helper", "toolUseId": "ag", "finished": True}))
    s = sv.summary(path, repo)
    before, first, second = s["turns"]
    assert sum(before["tokens"].values()) == 116 and first["tokens"]["output"] == 70
    assert first["agents"][0]["tokens"] == Counter({"input": 1, "output": 7, "cache_read": 100, "cache_write": 10})
    assert first["total"] == (111 + 50) + (111 + 20) + (111 + 7)  # m1 once, m2, and the helper's h1 once
    assert second["total"] == 0 and s["total"] == 116 + 410
    assert s["tokens"]["output"] == 5 + 70 + 7
    page = sv.render(s, repo)
    assert "526</b>tokens in total" in page and "class=tank" in page and "<span class=cost>118</span>" in page
    assert "tokens over 1 sessions" in sv.render_index([s], repo)


def test_amounts_read_at_a_glance():
    assert (sv.amount(950), sv.amount(1234), sv.amount(3_400_000)) == ("950", "1.2k", "3.4M")
    assert 'width:0%' in sv.tank(0, 0) and 'width:2%' in sv.tank(1, 10_000) and 'width:50%' in sv.tank(5, 10)
    assert sv.cost(Counter()) == "" and sv.usage({}) == Counter()


def test_the_look_is_the_shared_one_dark_by_default_with_its_own_font(monkeypatch, tmp_path):
    page = sv.page("t", "body")
    assert "prefers-color-scheme:light" not in page and "[data-theme=light]:root{" in page  # light only when chosen
    assert "localStorage.getItem('crissp.theme')" in page and "id=theme" in page  # the shared theme and switch
    assert "<header class=top>" in page and '<a href="../../dashboard/#changes">Changes</a>' in page
    assert "MutationObserver" in page and "uRip" in page  # the water, from crissp/look/water.js
    assert sv.WATER_JS == Path(sv.__file__).resolve().parents[2] / "look" / "water.js" and sv.FONT.is_file()
    assert 'font-family:"Figtree"' in page and "data:font/woff2;base64," in page and "fonts.googleapis" not in page
    monkeypatch.setattr(sv, "FONT", tmp_path / "missing.woff2")
    assert sv.font_face() == "" and "Figtree" in sv.page("t", "b")  # the font stack still names it, falling back


def test_the_top_bar_names_the_product_and_the_water_is_optional(monkeypatch, tmp_path):
    monkeypatch.setattr(sv, "ROOT", tmp_path / "shield")
    assert sv.product() == ("shield", "S")
    (tmp_path / "shield" / "crissp" / "testsuite").mkdir(parents=True)
    (tmp_path / "shield" / "crissp" / "testsuite" / "suites.json").write_text('{"product": "Shop", "monogram": "S"}')
    assert sv.product() == ("Shop", "S") and "<span class=logo>S</span>" in sv.top_bar("x")
    assert '<a href="../../dashboard/">Tests</a><a href="../../ux/">UX</a>' in sv.top_bar("x")  # the shared sections
    monkeypatch.setattr(sv, "WATER_JS", tmp_path / "none.js")
    assert sv.water() == "" and "<header class=top>" in sv.page("t", "b")


def test_the_pages_name_the_product_from_suites_json(monkeypatch, tmp_path):
    repo = _repo(tmp_path)
    s = sv.summary(_session(tmp_path, repo), repo)
    monkeypatch.setattr(sv, "ROOT", tmp_path / "shop")
    (tmp_path / "shop" / "crissp" / "testsuite").mkdir(parents=True)
    (tmp_path / "shop" / "crissp" / "testsuite" / "suites.json").write_text('{"product": "Shop", "monogram": "S"}')
    for page in (sv.render_index([], repo), sv.render_index([s], repo), sv.render(s, repo)):
        assert "<span class=eyebrow>Shop · what Claude did</span>" in page


def test_files_that_moved_into_crissp_are_named_by_their_new_place():
    assert sv.moved("backlog/E1-x.md") == "crissp/backlog/E1-x.md" and sv.moved("ARCHITECTURE.md") == "crissp/ARCHITECTURE.md"
    assert sv.moved("backlogs.md") == "backlogs.md" and sv.moved("app/CRISSP.md") == "app/CRISSP.md"
    assert sv.moved(".crissp/backlog/F.md") == "crissp/backlog/F.md"  # the hidden .crissp/ of earlier today
    assert sv.moved("crissp/CLAUDE.md") == "crissp/CLAUDE.md"
    assert sv.moved("testsuite/lib/gate.py") == "crissp/testsuite/lib/gate.py" and sv.moved("check.sh") == "crissp/check.sh"
    assert sv.moved("app/backend/deploy.sh") == "app/backend/deploy.sh"  # only the root's own scripts moved
