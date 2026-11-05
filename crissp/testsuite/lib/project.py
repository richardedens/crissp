"""The project the testsuite works for, and what its parts are: one configuration, read by every guard.

The project is CRISSP_ROOT, or the current directory (crissp/check.sh, check-all.sh, test.sh and run.sh export
CRISSP_ROOT); never the place of this file, so the engine and a project's data may live apart. The configuration is
the project's crissp/testsuite/suites.json:

    product      the product's name (default: the folder's name); monogram: one or two letters for the top bar
    steps        [{key, label, dir, run, seconds, coverage, gate, sources, omit, fail_under, tests, full_only, when}]
                 the suites of a run, in the order they run:
                   key        a short name (letters, digits, -): the step's log is results/<key>.log
                   label      what the run prints and the dashboard shows
                   dir        where the command runs, relative to the project (default ".")
                   run        the command (bash). It gets CRISSP_ROOT, RESULTS, STEP, JUNIT (results/<key>.xml),
                              COVERAGE_JSON (results/coverage-<key>.json), COVERAGE_FILE, TOOLS (the pinned test tools)
                              and the helper `covered <pytest arguments>`: pytest under coverage (lines and branches)
                              of `sources`, with the JUnit XML and the coverage JSON where the dashboard and the gate read
                              them (lib/steps.sh)
                   seconds    roughly how long it takes (crissp/check.sh --plan adds them up; default 10)
                   coverage   the step measures coverage (the dashboard shows it); gate: the coverage gate holds it
                   sources    what coverage measures, relative to the project; omit: patterns it leaves out;
                              fail_under: the step is red below this total (e.g. 100)
                   tests      where its test files are, for the dashboard (default: <dir>/tests)
                   full_only  only in the full run (a build, a browser check); when: the step exists only while this
                              path does (e.g. a script another part delivers)
                 The coverage gate (lib/gate.py) is a step of its own, `gate`, right after the last gated step.
    paths        [{match, steps}] what crissp/check.sh runs when a file changes (lib/impact.py): an exact path, a folder
                 ("…/") or a file name anywhere ("*/name"); the first rule that matches decides
    shared       [{match, why}] the product's shared ground: a change there needs the full run
    notes        [prefix] what needs no test besides Markdown, the backlog and docs/
    setup        {venvs: [dir], npm: [dir], needs: [{command, hint}]} what lib/setup_plan.py installs or asks for
    audit        {pip, npm, fs, config, dockerfiles, images, own_images, python} what lib/audit.py scans
    texts        the dashboard's texts for the product (e2e, journeys)

    python3 crissp/testsuite/lib/project.py check     say what is wrong with the configuration (exit 1), or that it is fine
"""

import json
import os
import re
import sys
from pathlib import Path

CONFIG = Path("crissp/testsuite/suites.json")
KEY = re.compile(r"[a-z0-9][a-z0-9-]{0,31}")
GATE = "gate"
GATE_LABEL = "Coverage gate (may only go up)"
STEP_KEYS = {"key", "label", "dir", "run", "seconds", "coverage", "gate", "sources", "omit", "fail_under", "tests",
             "full_only", "when"}
TOP_KEYS = {"product", "monogram", "steps", "paths", "shared", "notes", "setup", "audit", "texts", "$comment"}


class ConfigError(ValueError):
    """The configuration is wrong; the message says where and what."""


def root(env=None) -> Path:
    """The project: CRISSP_ROOT, or the current directory."""
    env = os.environ if env is None else env
    return Path(env.get("CRISSP_ROOT") or os.getcwd()).resolve()


def results(project: Path) -> Path:
    return project / "crissp" / "testsuite" / "results"


def _texts(value, where: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x.strip() for x in value):
        raise ConfigError(f"{where} must be a list of texts")
    return [x.strip() for x in value]


def _step(raw, n: int) -> dict:
    where = f"suites.json: steps[{n}]"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be an object")
    unknown = sorted(set(raw) - STEP_KEYS)
    if unknown:
        raise ConfigError(f"{where}: unknown field(s) {', '.join(unknown)}")
    key = raw.get("key")
    if not isinstance(key, str) or not KEY.fullmatch(key) or key == GATE:
        raise ConfigError(f"{where}: key must be a short name of letters, digits and - (not {GATE!r})")
    where = f"suites.json: step {key}"
    for field in ("label", "run"):
        if not isinstance(raw.get(field), str) or not raw[field].strip():
            raise ConfigError(f"{where}: {field} must be a text")
    seconds = raw.get("seconds", 10)
    if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 1:
        raise ConfigError(f"{where}: seconds must be a whole number of at least 1")
    fail_under = raw.get("fail_under")
    if fail_under is not None and (not isinstance(fail_under, (int, float)) or isinstance(fail_under, bool)
                                   or not 0 <= fail_under <= 100):
        raise ConfigError(f"{where}: fail_under must be a percentage from 0 to 100")
    for flag in ("coverage", "gate", "full_only"):
        if not isinstance(raw.get(flag, False), bool):
            raise ConfigError(f"{where}: {flag} must be true or false")
    step = {"key": key, "label": raw["label"].strip(), "dir": str(raw.get("dir") or "."), "run": raw["run"].strip(),
            "seconds": seconds, "gate": raw.get("gate", False), "full_only": raw.get("full_only", False),
            "sources": _texts(raw.get("sources", []), f"{where}: sources"),
            "omit": _texts(raw.get("omit", []), f"{where}: omit"), "fail_under": fail_under,
            "when": raw.get("when") if isinstance(raw.get("when"), str) else None}
    step["coverage"] = raw.get("coverage", False) or step["gate"]
    if step["coverage"] and not step["sources"]:
        raise ConfigError(f"{where}: a step that measures coverage names its sources")
    step["tests"] = _texts(raw["tests"], f"{where}: tests") if "tests" in raw else [f"{step['dir'].rstrip('/')}/tests"]
    return step


