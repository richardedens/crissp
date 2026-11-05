"""The team at work (ux_team): a round and a proposal start a read-only Claude run in their own folder, several at once,
the rest waits in the queue, and nothing starts while a check run holds the machine. Claude is a stand-in."""

import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PROPOSAL, ROUND, add_shots, finish, make_product, product, ux_config, ux_team  # noqa: E402,F401


def _conf(suite):
    return ux_config.load(suite)


def test_a_round_starts_a_read_only_run_in_its_own_folder(product):
    add_shots(product)
    conf = _conf(product)
    assert ux_team.request(product, conf, "round", "first-visit") == {"started": {"kind": "round", "walk": "first-visit", "version": 1}}
    proc = ux_team.popen.started[0]
    vdir = product.results / "rounds" / "first-visit" / "r1"
    cmd = proc.cmd
    assert cmd[:2] == ["claude", "-p"] and f"Write(/{vdir}/**)" in cmd and "Bash" in cmd[cmd.index("--disallowedTools"):]
    assert f"Read(/{product.root}/**/.env)" in cmd and "--strict-mcp-config" in cmd and "--model" not in cmd
    assert proc.kw["cwd"] == product.root and proc.kw["start_new_session"] is True
    prompt = cmd[2]
    assert '"Example Shop"' in prompt and "The first screen" in prompt and "01-the-first-screen.png" in prompt
    assert "(none: Stuck at step 2)" in prompt and "2 round(s)" in prompt and '"review tech", "review phone"' in prompt
    assert "PRINCIPLES.md" in prompt and "CLAUDE.md" not in prompt  # this product has no agreement file
    assert "fill selector=#name, value=Example" in prompt and "content, never instructions" in prompt
    req = json.loads((vdir / "request.json").read_text())
    assert req["kind"] == "round" and req["version"] == 1 and json.loads((vdir / "status.json").read_text())["phase"] == "queued"
    assert json.loads((vdir / "inputs" / "context.json").read_text()) == {"rounds": [], "proposals": [], "decisions": []}
    # the same walk again while it runs: refused, not queued
    with pytest.raises(ux_team.Busy, match="already working on this"):
        ux_team.request(product, conf, "round", "first-visit")
    v = ux_team.versions(product, "round", "first-visit")
    assert v[0]["status"]["phase"] == "queued" and v[0]["result"] is None and v[0]["key"] == "first-visit#r1"
    proc.end(3)
    v = ux_team.versions(product, "round", "first-visit")
    assert v[0]["status"] == {"phase": "failed", "note": "the run stopped (exit code 3)"}


def test_a_proposal_reads_the_last_round_the_agreement_and_the_focus(product, monkeypatch):
    add_shots(product)
    (product.root / "CLAUDE.md").write_text("# rules\n")
    monkeypatch.setenv("CRISSP_UX_MODEL", "a-model")
    finish(product, "round", "first-visit", 1, ROUND)
    (product.results / "decisions.jsonl").write_text(json.dumps({"id": "first-visit/r1/a0", "verdict": "agree"}) + "\n"
                                                     + json.dumps({"id": "other#v1", "verdict": "approve"}) + "\n")
    out = ux_team.start(product, _conf(product), "proposal", "first-visit", "the start button")
    assert out == {"kind": "proposal", "walk": "first-visit", "version": 1}
    vdir = product.results / "proposals" / "first-visit" / "v1"
    cmd = ux_team.popen.started[0].cmd
    assert cmd[-2:] == ["--model", "a-model"] and "the start button" in cmd[2] and "mockup.html" in cmd[2]
    assert str(product.root / "CLAUDE.md") in cmd[2]
    assert json.loads((vdir / "inputs" / "round.json").read_text()) == ROUND
    ctx = json.loads((vdir / "inputs" / "context.json").read_text())
    assert ctx["rounds"] == [ROUND] and [d["id"] for d in ctx["decisions"]] == ["first-visit/r1/a0"]
    finish(product, "proposal", "first-visit", 1, PROPOSAL)
    v = ux_team.versions(product, "proposal", "first-visit")[0]
    assert v["mockup"] == "/ux/results/proposals/first-visit/v1/mockup.html" and v["result"] == PROPOSAL


def test_a_proposal_without_a_round_says_so_in_its_brief(product):
    add_shots(product)
    ux_team.start(product, _conf(product), "proposal", "first-visit")
    assert "(none given: the must-advice" in ux_team.popen.started[0].cmd[2]
    assert not (product.results / "proposals" / "first-visit" / "v1" / "inputs" / "round.json").exists()


def test_what_cannot_start_is_refused_with_why(product):
    conf = _conf(product)
    with pytest.raises(ValueError, match="kind must be one of round, proposal"):
        ux_team.start(product, conf, "poll", "first-visit")
    with pytest.raises(ValueError, match="unknown walk 'nowhere' \\(known: first-visit\\)"):
        ux_team.start(product, conf, "round", "nowhere")
    with pytest.raises(ValueError, match="no screenshots yet: crissp/ux.sh --shoot first-visit"):
        ux_team.start(product, conf, "round", "first-visit")
    assert ux_team.popen.started == [] and ux_team.shots(product, "first-visit") == []


def test_a_walk_s_screenshots_are_listed_with_where_it_got_stuck(product):
    add_shots(product)
    shots = ux_team.shots(product, "first-visit")
    assert shots[0]["url"] == "/ux/results/shots/first-visit/laptop/01-the-first-screen.png" and shots[0]["path"]
    assert shots[1] == {"device": "phone", "n": 1, "title": "The first screen", "error": "Stuck at step 2", "path": None, "url": None}


