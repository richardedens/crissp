"""E1-F1-03: every test as it finishes, per worker (lib/pytest_plugin/crissp_timing.py), for the /workers page. Real
pytest runs on a tiny project, with and without xdist; the plugin only writes, and a write that fails never fails a test."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

PLUGINS = Path(__file__).resolve().parents[1] / "lib" / "pytest_plugin"
sys.path.insert(0, str(PLUGINS))
import crissp_timing

TESTS = {
    "tests/test_one.py": "def test_passes():\n    assert True\n\n\ndef test_fails():\n    assert False\n",
    "tests/test_two.py": "import pytest\n\n\n@pytest.mark.skip(reason='later')\ndef test_skipped():\n    pass\n\n\n"
                         "def test_also_passes():\n    assert 1\n",
}


@pytest.fixture
def tiny(tmp_path) -> Path:
    for rel, text in TESTS.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    return tmp_path


def pytest_run(root: Path, timing: Path, *args: str, **env: str) -> subprocess.CompletedProcess:
    clean = {k: v for k, v in os.environ.items() if k not in (crissp_timing.ACTIVE, "PYTEST_ADDOPTS")}
    return subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "crissp_timing", *args,
                           "tests"], cwd=root, capture_output=True, text=True, timeout=120,
                          env={**clean, "PYTHONPATH": str(PLUGINS), "CRISSP_TIMING_DIR": str(timing), "STEP": "unit",
                               "WORKERS": "2", "WORKERS_WHY": "3 CPUs, one left for the machine", **env}, check=False)


def lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_one_process_writes_every_test_as_it_finishes(tiny):
    timing = tiny / "results" / "timing"
    done = pytest_run(tiny, timing)
    assert done.returncode == 1  # its own outcome, untouched: one test fails
    rows = lines(timing / "unit.jsonl")
    assert [r["kind"] for r in rows] == ["start", "collected", "test", "test", "test", "test", "finish"]
    start = rows[0]
    assert start["workers"] == 2 and start["why"] == "3 CPUs, one left for the machine" and start["pid"] > 0
    assert rows[1]["n"] == 4 and rows[-1]["status"] == 1
    tests = {r["id"]: r for r in rows if r["kind"] == "test"}
    assert {k: v["outcome"] for k, v in tests.items()} == {
        "tests/test_one.py::test_passes": "passed", "tests/test_one.py::test_fails": "failed",
        "tests/test_two.py::test_skipped": "skipped", "tests/test_two.py::test_also_passes": "passed"}
    assert all(r["worker"] is None and r["seconds"] >= 0 for r in tests.values())
    assert not list(timing.glob("unit.now.*"))  # one process: no worker files


def test_xdist_workers_say_their_name_and_what_they_run_now(tiny):
    timing = tiny / "results" / "timing"
    done = pytest_run(tiny, timing, "-n", "2", "--dist", "loadfile")
    assert done.returncode == 1, done.stdout + done.stderr
    rows = lines(timing / "unit.jsonl")
    assert rows[0]["kind"] == "start" and rows[-1]["kind"] == "finish"
    assert max(r["n"] for r in rows if r["kind"] == "collected") == 4
    tests = [r for r in rows if r["kind"] == "test"]
    assert len(tests) == 4 and {r["worker"] for r in tests} <= {"gw0", "gw1"}
    by_file = {r["id"].split("::")[0]: r["worker"] for r in tests}
    assert all(r["worker"] == by_file[r["id"].split("::")[0]] for r in tests)  # a file stays on one worker
    nows = {p.name: json.loads(p.read_text()) for p in timing.glob("unit.now.*.json")}
    assert set(nows) <= {"unit.now.gw0.json", "unit.now.gw1.json"} and nows
    assert all(n["id"].startswith("tests/test_") and n["at"] > 0 for n in nows.values())


def test_a_pytest_a_test_starts_itself_stays_quiet_and_another_step_does_not(tiny):
    timing = tiny / "results" / "timing"
    path = str(timing / "unit.jsonl")
    pytest_run(tiny, timing, **{crissp_timing.ACTIVE: path})  # the outer run writes there already
    assert not (timing / "unit.jsonl").exists()
    pytest_run(tiny, timing, **{crissp_timing.ACTIVE: "/elsewhere/other.jsonl"})  # another project's run: its own
    assert (timing / "unit.jsonl").is_file()


def test_a_place_that_cannot_be_written_never_fails_a_test(tiny):
    (tiny / "taken").write_text("a file, not a folder")
    done = pytest_run(tiny, tiny / "taken", "-k", "passes")
    assert done.returncode == 0, done.stdout + done.stderr
    done = pytest_run(tiny, tiny / "taken", "-n", "2", "-k", "passes")
    assert done.returncode == 0, done.stdout + done.stderr


def test_without_a_timing_folder_it_does_nothing(tiny):
    done = pytest_run(tiny, tiny / "unused", "-k", "passes", CRISSP_TIMING_DIR="")
    assert done.returncode == 0 and not (tiny / "unused").exists()


def test_writes_that_fail_are_dropped(tmp_path, monkeypatch):
    monkeypatch.setitem(crissp_timing._out, "path", str(tmp_path / "gone" / "unit.jsonl"))
    crissp_timing._write({"kind": "x"})  # no folder: dropped, no error
    monkeypatch.setitem(crissp_timing._now, "path", str(tmp_path / "gone" / "unit.now.gw0.json"))
    crissp_timing.pytest_runtest_logstart("t::x", ("t", 1, "x"))
    monkeypatch.setitem(crissp_timing._now, "path", None)
    crissp_timing.pytest_runtest_logstart("t::x", ("t", 1, "x"))  # not a worker: nothing
    assert not (tmp_path / "gone").exists()


def test_a_worker_with_an_odd_name_writes_no_now_file(tmp_path, monkeypatch):
    class Config:
        workerinput = {"workerid": "../../etc"}  # noqa: RUF012  (a stand-in for pytest-xdist's config)
    monkeypatch.setenv("CRISSP_TIMING_DIR", str(tmp_path))
    monkeypatch.setitem(crissp_timing._now, "path", None)
    crissp_timing.pytest_configure(Config())
    assert crissp_timing._now["path"] is None
