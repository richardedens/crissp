"""Turn the raw results (JUnit XML, coverage JSON, step log) and changes.json into results/data.js for the dashboard.

    python3 crissp/testsuite/lib/collect.py        (crissp/test.sh runs it; the live server too, when something changed)

What differs per product comes from its crissp/testsuite/suites.json (lib/project.py): its name and monogram, its steps
(each step's JUnit XML is results/<key>.xml, its test files are in the step's `tests` folders), which steps measure
coverage, and the E2E and journey texts. The backlog is read by the crissp tool itself; a PBI an approved UX design
became (its Depends line names the design: UX proposal <walk>#v<n>) links back to that design in the UX suite."""

import ast
import importlib.util
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

ENGINE = Path(__file__).resolve().parent
sys.path.insert(0, str(ENGINE))
import project  # noqa: E402

TOOL = ENGINE.parents[1] / "tool" / "server.py"  # the crissp tool, beside this engine: the one backlog parser
UX_MARK = re.compile(r"UX\s+proposal\s+`([^`]+)`")
SPECIAL = ("e2e", "journeys")  # steps the dashboard shows on their own tabs, not among the unit tests

# Set by configure() from the project: where it is, its configuration, and per step (label, test folders, its folder).
ROOT = Path(".")
RESULTS = ROOT / "results"
CONFIG: dict = {"product": "", "monogram": "", "texts": {}, "steps": []}
SUITES: dict[str, tuple[str, list[Path], Path]] = {}
COVERAGE: list[str] = []


def configure(root: Path) -> None:
    global ROOT, RESULTS, CONFIG, SUITES, COVERAGE
    ROOT, RESULTS, CONFIG = root, project.results(root), project.load(root)
    steps = [s for s in project.steps(CONFIG, root) if s["key"] != project.GATE]
    SUITES = {s["key"]: (s["label"], [root / t for t in s["tests"]], root / s["dir"]) for s in steps}
    COVERAGE = [s["key"] for s in steps if s["coverage"]]


def _docs(test_file: Path) -> dict[str, tuple[str, int]]:
    """Docstring and line of every test function in a file (what the test proves, where it is)."""
    try:
        tree = ast.parse(test_file.read_text())
    except (OSError, SyntaxError):
        return {}
    out = {"__module__": ((ast.get_docstring(tree) or "").strip(), 1)}
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test"):
            out[n.name] = ((ast.get_docstring(n) or "").strip(), n.lineno)
    return out


def _test_file(key: str, classname: str) -> tuple[str, Path]:
    """(module, file) of a JUnit classname ("tests.test_x", "test_x", "tests.test_x.TestCase"): the last part that is a
    file in one of the step's test folders, else the last part, in the first folder."""
    parts = classname.split(".") if classname else [""]
    folders = SUITES[key][1] or [SUITES[key][2]]
    for part in reversed(parts):
        for folder in folders:
            if (folder / f"{part}.py").is_file():
                return part, folder / f"{part}.py"
    return parts[-1], folders[0] / f"{parts[-1]}.py"


def _where(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT.resolve()))
    except ValueError:
        return str(path)


def tests_of(key: str) -> list[dict]:
    path = RESULTS / f"{key}.xml"
    if not path.exists():
        return []
    docs: dict[str, dict] = {}
    out = []
    for case in ET.parse(path).getroot().iter("testcase"):
        module, file = _test_file(key, case.get("classname", ""))
        if module not in docs:
            docs[module] = _docs(file)
        status, detail = "passed", ""
        for tag in ("failure", "error", "skipped"):
            el = case.find(tag)
            if el is not None:
                status = {"failure": "failed", "error": "failed", "skipped": "skipped"}[tag]
                detail = ((el.get("message") or "") + "\n" + (el.text or "")).strip()[-4000:]
        doc, line = docs[module].get(case.get("name"), ("", 0))
        out.append({"suite": key, "module": module, "name": case.get("name"), "id": f"{module}::{case.get('name')}", "status": status,
                    "time": round(float(case.get("time") or 0), 3), "doc": doc, "moduleDoc": docs[module].get("__module__", ("", 1))[0],
                    "file": _where(file), "abs": str(file), "line": line, "detail": detail})
    return out