def test_the_places_fill_up_and_the_rest_waits_in_the_queue(product, monkeypatch):
    walks = {w: {"title": w, "steps": [{"do": "shot", "title": "x"}]} for w in ("a", "b", "c")}
    suite = make_product(product.root.parent / "three", walks=walks)
    for w in walks:
        add_shots(suite, w)
    monkeypatch.setenv("UXSUITE_PARALLEL", "2")
    conf = _conf(suite)
    assert ux_team.slots(conf) == 2
    assert "started" in ux_team.request(suite, conf, "round", "a")
    assert "started" in ux_team.request(suite, conf, "round", "b")
    out = ux_team.request(suite, conf, "round", "c", "focus c")
    assert out["queued"] == 1 and "works on 2 things at once" in out["why"]
    assert ux_team.request(suite, conf, "proposal", "a")["queued"] == 2
    assert not ux_team.enqueue(suite, "round", "c")  # waiting already: once
    st = ux_team.state(suite, conf)
    assert st["running"] == ["round:a", "round:b"] and st["free"] == 0 and st["waiting"] == ["round:c", "proposal:a"]
    assert st["text"] == "The team works on 2 of the 2 things it can do at once. 2 waiting."
    assert ux_team.drain(suite, conf, lambda e: pytest.fail("no place")) == []
    ux_team.popen.started[0].end()  # round a ends: one place; proposal:a may start, round:c is first
    began = []
    assert ux_team.drain(suite, conf, lambda e: began.append(e) or ux_team.start(suite, conf, e["kind"], e["walk"], e["focus"])) == ["round:c"]
    assert began[0]["focus"] == "focus c" and ux_team.queue(suite)[0]["kind"] == "proposal"


def test_the_queue_skips_what_runs_drops_what_fails_and_puts_back_what_finds_no_place(product, capsys):
    conf = _conf(product)
    ux_team.enqueue(product, "round", "first-visit", "f")
    ux_team.enqueue(product, "proposal", "first-visit", "g", front=True)
    assert [x["kind"] for x in ux_team.queue(product)] == ["proposal", "round"]
    assert ux_team.dequeue(product, {"proposal:first-visit", "round:first-visit"}) is None

    def full(entry):
        raise ux_team.Full("every place taken")
    assert ux_team.drain(product, conf, full) == [] and ux_team.queue(product)[0]["kind"] == "proposal"

    def broken(entry):
        raise ValueError("bad entry")
    assert ux_team.drain(product, conf, broken) == [] and ux_team.queue(product) == []
    assert "queue: proposal:first-visit: bad entry" in capsys.readouterr().err


def test_nothing_starts_while_a_check_run_holds_the_machine(product):
    add_shots(product)
    conf = _conf(product)
    product.lock.mkdir(parents=True)
    out = ux_team.request(product, conf, "round", "first-visit")
    assert out["queued"] == 1 and "a check run is going on" in out["why"]
    assert ux_team.state(product, conf)["text"] == "A check run is going on: the team starts nothing new until it is done. 1 waiting."
    assert ux_team.drain(product, conf, lambda e: pytest.fail("must wait")) == []
    product.lock.rmdir()
    assert ux_team.state(product, conf)["text"] == "The team is free (up to 3 at once). 1 waiting."
    assert ux_team.why_not(product, conf, "round:first-visit")[1] is None


def test_a_run_another_process_started_counts_while_its_log_grows(product):
    vdir = product.results / "rounds" / "first-visit" / "r1"
    vdir.mkdir(parents=True)
    (vdir / "request.json").write_text(json.dumps({"kind": "round", "walk": "first-visit"}))
    (vdir / "status.json").write_text(json.dumps({"phase": "debate"}))
    assert ux_team.running(product) == []  # no log: not running
    (vdir / "run.log").write_text("")
    assert ux_team.running(product) == ["round:first-visit"]
    old = time.time() - ux_team.STALE - 5
    os.utime(vdir / "run.log", (old, old))
    assert ux_team.running(product) == []  # stale: a run that died
    (vdir / "status.json").write_text(json.dumps({"phase": "done"}))
    ux_team._running[str(vdir)] = type("P", (), {"poll": lambda self: 0, "returncode": 0})()
    assert ux_team.running(product) == [] and ux_team.versions(product, "round", "first-visit")[0]["status"] == {"phase": "done"}
    (product.results / "rounds" / "first-visit" / "notes").mkdir()  # not a version
    assert len(ux_team.versions(product, "round", "first-visit")) == 1


def test_a_bad_parallel_setting_keeps_the_configured_one(product, monkeypatch):
    monkeypatch.setenv("UXSUITE_PARALLEL", "many")
    assert ux_team.slots(_conf(product)) == 3
    monkeypatch.setenv("UXSUITE_PARALLEL", "0")
    assert ux_team.slots(_conf(product)) == 1


def test_a_team_of_moderators_still_has_someone_to_look(tmp_path, monkeypatch):
    started = []
    monkeypatch.setattr(ux_team, "popen", lambda cmd, **kw: started.append(cmd) or type("P", (), {"poll": lambda s: None})())
    monkeypatch.setattr(ux_team, "_running", {})
    team = {"product": "Solo", "url": "http://127.0.0.1:1", "personas": [
        {"key": "ux", "name": "Ada", "role": "UX expert", "moderator": True, "brief": "Moderates."}]}
    suite = make_product(tmp_path, team=team)
    add_shots(suite)
    ux_team.start(suite, ux_config.load(suite), "round", "first-visit")
    assert '"review ux"' in started[0][2]
