"""Every test as it finishes, per worker (E1-F1-03): what the /workers page shows while a step runs.

`covered` (lib/steps.sh) loads it in every step's pytest (`-p crissp_timing`, this folder on PYTHONPATH; a folder of its
own, so a product's tests never import the testsuite's modules by accident). lib/run.py says where to write:

    $CRISSP_TIMING_DIR/<step>.jsonl          one JSON line each: start (when, the process, WORKERS and WORKERS_WHY),
                                             collected (how many tests), test (id, outcome, seconds, worker), finish
    $CRISSP_TIMING_DIR/<step>.now.<w>.json   an xdist worker's test right now, replaced each time (never half a file)

With xdist the controller hears every worker's results, with the worker's name, and writes the lines; each worker
writes only its own now file. A pytest that a test starts itself (with the same file to write) stays quiet. It only
writes: it never changes an outcome, and a write that fails (a full disc, a folder that is gone) is dropped.
"""

import json
import os
import re
import time

import pytest

ACTIVE = "CRISSP_TIMING_ACTIVE"  # the file the outermost pytest writes; a pytest it starts inherits it and stays quiet
WORKER = re.compile(r"gw\d+")
_out: dict = {"path": None}
_now: dict = {"path": None}
_tests: dict[str, dict] = {}  # nodeid → seconds so far, outcome so far (setup, call and teardown each report)


def _write(record: dict) -> None:
    if not _out["path"]:
        return
    try:
        with open(_out["path"], "a") as f:
            f.write(json.dumps(record) + "\n")
    except OSError:
        pass  # the timing is for people: it never fails a test


def _step() -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", os.environ.get("STEP") or "pytest")


def pytest_configure(config):
    folder = os.environ.get("CRISSP_TIMING_DIR")
    if not folder:
        return
    if hasattr(config, "workerinput"):  # an xdist worker: only what it runs now (the controller writes what finished)
        worker = str(config.workerinput.get("workerid") or "")
        if WORKER.fullmatch(worker):
            _now["path"] = os.path.join(folder, f"{_step()}.now.{worker}.json")
        return
    path = os.path.join(folder, f"{_step()}.jsonl")
    if os.environ.get(ACTIVE) == path:
        return
    os.environ[ACTIVE] = path
    try:
        os.makedirs(folder, exist_ok=True)
    except OSError:
        return
    _out["path"] = path
    workers = os.environ.get("WORKERS", "")
    _write({"kind": "start", "at": time.time(), "pid": os.getpid(), "workers": int(workers) if workers.isdigit() else 1,
            "why": os.environ.get("WORKERS_WHY") or ""})


def pytest_collection_finish(session):
    _write({"kind": "collected", "n": len(session.items), "at": time.time()})


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    _write({"kind": "collected", "n": len(ids), "at": time.time(), "worker": node.gateway.id})


def pytest_runtest_logreport(report):
    test = _tests.setdefault(report.nodeid, {"seconds": 0.0, "outcome": "passed"})
    test["seconds"] += report.duration or 0.0
    if report.failed:
        test["outcome"] = "failed"
    elif report.skipped and test["outcome"] != "failed":
        test["outcome"] = "skipped"
    if report.when == "teardown":  # the last report of every test, also after a failed or skipped setup
        _tests.pop(report.nodeid)
        node = getattr(report, "node", None)  # with xdist: the worker it came from
        _write({"kind": "test", "id": report.nodeid, "outcome": test["outcome"], "seconds": round(test["seconds"], 3),
                "worker": node.gateway.id if node is not None else None, "at": time.time()})


def pytest_runtest_logstart(nodeid, location):
    if not _now["path"]:
        return
    try:  # replaced in one step: the page never reads half a file
        tmp = _now["path"] + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"id": nodeid, "at": time.time(), "pid": os.getpid()}, f)
        os.replace(tmp, _now["path"])
    except OSError:
        pass


def pytest_sessionfinish(session, exitstatus):
    _write({"kind": "finish", "status": int(exitstatus), "at": time.time()})
