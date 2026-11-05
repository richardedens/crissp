"""The UX suite from the terminal: cli.main (list, status, round, propose, shoot) and crissp/ux.sh around it."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ux_kit import REPO, ROUND, add_shots, finish, make_product, product, ux_team  # noqa: E402,F401

import cli  # noqa: E402


def test_list_names_the_team_and_the_walks(product, capsys):
    assert cli.main(["list"], product) == 0
    out = capsys.readouterr().out
    assert out.startswith("Example Shop: A shop.\nRuns against http://127.0.0.1:5173.")
    assert "ux         Ada, UX expert (both) — moderator" in out and "first-visit        First visit" in out


def test_list_without_walks_says_where_they_go(tmp_path, capsys):
    suite = make_product(tmp_path, walks={})
    assert cli.main(["list"], suite) == 0 and "none yet: add one to crissp/uxsuite/walks/" in capsys.readouterr().out


def test_status_counts_what_the_team_did(product, capsys):
    add_shots(product)
    finish(product, "round", "first-visit", 1, ROUND)
    (product.results / "decisions.jsonl").write_text(json.dumps({"id": "first-visit/r1/a0", "verdict": "agree"}) + "\n")
    assert cli.main(["status"], product) == 0
    assert capsys.readouterr().out == "The team is free (up to 3 at once).\n1 round(s), 0 design(s), 1 verdict(s).\n"
    assert cli.main(["round", "first-visit"], product) == 0
    assert capsys.readouterr().out == "Started: round 2 of first-visit (results/rounds/first-visit).\n"
    assert cli.main(["status"], product) == 0
    assert "  running: round:first-visit" in capsys.readouterr().out


def test_round_and_propose_start_or_queue(product, capsys):
    add_shots(product)
    product.lock.mkdir(parents=True)
    assert cli.main(["propose", "first-visit", "the", "start"], product) == 0
    out = capsys.readouterr().out
    assert out.startswith("Queued as number 1 (a check run is going on") and "crissp/ux.sh opens it" in out
    assert ux_team.queue(product)[0]["focus"] == "the start"
    assert cli.main(["status"], product) == 0 and "  waiting: proposal:first-visit" in capsys.readouterr().out
    assert cli.main(["round", "nowhere"], product) == 1 and "unknown walk" in capsys.readouterr().err


def test_shoot_says_what_the_browser_did(product, capsys):
    def browser(cmd, **kw):
        (Path(cmd[-1]).parent / "shots.json").write_text("[]")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    assert cli.main(["shoot", "first-visit"], product, run=browser) == 0
    assert "first-visit: 0 screenshot(s)" in capsys.readouterr().out


def test_a_wrong_command_shows_the_help(product, capsys):
    for argv in ([], ["fly"], ["round"]):
        assert cli.main(argv, product) == 2
    assert "cli.py round <walk>" in capsys.readouterr().err
    (product.here / "team.json").write_text("{}")
    assert cli.main(["list"], product) == 1 and "product must be a text" in capsys.readouterr().err


def _copy_suite(tmp_path) -> Path:
    """This repository's crissp/ux.sh and UX suite in a throwaway product (the real config, no results)."""
    root = tmp_path / "copy"
    (root / "crissp").mkdir(parents=True)
    shutil.copy(REPO / "crissp" / "ux.sh", root / "crissp" / "ux.sh")
    shutil.copytree(REPO / "crissp" / "uxsuite", root / "crissp" / "uxsuite",
                    ignore=shutil.ignore_patterns("results", "tests", "__pycache__"))
    return root


def sh(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([str(root / "crissp" / "ux.sh"), *args], cwd=root, capture_output=True, text=True, timeout=60,
                          env={**os.environ, "UXSUITE_PARALLEL": ""})


def test_ux_sh_lists_reports_and_refuses_what_it_does_not_know(tmp_path):
    root = _copy_suite(tmp_path)
    r = sh(root, "--list")
    assert r.returncode == 0 and r.stdout.startswith("C.R.I.S.S.P.: ") and "tests-overview" in r.stdout
    r = sh(root, "--status")
    assert r.returncode == 0 and "0 round(s), 0 design(s), 0 verdict(s)." in r.stdout
    r = sh(root, "--round", "tests-overview")
    assert r.returncode == 1 and "no screenshots yet: crissp/ux.sh --shoot tests-overview" in r.stderr
    r = sh(root, "--fly")
    assert r.returncode == 2 and "crissp/ux.sh --round <walk>" in r.stderr


def test_ux_sh_without_an_argument_opens_the_suite_in_the_dashboard(tmp_path):
    root = _copy_suite(tmp_path)
    (root / "crissp" / "test.sh").write_text('#!/usr/bin/env bash\necho "test.sh $*"\n')
    (root / "crissp" / "test.sh").chmod(0o755)
    r = sh(root)
    assert r.returncode == 0 and r.stdout == "test.sh --ux\n"
