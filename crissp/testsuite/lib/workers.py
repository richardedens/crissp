"""How many workers a step's tests get on this machine (E1-F1): the CPUs and the memory it actually has.

    python3 crissp/testsuite/lib/workers.py      this machine, and what a parallel step gets here

The CPUs are the ones this process may use (os.process_cpu_count), capped by a cgroup quota (cpu.max, as on a CI runner
or in a container). The memory is what there is and what is available now: on macOS hw.memsize and vm_stat's free,
inactive and speculative pages; on Linux /proc/meminfo's MemTotal and MemAvailable, capped by a cgroup's memory.max.
What cannot be read is unknown, never an error: then that limit does not count.

A step's workers are the tightest of three limits, and never fewer than one:
- the CPUs, one left for the machine (the run itself, the dashboard, the editor);
- three quarters of the available memory, divided by what one worker needs (the step's memory_mb, default 256);
- the step's test files (one file stays on one worker, so more workers would only wait).
CRISSP_WORKERS=<n> sets it instead. The reason names the limit that decided it, so the plan and /workers can say why.

state() is what the /workers page shows (lib/serve.py, /dashboard/workers.json): this machine, what a parallel step
would get, and per step that ran (results/timing, written by lib/pytest_plugin/crissp_timing.py) its workers and why,
how far it is and about how long is left, its outcomes, and one lane per worker: what it runs now and since when (quiet
after a minute), what it finished and how long it was busy. A step whose process is gone without finishing is stopped.
"""

import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402

DEFAULT_MB = 256
QUIET_S = 60  # a worker on one test this long is marked quiet: a slow test, or one that hangs
SHARE = 0.75  # of the available memory: the rest stays for the machine
MB = 2**20


def _command(cmd: list[str]) -> str | None:
    """A command's output, or None when it is not there or fails."""
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def _text(path: Path) -> str | None:
    try:
        return path.read_text()
    except OSError:
        return None


def usable_cpus(os_=os) -> int | None:
    counter = getattr(os_, "process_cpu_count", None) or os_.cpu_count  # process_cpu_count: Python 3.13+
    return counter()


def _cgroup_cpus(root: Path) -> float | None:
    found = (_text(root / "sys/fs/cgroup/cpu.max") or "").split()
    try:
        quota, period = found
        return None if quota == "max" else int(quota) / int(period)
    except ValueError:
        return None


def _cgroup_memory(root: Path) -> tuple[int, int] | None:
    """(limit, limit less what the group uses) in MB, or None without a limit."""
    try:
        limit = int((_text(root / "sys/fs/cgroup/memory.max") or "").strip())
    except ValueError:
        return None
    try:
        used = int((_text(root / "sys/fs/cgroup/memory.current") or "").strip())
    except ValueError:
        used = 0
    return limit // MB, (limit - used) // MB


