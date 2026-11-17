"""E1-F1-01: how many workers a step gets on this machine. Every source (the CPUs, /proc, the cgroup, sysctl, vm_stat)
is a stand-in: the tests never depend on the machine they run on."""

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