def _rules(value, where: str, field: str) -> list[dict]:
    if not isinstance(value, list):
        raise ConfigError(f"suites.json: {where} must be a list")
    out = []
    for n, rule in enumerate(value):
        if not isinstance(rule, dict) or not isinstance(rule.get("match"), str) or not rule["match"].strip():
            raise ConfigError(f"suites.json: {where}[{n}] needs a match (a path, a folder/ or */name)")
        out.append({"match": rule["match"].strip(), field: rule.get(field)})
    return out


def parse(data) -> dict:
    """The configuration checked, with every default filled in; raises ConfigError with what is wrong."""
    if not isinstance(data, dict):
        raise ConfigError("suites.json must hold one JSON object")
    unknown = sorted(set(data) - TOP_KEYS)
    if unknown:
        raise ConfigError(f"suites.json: unknown field(s) {', '.join(unknown)}")
    steps = [_step(raw, n) for n, raw in enumerate(data.get("steps", []))] if isinstance(data.get("steps", []), list) \
        else None
    if steps is None:
        raise ConfigError("suites.json: steps must be a list")
    keys = [s["key"] for s in steps]
    doubled = sorted({k for k in keys if keys.count(k) > 1})
    if doubled:
        raise ConfigError(f"suites.json: step {', '.join(doubled)} is named twice")
    paths = _rules(data.get("paths", []), "paths", "steps")
    for rule in paths:
        named = rule["steps"]
        if not isinstance(named, list) or not named or not all(isinstance(k, str) for k in named):
            raise ConfigError(f"suites.json: paths {rule['match']}: steps must name at least one step")
        unknown = [k for k in named if k not in keys]
        if unknown:
            raise ConfigError(f"suites.json: paths {rule['match']}: unknown step {', '.join(unknown)}")
    shared = _rules(data.get("shared", []), "shared", "why")
    for rule in shared:
        if not isinstance(rule["why"], str) or not rule["why"].strip():
            raise ConfigError(f"suites.json: shared {rule['match']}: why must say why a change there needs the full run")
    setup = data.get("setup", {})
    if not isinstance(setup, dict):
        raise ConfigError("suites.json: setup must be an object")
    needs = setup.get("needs", [])
    if not isinstance(needs, list) or not all(isinstance(x, dict) and isinstance(x.get("command"), str)
                                              and isinstance(x.get("hint"), str) for x in needs):
        raise ConfigError("suites.json: setup.needs must be a list of {command, hint}")
    audit = data.get("audit")
    if audit is not None and not isinstance(audit, dict):
        raise ConfigError("suites.json: audit must be an object")
    texts = data.get("texts", {})
    if not isinstance(texts, dict):
        raise ConfigError("suites.json: texts must be an object")
    product = data.get("product")
    return {"product": product.strip() if isinstance(product, str) and product.strip() else None,
            "monogram": data.get("monogram") if isinstance(data.get("monogram"), str) else None,
            "steps": steps, "paths": paths, "shared": shared, "notes": _texts(data.get("notes", []), "suites.json: notes"),
            "setup": {"venvs": _texts(setup.get("venvs", []), "suites.json: setup.venvs"),
                      "npm": _texts(setup.get("npm", []), "suites.json: setup.npm"), "needs": needs},
            "audit": audit, "texts": texts}


def load(project: Path) -> dict:
    """The project's configuration (suites.json), checked; its product named after the folder when it has no name."""
    path = project / CONFIG
    try:
        data = json.loads(path.read_text())
    except OSError:
        raise ConfigError(f"{CONFIG} is missing: describe the product's parts there "
                          "(crissp/template/crissp/testsuite/suites.json is a start)") from None
    except json.JSONDecodeError as e:
        raise ConfigError(f"{CONFIG} is not valid JSON: {e}") from None
    conf = parse(data)
    conf["product"] = conf["product"] or project.name
    conf["monogram"] = conf["monogram"] or conf["product"][:1].upper()
    return conf


def gate_step(gated: list[str]) -> dict:
    return {"key": GATE, "label": GATE_LABEL, "dir": ".", "run": "", "seconds": 2, "gate": False, "coverage": False,
            "full_only": False, "sources": [], "omit": [], "fail_under": None, "tests": [], "when": None,
            "suites": gated}


def steps(conf: dict, project: Path) -> list[dict]:
    """The steps of a full run in their order: the configured ones that exist now (`when`), and the coverage gate right
    after the last gated one."""
    present = [s for s in conf["steps"] if not s["when"] or (project / s["when"]).exists()]
    gated = [s["key"] for s in present if s["gate"]]
    if not gated:
        return present
    last = max(i for i, s in enumerate(present) if s["gate"])
    return present[: last + 1] + [gate_step(gated)] + present[last + 1:]


def main(argv: list[str]) -> int:
    if argv[1:] != ["check"]:
        print(__doc__, file=sys.stderr)
        return 2
    try:
        conf = load(root())
    except ConfigError as e:
        print(e, file=sys.stderr)
        return 1
    print(f"{conf['product']}: " + ", ".join(s["key"] for s in steps(conf, root())))
    return 0


if __name__ == "__main__":  # pragma: no cover — run as a script; main() is tested
    sys.exit(main(sys.argv))
