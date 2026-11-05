"""Shooting a walk (ux_shoot): the plan names the devices the team uses and the walk's steps; the browser run is a
stand-in (no browser, no network) and its outcome is told in plain words."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import PERSONAS, make_product, ux_config  # noqa: E402

import ux_shoot  # noqa: E402


def test_the_plan_takes_the_walk_on_the_team_s_devices(tmp_path):
    suite = make_product(tmp_path)
    p = ux_shoot.plan(suite, ux_config.load(suite), "first-visit")
    assert list(p["devices"]) == ["laptop", "phone"] and p["devices"]["phone"] == {"width": 390, "height": 844, "touch": True}
    assert p["url"] == "http://127.0.0.1:5173" and p["steps"][0] == {"do": "goto", "path": "/"}
    desk = make_product(tmp_path / "desk", team={"product": "D", "url": "http://x", "personas": [
        {**PERSONAS[0], "moderator": True}]})
    assert ux_shoot.devices(ux_config.load(desk)) == ["laptop"]
    with pytest.raises(ValueError, match="unknown walk 'x'"):
        ux_shoot.plan(suite, ux_config.load(suite), "x")
    assert ux_shoot.slug("The first screen!") == "the-first-screen" and ux_shoot.slug("!!") == "shot"


def _browser(shots=None, code=0, err=""):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        out = Path(cmd[-1]).parent
        if shots is not None:
            (out / "shots.json").write_text(json.dumps(shots))
        return subprocess.CompletedProcess(cmd, code, "", err)
    return run, calls


def test_a_shoot_runs_the_browser_under_uv_and_says_what_came_back(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    old = suite.results / "shots" / "first-visit" / "laptop" / "old.png"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"old")
    run, calls = _browser([{"device": "laptop", "n": 1, "title": "a", "file": "laptop/01-a.png"},
                           {"device": "phone", "n": 1, "title": "a", "file": "", "error": "Stuck at step 2 (click)"}])
    code, text = ux_shoot.shoot(suite, conf, "first-visit", run)
    assert code == 0 and not old.exists()
    assert text == "first-visit: 1 screenshot(s) in crissp/uxsuite/results/shots/first-visit\n  phone: Stuck at step 2 (click)"
    assert calls[0][:6] == ["uv", "run", "--quiet", "--no-project", "--with", ux_shoot.PLAYWRIGHT]
    assert json.loads(Path(calls[0][-1]).read_text())["walk"] == "first-visit"


def test_a_shoot_that_fails_says_how_to_get_the_browser(tmp_path):
    suite = make_product(tmp_path)
    conf = ux_config.load(suite)
    code, text = ux_shoot.shoot(suite, conf, "first-visit", _browser(code=1, err="Executable doesn't exist")[0])
    assert code == 1 and "Executable doesn't exist" in text and "playwright install chromium" in text
    code, text = ux_shoot.shoot(suite, conf, "first-visit", _browser()[0])
    assert code == 1 and "without a list of shots" in text