def coverage(key: str) -> dict | None:
    path = RESULTS / f"coverage-{key}.json"
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    base = SUITES[key][2]
    files = []
    for name, f in data["files"].items():
        s = f["summary"]
        full = (Path(name) if Path(name).is_absolute() else base / name).resolve()
        files.append({"file": _where(full), "abs": str(full), "statements": s["num_statements"], "covered": s["covered_lines"],
                      "missing": s["missing_lines"], "linePercent": _p(s["covered_lines"], s["num_statements"]),
                      "branches": s.get("num_branches", 0), "branchesCovered": s.get("covered_branches", 0),
                      "branchPercent": _p(s.get("covered_branches", 0), s.get("num_branches", 0)),
                      "percent": round(s["percent_covered"], 1), "missingLines": f.get("missing_lines", []),
                      "missingBranches": f.get("missing_branches", [])})
    t = data["totals"]
    return {"percent": round(t["percent_covered"], 1), "statements": t["num_statements"], "covered": t["covered_lines"],
            "linePercent": _p(t["covered_lines"], t["num_statements"]), "branches": t.get("num_branches", 0),
            "branchesCovered": t.get("covered_branches", 0), "branchPercent": _p(t.get("covered_branches", 0), t.get("num_branches", 0)),
            "full": sum(1 for f in files if f["percent"] == 100), "files": sorted(files, key=lambda x: x["file"])}


