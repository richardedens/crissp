"""Run the project's suites, step by step, and write what the gate, the certificate and the dashboard read.

    python3 crissp/testsuite/lib/run.py                  every step: the full run of crissp/check-all.sh
    python3 crissp/testsuite/lib/run.py --quick          every step that is not full_only (no build, no audit)
    python3 crissp/testsuite/lib/run.py --quick <step…>  only these steps (crissp/check.sh passes the ones a change
                                                         touches, lib/impact.py)

The steps are the project's (crissp/testsuite/suites.json, lib/project.py), each a bash command run in its folder with
lib/steps.sh at hand. Each step's output is results/<step>.log; results/steps.json is {step: "passed" | "failed"} for
this run and results/steps.jsonl has each step's label and duration too. The coverage gate is a step of its own
(lib/gate.py), for the gated steps this run measured. crissp/testsuite/run.sh runs lib/setup_plan.py first.
A parallel step (E1-F1) gets WORKERS and WORKERS_WHY: how many workers this machine gives it, and the limit that
decided it (lib/workers.py); the run prints them and steps.jsonl keeps them.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402
import workers  # noqa: E402

TOOLS = ENGINE.parent / "requirements.txt"  # the pinned test tools (pytest, pytest-xdist, coverage, ruff): one place
HELPERS = ENGINE / "steps.sh"


def select(every: list[dict], quick: bool, wanted: list[str]) -> list[dict]:
    """The steps of this run, in run order; raises ValueError for a step the project does not have."""
    known = [s["key"] for s in every]
    unknown = [w for w in wanted if w not in known]
    if unknown:
        raise ValueError(f"unknown step {', '.join(unknown)} (known: {' '.join(known) or 'none'})")
    if wanted:
        chosen = [s for s in every if s["key"] in wanted]
    else:
        chosen = [s for s in every if not (quick and s["full_only"])]
    ran = {s["key"] for s in chosen}
    return [{**s, "suites": [k for k in s["suites"] if k in ran]} if s["key"] == project.GATE else s for s in chosen]


def env_for(step: dict, root: Path, results: Path) -> dict:
    """What a step's command gets: where to write, the pinned tools, the helpers, what coverage measures."""
    key = step["key"]
    env = {**os.environ, "CRISSP_ROOT": str(root), "RESULTS": str(results), "STEP": key, "TOOLS": str(TOOLS),
           "JUNIT": str(results / f"{key}.xml"), "COVERAGE_JSON": str(results / f"coverage-{key}.json"),
           "COVERAGE_FILE": str(results / f".coverage-{key}"), "BASH_ENV": str(HELPERS)}
    for name, value in (("COVERAGE_SOURCES", ",".join(str(root / s) for s in step["sources"])),
                        ("COVERAGE_OMIT", ",".join(step["omit"])),
                        ("COVERAGE_FAIL_UNDER", "" if step["fail_under"] is None else f"{step['fail_under']:g}")):
        if value:
            env[name] = value
        else:
            env.pop(name, None)  # never one inherited from the shell that started the run
    for name, value in (("WORKERS", step.get("workers")), ("WORKERS_WHY", step.get("workers_why"))):
        if value:
            env[name] = str(value)
        else:
            env.pop(name, None)
    return env


def command(step: dict) -> list[str]:
    if step["key"] == project.GATE:
        return [sys.executable, str(ENGINE / "gate.py"), *(["--suites", ",".join(step["suites"])] if step["suites"] else [])]
    return ["bash", "-c", step["run"]]


def run_step(step: dict, root: Path, results: Path, runner=subprocess.run, clock=time.monotonic) -> dict:
    """Run one step, its output into results/<key>.log; its result as steps.jsonl keeps it."""
    folder = root / step["dir"]
    start = clock()
    with open(results / f"{step['key']}.log", "w") as log:
        if not folder.is_dir():
            log.write(f"no folder {step['dir']} in the project\n")
            status = "failed"
        else:
            done = runner(command(step), cwd=folder, env=env_for(step, root, results), stdout=log,
                          stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
            status = "passed" if done.returncode == 0 else "failed"
    row = {"key": step["key"], "label": step["label"], "status": status, "seconds": round(clock() - start)}
    return {**row, "workers": step["workers"], "workers_why": step["workers_why"]} if step.get("workers") else row


def clear(chosen: list[dict], results: Path) -> None:
    """The results of the previous run of these steps (only files this run writes itself)."""
    for s in chosen:
        for name in (f"{s['key']}.log", f"{s['key']}.xml", f"coverage-{s['key']}.json", f".coverage-{s['key']}",
                     f"coverage-{s['key']}.rc"):
            (results / name).unlink(missing_ok=True)
        for part in results.glob(f".coverage-{s['key']}.*"):  # a parallel step's workers' data a stopped run left
            part.unlink()
        if s["key"] == project.GATE:
            (results / "gate.json").unlink(missing_ok=True)
    for name in ("steps.jsonl", "steps.json"):
        (results / name).unlink(missing_ok=True)


def main(argv: list[str], root: Path | None = None, runner=subprocess.run, out=None) -> int:
    out = out or sys.stdout
    root = root or project.root()
    args = argv[1:]
    quick = bool(args) and args[0] == "--quick"
    wanted = args[1:] if quick else args
    try:
        every = project.steps(project.load(root), root)
        chosen = select(every, quick, wanted)
    except ValueError as e:  # a broken configuration, or a step the project does not have
        print(f"run: {e}", file=sys.stderr)
        return 2
    results = project.results(root)
    results.mkdir(parents=True, exist_ok=True)
    clear(chosen, results)
    rows = []
    found = workers.machine() if any(s["parallel"] for s in chosen) else None
    for step in chosen:
        if step["parallel"]:
            n, why = workers.count(found, step["memory_mb"], workers.test_files(root, step["tests"]), dict(os.environ))
            step = {**step, "workers": n, "workers_why": why}
        print(f"▸ {step['label']:<54}", end="", file=out, flush=True)
        row = run_step(step, root, results, runner)
        n = row.get("workers")
        spread = f", {n} worker{'s' if n != 1 else ''}" if n else ""
        print(f"{row['status']} ({row['seconds']}s{spread})", file=out, flush=True)
        rows.append(row)
        with open(results / "steps.jsonl", "a") as f:
            f.write(json.dumps(row) + "\n")
    (results / "steps.json").write_text(json.dumps({r["key"]: r["status"] for r in rows}, indent=1))
    return 1 if any(r["status"] == "failed" for r in rows) else 0


if __name__ == "__main__":  # pragma: no cover — run by crissp/testsuite/run.sh; main() is tested
    sys.exit(main(sys.argv))
