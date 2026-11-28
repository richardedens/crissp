"""E1-F1-01: how many workers a step gets on this machine. Every source (the CPUs, /proc, the cgroup, sysctl, vm_stat)
is a stand-in: the tests never depend on the machine they run on."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / "crissp" / "testsuite" / "lib"))
import workers  # noqa: E402

GB = 1024  # MB

VM_STAT = """Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                                     6636.
Pages active:                                1413712.
Pages inactive:                              1262283.
Pages speculative:                            149887.
Pages wired down:                             254902.
"""
MEMINFO = "MemTotal:        8000000 kB\nMemFree:          500000 kB\nMemAvailable:    7168000 kB\n"


class Cpus:
    def __init__(self, n):
        self.n = n

    def process_cpu_count(self):
        return self.n


def files(root: Path, entries: dict[str, str]) -> Path:
    for rel, text in entries.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    return root


def commands(answers: dict[str, str]):
    def run(cmd: list[str]) -> str | None:
        return answers.get(" ".join(cmd))
    return run


def test_a_mac_counts_its_cpus_its_memory_and_what_is_available(tmp_path):
    run = commands({"sysctl -n hw.memsize": "51539607552\n", "vm_stat": VM_STAT})
    m = workers.machine(tmp_path, run, "darwin", Cpus(16))
    assert m["cpus"] == 16 and m["memory_mb"] == 48 * GB
    assert m["available_mb"] == (6636 + 1262283 + 149887) * 16384 // 2**20  # free, inactive and speculative pages
    assert m["memory_from"] == "sysctl hw.memsize, vm_stat"


def test_linux_reads_proc_and_a_cgroup_limits_both(tmp_path):
    root = files(tmp_path, {"proc/meminfo": MEMINFO})
    m = workers.machine(root, commands({}), "linux", Cpus(4))
    assert (m["cpus"], m["memory_mb"], m["available_mb"]) == (4, 7812, 7000) and m["memory_from"] == "/proc/meminfo"
    files(root, {"sys/fs/cgroup/cpu.max": "150000 100000\n", "sys/fs/cgroup/memory.max": str(3 * 2**30) + "\n",
                 "sys/fs/cgroup/memory.current": str(2**30) + "\n"})
    m = workers.machine(root, commands({}), "linux", Cpus(4))
    assert m["cpus"] == 2 and m["cpu_from"] == "cgroup cpu.max: 1.5 of 4 CPUs"  # a quota of 1.5 is 2 at most
    assert (m["memory_mb"], m["available_mb"]) == (3072, 2048) and m["memory_from"] == "/proc/meminfo, cgroup memory.max"
    files(root, {"sys/fs/cgroup/cpu.max": "max 100000\n", "sys/fs/cgroup/memory.max": "max\n"})
    m = workers.machine(root, commands({}), "linux", Cpus(4))
    assert (m["cpus"], m["available_mb"]) == (4, 7000)  # no limit set
    (root / "sys/fs/cgroup/memory.current").unlink()
    files(root, {"sys/fs/cgroup/memory.max": str(2**30) + "\n"})
    assert workers.machine(root, commands({}), "linux", Cpus(4))["available_mb"] == 1024  # what it uses: unknown, so 0


def test_what_cannot_be_read_is_unknown_never_an_error(tmp_path):
    files(tmp_path, {"proc/meminfo": "nonsense\n", "sys/fs/cgroup/cpu.max": "x y\n", "sys/fs/cgroup/memory.max": "1073741824\n"})  # a limit, no meminfo
    m = workers.machine(tmp_path, commands({"vm_stat": "nothing"}), "linux", Cpus(None))
    assert m == {"cpus": 1, "cpu_from": "unknown: 1 CPU assumed", "memory_mb": None, "available_mb": None,
                 "memory_from": "unknown"}
    m = workers.machine(tmp_path, commands({"sysctl -n hw.memsize": "x", "vm_stat": "Pages free: 3."}), "darwin", Cpus(8))
    assert (m["memory_mb"], m["available_mb"]) == (None, None)
    assert workers.machine(tmp_path, commands({}), "win32", Cpus(8))["memory_from"] == "unknown"


def test_the_os_module_without_process_cpu_count_falls_back_to_cpu_count():
    class Old:
        def cpu_count(self):
            return 6
    assert workers.usable_cpus(Old()) == 6
    assert workers.machine(Path("/nowhere"), commands({}), "win32", Old())["cpu_from"] == "os.cpu_count"


@pytest.mark.parametrize("machine, memory_mb, n_files, env, expect", [
    ({"cpus": 16, "available_mb": 23 * GB}, 256, 40, {}, (15, "16 CPUs, one left for the machine")),
    ({"cpus": 2, "available_mb": 7 * GB}, 256, 40, {}, (1, "2 CPUs, one left for the machine")),
    ({"cpus": 16, "available_mb": 23 * GB}, 256, 3, {}, (3, "3 test files")),
    ({"cpus": 16, "available_mb": 2 * GB}, 512, 40, {}, (3, "2.0 GB available, 512 MB per worker")),
    ({"cpus": 16, "available_mb": 100}, 256, 40, {}, (1, "0.1 GB available, 256 MB per worker")),
    ({"cpus": 16, "available_mb": None}, 256, None, {}, (15, "16 CPUs, one left for the machine")),
    ({"cpus": 16, "available_mb": 23 * GB}, 256, 40, {"CRISSP_WORKERS": "4"}, (4, "CRISSP_WORKERS=4")),
    ({"cpus": 16, "available_mb": 23 * GB}, 256, 0, {"CRISSP_WORKERS": "none"}, (1, "0 test files")),
])
def test_a_steps_workers_are_the_tightest_limit(machine, memory_mb, n_files, env, expect):
    assert workers.count(machine, memory_mb, n_files, env) == expect


def test_test_files_are_counted_in_the_steps_test_folders(tmp_path):
    files(tmp_path, {"t/test_a.py": "", "t/sub/test_b.py": "", "t/b_test.py": "", "t/conftest.py": "", "u/test_c.py": ""})
    assert workers.test_files(tmp_path, ["t", "u", "missing"]) == 4


def test_it_says_the_machine_and_what_a_step_would_get(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(workers, "machine", lambda *a, **k: {"cpus": 8, "cpu_from": "os.process_cpu_count", "memory_mb": 16 * GB,
                                                            "available_mb": 9 * GB, "memory_from": "sysctl hw.memsize, vm_stat"})
    assert workers.main([], {}) == 0
    out = capsys.readouterr().out
    assert out == ("This machine: 8 CPUs (os.process_cpu_count), 16.0 GB memory, 9.0 GB available (sysctl hw.memsize, vm_stat).\n"
                   "A parallel step gets 7 workers here: 8 CPUs, one left for the machine.\n")
    monkeypatch.setattr(workers, "machine", lambda *a, **k: {"cpus": 1, "cpu_from": "unknown: 1 CPU assumed",
                                                            "memory_mb": None, "available_mb": None, "memory_from": "unknown"})
    workers.main([], {"CRISSP_WORKERS": "2"})
    assert capsys.readouterr().out == ("This machine: 1 CPU (unknown: 1 CPU assumed), memory unknown.\n"
                                       "A parallel step gets 2 workers here: CRISSP_WORKERS=2.\n")


def test_the_real_sources_answer_on_this_machine():
    """The one test that reads the machine it runs on: the readers must not fail on it (whatever it has)."""
    m = workers.machine()
    assert m["cpus"] >= 1 and isinstance(m["cpu_from"], str)
    assert workers._command(["a-command-that-does-not-exist-anywhere"]) is None


def test_a_command_answers_its_output_or_none_when_it_fails():
    """Portable (F-31): the output of a command that succeeds, None for one that fails; on every platform."""
    assert workers._command([sys.executable, "-c", "print('ok')"]) == "ok\n"
    assert workers._command([sys.executable, "-c", "raise SystemExit(3)"]) is None


# E1-F1-04: the /workers page's data, from what crissp_timing wrote (results/timing), with stand-in processes and clock

import json  # noqa: E402

FOUND = {"cpus": 4, "cpu_from": "os.process_cpu_count", "memory_mb": 8192, "available_mb": 4096, "memory_from": "x"}
T0 = 1_000_000.0


def timing(root: Path, step: str, rows: list[dict], now: dict[str, dict] | None = None) -> None:
    folder = root / "crissp/testsuite/results/timing"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{step}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows) + "not json\n")
    for worker, cur in (now or {}).items():
        (folder / f"{step}.now.{worker}.json").write_text(json.dumps(cur))


def ran(id_: str, worker: str | None, outcome: str = "passed", seconds: float = 1.0, at: float = T0 + 5) -> dict:
    return {"kind": "test", "id": id_, "outcome": outcome, "seconds": seconds, "worker": worker, "at": at}


@pytest.fixture
def project_root(tmp_path) -> Path:
    files(tmp_path, {"crissp/testsuite/suites.json": json.dumps({"product": "Shop", "steps": [
        {"key": "unit", "label": "Unit tests", "run": "x", "parallel": True}]})})
    return tmp_path


def test_a_running_step_shows_each_worker_what_it_runs_now_and_what_is_left(project_root):
    timing(project_root, "unit", [
        {"kind": "start", "at": T0, "pid": 11, "workers": 2, "why": "3 CPUs, one left for the machine"},
        {"kind": "collected", "n": 10, "worker": "gw0"}, {"kind": "collected", "n": 10, "worker": "gw1"},
        ran("tests/test_a.py::test_one", "gw0", seconds=2.0), ran("tests/test_a.py::test_two", "gw0", "failed"),
        ran("tests/test_b.py::test_one", "gw1", "skipped", 0.0, at=T0 + 8)],
        now={"gw0": {"id": "tests/test_a.py::test_three", "at": T0 + 6},
             "gw1": {"id": "tests/test_b.py::test_one", "at": T0 + 7},  # finished since (T0 + 8): not running now
             "gw2": {"id": "tests/test_c.py::test_old", "at": T0 - 100}})  # from before this run started
    s = workers.state(project_root, now=T0 + 10, alive=lambda pid: pid == 11, found=FOUND, env={})
    assert s["product"] == "Shop" and s["machine"] == FOUND
    assert s["would"] == {"workers": 3, "why": "4 CPUs, one left for the machine"}
    (step,) = s["steps"]
    assert {k: step[k] for k in ("key", "label", "status", "workers", "why", "collected", "done", "elapsed", "left")} == {
        "key": "unit", "label": "Unit tests", "status": "running", "workers": 2, "why": "3 CPUs, one left for the machine",
        "collected": 10, "done": 3, "elapsed": 10, "left": 23}  # 10 s for 3 tests: about 23 s for the other 7
    assert step["outcomes"] == {"passed": 1, "failed": 1, "skipped": 1} and step["failed"] == ["tests/test_a.py::test_two"]
    gw0, gw1 = step["lanes"]  # gw2's file is from before this run
    assert (gw0["worker"], gw0["done"], gw0["passed"], gw0["failed"], gw0["busy"]) == ("gw0", 2, 1, 1, 3.0)
    assert (gw0["now"], gw0["since"], gw0["quiet"]) == ("tests/test_a.py::test_three", 4, False)
    assert gw1["now"] is None and gw1["last"] == "tests/test_b.py::test_one" and gw1["skipped"] == 1


def test_a_worker_quiet_for_a_minute_is_marked_and_lanes_sort_by_number(project_root):
    rows = [{"kind": "start", "at": T0, "pid": 11, "workers": 11}] + [ran(f"t{i}.py::x", f"gw{i}") for i in (10, 2)]
    timing(project_root, "unit", rows, now={"gw2": {"id": "t2.py::slow", "at": T0 + 6}})
    (step,) = workers.state(project_root, now=T0 + 90, alive=lambda pid: True, found=FOUND, env={})["steps"]
    assert [lane["worker"] for lane in step["lanes"]] == ["gw2", "gw10"]
    assert step["lanes"][0]["quiet"] and step["lanes"][0]["since"] == 84


def test_finished_and_stopped_steps_keep_their_lanes_but_run_nothing_now(project_root):
    timing(project_root, "unit", [{"kind": "start", "at": T0, "pid": 11, "workers": 1}, {"kind": "collected", "n": 2},
                                  ran("t.py::a", None), {"kind": "finish", "status": 1, "at": T0 + 20}],
           now={"gw0": {"id": "t.py::b", "at": T0 + 6}})
    timing(project_root, "lint", [{"kind": "start", "at": T0 + 30, "pid": 12},
                                  ran("u.py::a", None, at=T0 + 40)])
    timing(project_root, "empty", [{"kind": "collected", "n": 1}])  # no start line: not shown
    s = workers.state(project_root, now=T0 + 100, alive=lambda pid: False, found=FOUND, env={})
    lint, unit = s["steps"]  # the newest first
    assert (unit["status"], unit["elapsed"], unit["left"], unit["label"]) == ("failed", 20, None, "Unit tests")
    assert [lane["worker"] for lane in unit["lanes"]] == ["main", "gw0"] and unit["lanes"][1]["now"] is None
    assert (lint["status"], lint["elapsed"], lint["label"], lint["workers"], lint["why"]) == ("stopped", 10, "lint", 1, "")
    assert lint["lanes"][0]["since"] is None
    timing(project_root, "unit", [{"kind": "start", "at": T0 + 50, "pid": 11}, {"kind": "finish", "status": 0, "at": T0 + 51}])
    unit = next(st for st in workers.state(project_root, now=T0 + 100, alive=lambda pid: False, found=FOUND, env={})["steps"]
                if st["key"] == "unit")
    assert unit["status"] == "passed" and unit["lanes"] == []


def test_no_run_yet_and_no_configuration_still_show_the_machine(tmp_path, monkeypatch):
    monkeypatch.setattr(workers, "machine", lambda: FOUND)
    s = workers.state(tmp_path, now=T0, env={"CRISSP_WORKERS": "2"})
    assert s["steps"] == [] and s["product"] == tmp_path.name and s["would"] == {"workers": 2, "why": "CRISSP_WORKERS=2"}


def test_a_process_is_alive_only_while_it_runs():
    assert workers.alive(os.getpid())
    done = subprocess.run([sys.executable, "-c", "import os; print(os.getpid())"], capture_output=True, text=True)
    assert not workers.alive(int(done.stdout))
    assert not workers.alive(None) and not workers.alive("12")


def test_a_process_of_another_user_still_runs(monkeypatch):
    def refused(pid, signal):
        raise PermissionError
    monkeypatch.setattr(workers.os, "kill", refused)
    assert workers.alive(1)


def test_a_worker_file_being_written_or_broken_runs_nothing(project_root):
    timing(project_root, "unit", [{"kind": "start", "at": T0, "pid": 11, "workers": 2}])
    folder = project_root / "crissp/testsuite/results/timing"
    (folder / "unit.now.gw0.json").write_text("{half")
    (folder / "unit.now.gw1.json").write_text("[1]")
    (step,) = workers.state(project_root, now=T0 + 5, alive=lambda pid: True, found=FOUND, env={})["steps"]
    assert step["lanes"] == []  # no time in either: from before the run, so no lane