def _p(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 100.0


def locate(file: str, symbol: str) -> dict:
    """The line of a symbol in a source file, with the code around it (so the dashboard shows the fix itself)."""
    path = ROOT / file
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return {"file": file, "symbol": symbol, "line": 0, "found": False, "code": "", "abs": str(path)}
    at = next((i for i, line in enumerate(lines) if symbol in line), None)
    if at is None:
        return {"file": file, "symbol": symbol, "line": 0, "found": False, "code": "", "abs": str(path)}
    indent = len(lines[at]) - len(lines[at].lstrip())
    end = at + 1
    while end < len(lines) and end - at < 36:  # the block that starts at the symbol: until the indentation falls back
        text = lines[end]
        if text.strip() and len(text) - len(text.lstrip()) <= indent and not text.lstrip().startswith((")", "}", "]")) and end - at > 2:
            break
        end += 1
    return {"file": file, "symbol": symbol, "line": at + 1, "found": True, "code": "\n".join(lines[at:end]).rstrip(), "abs": str(path)}


def _journeys() -> list[dict]:
    """Every journey per language as last recorded: verified, out of date (the screen changed) or never verified, with its
    steps and screenshots (paths as the dashboard reaches them) and, after a failure, the screen at that moment."""
    out = []
    for path in sorted((RESULTS / "journeys").glob("*/*/journey.json")):
        doc = json.loads(path.read_text())
        base = f"../results/journeys/{doc['id']}/{doc['lang']}/"
        failure = RESULTS / "journeys-run" / doc["id"] / doc["lang"] / "failure.png"
        doc.update(base=base, failure=f"../results/journeys-run/{doc['id']}/{doc['lang']}/failure.png" if doc["status"] != "verified" and failure.exists() else None)
        out.append(doc)
    return sorted(out, key=lambda d: (("beginner", "professional", "advanced", "architect").index(d["level"]), d["order"], d["id"], d["lang"]))


def _capabilities(by_ref: dict[str, list[dict]], threats: dict, journeys: list[dict] | None = None) -> list[dict]:
    """Each capability with the tests that exercised it (and their result), the journeys that document it and the threats
    that apply to it. An empty column is visible on purpose."""
    import fnmatch

    path = RESULTS / "capabilities.json"
    if not path.exists():
        return []
    documenting: dict[str, dict[str, set[str]]] = {}  # capability -> journey -> statuses (per language)
    for j in journeys or []:
        for cap_id in j.get("capabilities", []):
            documenting.setdefault(cap_id, {}).setdefault(j["id"], set()).add(j["status"])
    out = []
    for cap in json.loads(path.read_text()):
        tests = [t for ref in cap["tests"] for t in by_ref.get(ref, [])]
        docs = documenting.get(cap["id"], {})
        statuses = set().union(*docs.values()) if docs else set()
        failed = [t["id"] for t in tests if t["status"] == "failed"]
        applying = [x["id"] for b in threats.get("boundaries", []) for x in b["threats"]
                    if any(fnmatch.fnmatch(cap["id"], pattern) for pattern in x.get("applies", []))]
        out.append({**cap, "testCount": len(cap["tests"]), "failed": failed,
                    "tested": "failed" if failed else "passed" if cap["tests"] else "untested",
                    "journeys": sorted(docs), "threats": applying,
                    "documented": "missing" if not docs else "passed" if statuses == {"verified"} else "failed"})
    return out


def _steps() -> list[dict]:
    """The steps of the last run with their logs: steps.json as a list, or steps.jsonl plus each step's log."""
    listed = json.loads((RESULTS / "steps.json").read_text()) if (RESULTS / "steps.json").exists() else []
    if isinstance(listed, list):
        return listed
    lines = (RESULTS / "steps.jsonl").read_text().splitlines() if (RESULTS / "steps.jsonl").exists() else []
    steps = [json.loads(line) for line in lines if line.strip()]
    for s in steps:
        log = RESULTS / f"{s['key']}.log"
        s.setdefault("log", log.read_text(errors="replace")[-20000:] if log.exists() else "")
    return steps


def _product() -> dict:
    """What the page needs to name this product: from suites.json, plus the Claude sessions when they were built."""
    out = {k: CONFIG[k] for k in ("product", "monogram", "texts")}
    out.update(coverageKeys=COVERAGE, unitSuites=[k for k in SUITES if k not in SPECIAL])
    summary = RESULTS / "sessions" / "summary.json"
    if summary.exists():
        out["sessions"] = {"href": "../results/sessions/index.html", **json.loads(summary.read_text())}
    return out


def _backlog() -> dict | None:
    """The backlog for the board, read by the crissp tool itself (crissp/tool/server.py: one parser, never a second):
    every epic with its features and their PBIs, and the PBIs from before features. None without the tool."""
    if not TOOL.exists():
        return None
    spec = importlib.util.spec_from_file_location("crissp_for_the_board", TOOL)
    crissp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(crissp)
    features, items = crissp.features(ROOT), crissp.items(ROOT)
    for i in items:  # a PBI an approved UX design became links back to it
        mark = UX_MARK.search(i["block"])
        if mark:
            i["ux"] = mark.group(1)
    epics = []
    for f in crissp.epic_files(ROOT):
        m = crissp.EPIC.search(crissp.read(f))
        if not m:
            continue
        epic = m.group(1)
        epics.append({"id": epic, "title": m.group(2).strip(), "file": str(f.relative_to(ROOT)), "done": f.parent.name == "done",
                      "features": [{**ft, "pbis": [i for i in items if i["id"].startswith(ft["id"] + "-")]}
                                   for ft in features if ft["id"].startswith(epic + "-F")],
                      "items": [i for i in items if re.fullmatch(rf"{epic}-\d+", i["id"])]})
    return {"epics": epics, "statuses": list(crissp.STATUSES)}


def _ref(ref: str) -> str:
    """A test reference as the results name it: `test_x.py::test_y` and `test_x.py` mean `test_x::test_y` and `test_x`."""
    file, sep, name = ref.partition("::")
    return file.removesuffix(".py") + sep + name


def _status(found: list[dict]) -> str:
    if not found:
        return "missing"
    return "failed" if any(t["status"] == "failed" for t in found) else "passed"


def main(root: Path | None = None) -> int:
    try:
        configure(root or project.root())
    except project.ConfigError as e:
        print(f"dashboard data: {e}", file=sys.stderr)
        return 1
    tests = [t for key in SUITES for t in tests_of(key)]
    by_ref: dict[str, list[dict]] = {}
    for t in tests:
        if t["suite"] == "e2e":
            by_ref.setdefault("e2e:" + t["name"], []).append(t)
        else:
            by_ref.setdefault(t["module"], []).append(t)
            by_ref.setdefault(t["id"], []).append(t)
            if "[" in t["id"]:  # a parametrised test also answers to its base name
                by_ref.setdefault(t["id"].split("[", 1)[0], []).append(t)
    suite = ROOT / "crissp" / "testsuite"
    manifest = json.loads((suite / "changes.json").read_text()) if (suite / "changes.json").exists() else {"changes": []}
    shot_dir = RESULTS / "e2e" / "shots"
    shots = sorted(p.name for p in shot_dir.glob("*.png")) if shot_dir.exists() else []
    changes = []
    for c in manifest["changes"]:
        proof = [{"ref": ref, "tests": [t["id"] for t in by_ref.get(_ref(ref), [])], "status": _status(by_ref.get(_ref(ref), []))}
                 for ref in c["tests"]]
        proof += [{"ref": ref, "tests": [t["id"] for t in by_ref.get("e2e:" + ref, [])], "status": _status(by_ref.get("e2e:" + ref, [])), "e2e": True}
                  for ref in c.get("e2e", [])]
        statuses = {p["status"] for p in proof}
        verdict = "failed" if "failed" in statuses else "missing" if ("missing" in statuses or not proof) else "passed"
        changes.append({**c, "sources": [locate(s["file"], s["symbol"]) for s in c["sources"]], "proof": proof, "verdict": verdict,
                        "screenshots": [s + ".png" for s in c.get("screenshots", []) if s + ".png" in shots]})
    steps = _steps()
    gate = json.loads((RESULTS / "gate.json").read_text()) if (RESULTS / "gate.json").exists() else None
    threats = json.loads((suite / "threats.json").read_text()) if (suite / "threats.json").exists() else {"boundaries": []}
    for boundary in threats["boundaries"]:
        for threat in boundary["threats"]:
            proof = [{"ref": ref, "tests": [x["id"] for x in by_ref.get(ref, [])], "status": _status(by_ref.get(ref, []))} for ref in threat["tests"]]
            statuses = {p["status"] for p in proof}
            threat["proof"] = proof
            threat["status"] = ("untested" if not proof else "failed" if "failed" in statuses else "missing" if "missing" in statuses else "passed")

    def summary(k: str) -> dict:
        mine = [t for t in tests if t["suite"] == k]
        return {"label": SUITES[k][0], "tests": len(mine), "passed": sum(t["status"] == "passed" for t in mine),
                "failed": sum(t["status"] == "failed" for t in mine), "skipped": sum(t["status"] == "skipped" for t in mine),
                "time": round(sum(t["time"] for t in mine), 1)}

    journeys = _journeys()
    capabilities = _capabilities(by_ref, threats, journeys)
    data = {"generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "root": str(ROOT), "steps": steps, "suites": {k: summary(k) for k in SUITES},
            "tests": tests, "coverage": {k: coverage(k) for k in COVERAGE}, "changes": changes, "gaps": manifest.get("gaps", []), "gate": gate, "threats": threats, "capabilities": capabilities,
            "journeys": journeys, "screenshots": shots, "backlog": _backlog(), **_product()}
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "data.js").write_text("window.SUITE = " + json.dumps(data, ensure_ascii=False).replace("</", "<\\/") + ";\n")
    failed = sum(t["status"] == "failed" for t in tests) + sum(s.get("status") == "failed" for s in steps)
    unresolved = [f"{c['id']}: {s['file']} · {s['symbol']}" for c in changes for s in c["sources"] if not s["found"]]
    print(f"dashboard data: {len(tests)} tests, {len(changes)} changes, {failed} failures")
    for u in unresolved:
        print("  source not found:", u)
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script by crissp/test.sh; main() is tested
    sys.exit(main())