def _meminfo(root: Path) -> tuple[int | None, int | None]:
    found = dict(re.findall(r"^(\w+):\s+(\d+) kB", _text(root / "proc/meminfo") or "", re.MULTILINE))
    total, available = found.get("MemTotal"), found.get("MemAvailable")
    return (int(total) // 1024 if total else None), (int(available) // 1024 if available else None)


def _mac(run) -> tuple[int | None, int | None]:
    size = (run(["sysctl", "-n", "hw.memsize"]) or "").strip()
    total = int(size) // MB if size.isdigit() else None
    stat = run(["vm_stat"]) or ""
    page = re.search(r"page size of (\d+) bytes", stat)
    pages = {k: int(v) for k, v in re.findall(r"^Pages (\w+):\s+(\d+)\.", stat, re.MULTILINE)}
    available = None
    if page and pages:
        available = sum(pages.get(k, 0) for k in ("free", "inactive", "speculative")) * int(page.group(1)) // MB
    return total, available


def machine(root: Path = Path("/"), run=_command, platform: str = sys.platform, os_=os) -> dict:
    """This machine: its usable CPUs and its memory in MB (total, available), with where each came from."""
    n = usable_cpus(os_)
    called = "os.process_cpu_count" if hasattr(os_, "process_cpu_count") else "os.cpu_count"  # Python 3.12: cpu_count
    cpus, cpu_from = (n, called) if n else (1, "unknown: 1 CPU assumed")
    total = available = None
    sources = []
    if platform == "darwin":
        total, available = _mac(run)
        sources = ["sysctl hw.memsize, vm_stat"] if total else []
    elif platform.startswith("linux"):
        total, available = _meminfo(root)
        sources = ["/proc/meminfo"] if total else []
        quota = _cgroup_cpus(root)
        if quota:
            cpus, cpu_from = min(cpus, math.ceil(quota)), f"cgroup cpu.max: {quota:g} of {n} CPUs"
        limit = _cgroup_memory(root)
        if limit and total:
            total, available = min(total, limit[0]), min(available or limit[1], limit[1])
            sources.append("cgroup memory.max")
    return {"cpus": cpus, "cpu_from": cpu_from, "memory_mb": total, "available_mb": available if total else None,
            "memory_from": ", ".join(sources) or "unknown"}


def count(found: dict, memory_mb: int = DEFAULT_MB, files: int | None = None, env: dict | None = None) -> tuple[int, str]:
    """(workers, why) for a step on this machine: the tightest limit, at least 1, unless CRISSP_WORKERS says."""
    wanted = (env or {}).get("CRISSP_WORKERS", "")
    if wanted.isdigit() and int(wanted) >= 1:
        return int(wanted), f"CRISSP_WORKERS={wanted}"
    limits = [(found["cpus"] - 1, f"{found['cpus']} CPUs, one left for the machine")]
    if found.get("available_mb") is not None:
        limits.append((int(found["available_mb"] * SHARE // memory_mb),
                       f"{found['available_mb'] / 1024:.1f} GB available, {memory_mb} MB per worker"))
    if files is not None:
        limits.append((files, f"{files} test files"))
    n, why = min(limits, key=lambda limit: limit[0])
    return max(1, n), why


def test_files(project: Path, folders: list[str]) -> int:
    """The test files in a step's test folders (test_*.py, *_test.py)."""
    seen = set()
    for folder in folders:
        base = project / folder
        if base.is_dir():
            seen |= {p for p in base.rglob("*.py") if p.name.startswith("test_") or p.name.endswith("_test.py")}
    return len(seen)


def describe(found: dict) -> str:
    cpus = f"{found['cpus']} CPU{'s' if found['cpus'] != 1 else ''} ({found['cpu_from']})"
    if found["memory_mb"] is None:
        return f"This machine: {cpus}, memory unknown."
    return (f"This machine: {cpus}, {found['memory_mb'] / 1024:.1f} GB memory, {found['available_mb'] / 1024:.1f} GB "
            f"available ({found['memory_from']}).")


def alive(pid) -> bool:
    """Whether the process that wrote a step's start line still runs."""
    if not isinstance(pid, int):
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:  # it runs, as another user
        return True
    return True


def _rows(path: Path) -> list[dict]:
    out = []
    for line in path.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue  # a line being written right now
    return out


def _lane(name: str) -> dict:
    return {"worker": name, "done": 0, "passed": 0, "failed": 0, "skipped": 0, "busy": 0.0, "last": None, "last_at": None,
            "now": None, "now_at": None}


def _order(lane: dict) -> tuple:
    digits = "".join(c for c in lane["worker"] if c.isdigit())
    return (int(digits) if digits else -1, lane["worker"])


def step_state(folder: Path, path: Path, label: str, now: float, alive) -> dict | None:
    """One step's run, from its timing file and its workers' now files; None without a start line."""
    key, rows = path.stem, _rows(path)
    start = next((r for r in rows if r.get("kind") == "start"), None)
    if start is None:
        return None
    began = start.get("at") or now
    finish = next((r for r in rows if r.get("kind") == "finish"), None)
    gone = finish is None and not alive(start.get("pid"))
    running = finish is None and not gone
    tests = [r for r in rows if r.get("kind") == "test"]
    lanes: dict[str, dict] = {}
    for r in tests:
        lane = lanes.setdefault(r.get("worker") or "main", _lane(r.get("worker") or "main"))
        outcome = r.get("outcome") if r.get("outcome") in ("passed", "failed", "skipped") else "passed"
        lane["done"] += 1
        lane[outcome] += 1
        lane["busy"] += r.get("seconds") or 0.0
        lane["last"], lane["last_at"] = r.get("id"), r.get("at")
    for now_file in sorted(folder.glob(f"{key}.now.*.json")):
        cur = read_json(now_file)
        at = cur.get("at") or 0
        if at < began:  # a worker of an earlier run
            continue
        name = now_file.name[len(key) + 5:-5]
        lane = lanes.setdefault(name, _lane(name))
        if running and not (lane["last_at"] and lane["last_at"] >= at):  # not finished since
            lane["now"], lane["now_at"] = cur.get("id"), at
    end = finish.get("at", now) if finish else now if running else max((r.get("at") or began for r in rows), default=began)
    elapsed, done = end - began, len(tests)
    collected = max((r.get("n") or 0 for r in rows if r.get("kind") == "collected"), default=0)
    out_lanes = []
    for lane in sorted(lanes.values(), key=_order):
        since = round(now - lane["now_at"]) if lane["now"] else None
        out_lanes.append({**{k: v for k, v in lane.items() if k not in ("last_at", "now_at")}, "busy": round(lane["busy"], 1),
                          "since": since, "quiet": bool(since is not None and since > QUIET_S)})
    return {"key": key, "label": label, "workers": start.get("workers") or 1, "why": start.get("why") or "",
            "status": ("failed" if finish.get("status") else "passed") if finish else "running" if running else "stopped",
            "began": began, "elapsed": round(elapsed), "collected": collected, "done": done,
            "left": round(elapsed / done * (collected - done)) if running and done and collected > done else None,
            "outcomes": {k: sum(1 for r in tests if r.get("outcome") == k) for k in ("passed", "failed", "skipped")},
            "failed": [r.get("id") for r in tests if r.get("outcome") == "failed"][:50], "lanes": out_lanes}


def read_json(path: Path) -> dict:
    try:
        found = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return found if isinstance(found, dict) else {}


def state(root: Path, now: float | None = None, alive=alive, found: dict | None = None, env: dict | None = None) -> dict:
    """What /workers shows: this machine, what a parallel step would get here, and every step that ran (running first,
    then the newest)."""
    now = time.time() if now is None else now
    try:
        conf = project.load(root)
    except project.ConfigError:
        conf = {"product": root.name, "monogram": root.name[:1].upper(), "steps": []}
    labels = {s["key"]: s["label"] for s in conf["steps"]}
    found = found or machine()
    n, why = count(found, env=dict(os.environ) if env is None else env)
    folder = project.results(root) / "timing"
    steps = [step_state(folder, p, labels.get(p.stem, p.stem), now, alive) for p in sorted(folder.glob("*.jsonl"))]
    steps = sorted((s for s in steps if s), key=lambda s: (s["status"] != "running", -s["began"]))
    return {"product": conf["product"], "monogram": conf["monogram"], "machine": found,
            "would": {"workers": n, "why": why}, "steps": steps, "now": now}


def main(argv: list[str], env: dict) -> int:
    found = machine()
    n, why = count(found, env=env)
    print(describe(found))
    print(f"A parallel step gets {n} worker{'s' if n != 1 else ''} here: {why}.")
    return 0


if __name__ == "__main__":  # pragma: no cover — run by people and crissp check --plan; main() is tested
    sys.exit(main(sys.argv[1:], dict(os.environ)))
