"""Every dependency and every image CVE-tested: what blocks a release, and what is accepted for a while.

The audit step runs the scanners the project names (crissp/testsuite/suites.json, audit) and decides from their JSON
(never from their exit codes):
- pip        requirements files, resolved with every transitive package, then pip-audit (PyPI advisories, OSV). PyPI
             gives no severity, so every finding blocks. `python`: the Python they are resolved for (default 3.14).
- npm        folders with a package-lock.json: npm audit, every package. High and critical block; the rest is listed.
- missing    "skip": a place that is not there (yet) is listed as absent, not a problem (the template names the
             default places, D-02); otherwise a missing place is a problem.
- fs         folders whose lock files trivy fs scans; config: what trivy config checks (a chart, Terraform), together
             with the `dockerfiles` (globs); images: files whose image: lines name images (a compose file, chart
             values), scanned with trivy image together with every Dockerfile's FROM. own_images: {values, parts} the
             chart's own images, named as not scanned yet (they need a build). High and critical block when a fix
             exists (vulnerabilities) or the check fails (misconfigurations); the rest is listed.
trivy is the pinned one (lib/tools.py), never whatever a machine has on its PATH. A scanner that cannot run is a
problem, never a pass. crissp/testsuite/accepted-risks.json accepts a finding for at most
90 days, with why and by whom; an expired or incomplete acceptance is a problem and accepts nothing.

The secrets scan is the pinned gitleaks (lib/tools.py) over the git history, or over the files when there is no git.
It says where a secret is, never what it is (redacted, and the value is never read). The project's own gitleaks
configuration counts, as gitleaks reads it: .gitleaks.toml, .gitleaksignore (fingerprints) and gitleaks:allow.

SAST is the pinned Semgrep, offline (metrics off, no registry), with crissp's rules (crissp/testsuite/sast: Python,
JavaScript, TypeScript, JSX) and the rules folders the project names (sast_rules), on the code it names (sast). An
ERROR blocks; a WARNING is listed for review. The project's .semgrepignore counts.

    python3 crissp/testsuite/lib/audit.py run       scan, write crissp/testsuite/results/audit.json, exit 1 when anything blocks
    python3 crissp/testsuite/lib/audit.py secrets   the git history, into results/secrets.json, exit 1 on a secret
    python3 crissp/testsuite/lib/audit.py sast      the code (audit.sast), into results/sast.json, exit 1 on an ERROR
    python3 crissp/testsuite/lib/audit.py rules     crissp's Semgrep rules against their own tests (sast/tests)
"""

import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project
import tools

BLOCKING = ("CRITICAL", "HIGH")
MAX_DAYS = 90
NEEDED = ("id", "package", "why", "by", "since", "until")
PIP_AUDIT = "pip-audit==2.10.1"
SEMGREP = "semgrep==1.185.0"  # SAST, run offline with crissp's own rules (never the registry, metrics off)
RULES = Path(__file__).resolve().parents[1] / "sast"  # crissp's Semgrep rules, with their tests in sast/tests
PYTHON = "3.14"  # what pip-audit resolves for, unless the project names another


def binary(name: str) -> str:
    """The pinned scanner (lib/tools.py): fetched once, checksum-checked, never the one on the PATH."""
    return str(tools.ensure(name, dict(os.environ)))


def today() -> datetime.date:
    return datetime.date.today()


def runner(argv: list[str], cwd: Path) -> tuple[int, str, str]:
    try:
        done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=900, check=False)
    except FileNotFoundError:
        return 127, "", f"{argv[0]} is not installed"
    return done.returncode, done.stdout, done.stderr


def _finding(source, target, package, installed, id_, severity, fixed, title, blocks, aliases=()) -> dict:
    return {"source": source, "target": target, "package": package, "installed": installed, "id": id_,
            "aliases": list(aliases), "severity": severity, "fixed": fixed, "title": title, "blocks": blocks}


def from_pip_audit(data: dict, target: str) -> list[dict]:
    out, seen = [], set()
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            if (dep["name"], v["id"]) in seen:  # pip-audit can report one advisory twice
                continue
            seen.add((dep["name"], v["id"]))
            out.append(_finding("pip-audit", target, dep["name"], dep["version"], v["id"], "UNKNOWN",
                                ", ".join(v.get("fix_versions", [])) or "no fix",
                                (v.get("description") or "").splitlines()[0][:160], True, v.get("aliases", [])))
    return out


def from_npm_audit(data: dict, target: str) -> list[dict]:
    out = []
    for name, vuln in sorted(data.get("vulnerabilities", {}).items()):
        for via in vuln.get("via", []):
            if not isinstance(via, dict):  # only points at another package's advisory: counted there
                continue
            severity = via.get("severity", vuln.get("severity", "")).upper().replace("MODERATE", "MEDIUM")
            out.append(_finding("npm audit", target, name, vuln.get("range", ""), via["url"].rsplit("/", 1)[-1],
                                severity, "fix available" if vuln.get("fixAvailable") else "no fix",
                                via.get("title", ""), severity in BLOCKING))
    return out


def from_trivy(data: dict, target: str) -> list[dict]:
    out = []
    for result in data.get("Results") or []:
        for v in result.get("Vulnerabilities") or []:
            fixed = v.get("FixedVersion") or ""
            out.append(_finding("trivy", target, v["PkgName"], v.get("InstalledVersion", ""), v["VulnerabilityID"],
                                v["Severity"], fixed or "no fix", v.get("Title", ""),
                                v["Severity"] in BLOCKING and bool(fixed)))
        for m in result.get("Misconfigurations") or []:
            if m.get("Status") == "FAIL":
                out.append(_finding("trivy", target, result["Target"], "", m["ID"], m["Severity"], "change the config",
                                    m.get("Title", ""), m["Severity"] in BLOCKING))
    return out


def _date(text: str) -> datetime.date:
    return datetime.date.fromisoformat(text)


def apply_accepted(findings: list[dict], accepted: dict, on: datetime.date) -> tuple[list[dict], list[str]]:
    valid, problems = [], []
    for r in accepted.get("accepted", []):
        name = f"accepted risk {r.get('id', '?')} ({r.get('package', '?')})"
        if not all(str(r.get(k) or "").strip() for k in NEEDED):
            problems.append(f"{name} needs id, package, why, by, since and until")
            continue
        try:
            since, until = _date(r["since"]), _date(r["until"])
        except ValueError:
            problems.append(f"{name}: dates are YYYY-MM-DD")
            continue
        if until < since:
            problems.append(f"{name} ends before it starts")
        elif (until - since).days > MAX_DAYS:
            problems.append(f"{name}: an acceptance lasts at most {MAX_DAYS} days")
        elif until < on:
            problems.append(f"{name} expired on {until}: fix it or accept it again")
        else:
            valid.append(r)
    out = []
    for f in findings:
        hit = next((r for r in valid if r["package"] == f["package"] and r["id"] in (f["id"], *f["aliases"])), None)
        out.append({**f, "blocks": False, "accepted": f"{hit['by']} until {hit['until']}: {hit['why']}"} if hit else f)
    return out, problems


_FROM = re.compile(r"^FROM\s+(?:--platform=\S+\s+)?(\S+)(?:\s+AS\s+(\S+))?", re.IGNORECASE | re.MULTILINE)
_IMAGE = re.compile(r"^[ \t]*image:[ \t]*[\"']?([^\s\"'#{]+)", re.MULTILINE)  # on one line: never a block's first key
_OWN = re.compile(r"^image:\n\s+repository:\s*(\S+).*\n\s+version:\s*[\"']?([^\"'\s]+)", re.MULTILINE)


def dockerfiles(root: Path, conf: dict) -> list[Path]:
    """The Dockerfiles the audit names (globs relative to the project, e.g. app/*/Dockerfile)."""
    return sorted({p for pattern in conf.get("dockerfiles", []) for p in root.glob(pattern) if p.is_file()})


def images(root: Path, conf: dict) -> list[str]:
    """Every image the Dockerfiles (FROM) and the listed files (compose files, chart values: image:) name."""
    found: set[str] = set()
    for dockerfile in dockerfiles(root, conf):
        stages: set[str] = set()
        for image, alias in _FROM.findall(dockerfile.read_text()):
            if image not in stages and image != "scratch":
                found.add(image)
            if alias:
                stages.add(alias)
    for name in conf.get("images", []):
        path = root / name
        if path.is_file():
            found.update(_IMAGE.findall(path.read_text()))
    return sorted(found)


def own_images(root: Path, conf: dict) -> list[str]:
    """The chart's own images (image.repository, one tag per part): built here, so only a built-image scan sees them."""
    own = conf.get("own_images") or {}
    values = root / own["values"] if own.get("values") else None
    found = _OWN.findall(values.read_text()) if values and values.is_file() else []
    return sorted(f"{repo}:{part}-{version}" for repo, version in found for part in own.get("parts", []))


def _scanner(run, findings: list, problems: list, scanned: list):
    """scan(label, argv, cwd, parse, target): run one scanner, its JSON parsed into findings, or a problem."""
    def scan(label: str, argv: list[str], cwd: Path, parse, target: str) -> None:
        code, out, err = run(argv, cwd)
        try:
            data = json.loads(out)
        except ValueError:
            problems.append(f"{label} could not run (exit {code}): {(err or out).strip()[-300:]}")
            return
        findings.extend(parse(data, target))
        scanned.append(label)
    return scan


def _report(kind: str, on: datetime.date, scanned: list, problems: list, findings: list, accepted: dict,
            **more) -> dict:
    findings, invalid = apply_accepted(findings, accepted, on)
    return {"kind": kind, "date": on.isoformat(), "scanned": scanned, "not_scanned": [], "absent": [], **more,
            "problems": problems + invalid, "findings": findings, "blocking": [f for f in findings if f["blocks"]]}


def run_all(root: Path, run, on: datetime.date, accepted: dict, conf: dict) -> dict:
    """Every scan the project's audit configuration names (suites.json, audit), and what they found."""
    findings, problems, scanned = [], [], []
    scan = _scanner(run, findings, problems, scanned)

    skip = conf.get("missing") == "skip"
    absent: list[str] = []

    def there(label: str, path: str) -> bool:
        """A place the audit names: there, or listed as absent (missing: skip), or a problem."""
        if (root / path).exists():
            return True
        if skip:
            absent.append(path)
        else:
            problems.append(f"{label}: {path} is not there")
        return False

    python = str(conf.get("python") or PYTHON)
    for req in [r for r in conf.get("pip", []) if there(f"pip-audit {r}", r)]:
        # resolved first (every transitive package, pinned), then audited as is: no throwaway environment, no pip run
        with tempfile.TemporaryDirectory(prefix="audit-") as tmp:
            resolved = str(Path(tmp) / "resolved.txt")
            code, _, err = run(["uv", "pip", "compile", "--quiet", "--python-version", python, req, "-o", resolved], root)
            if code != 0:
                problems.append(f"pip-audit {req}: could not resolve the requirements (exit {code}): {err.strip()[-300:]}")
                continue
            scan(f"pip-audit {req}", ["uv", "run", "--quiet", "--no-project", "--with", PIP_AUDIT, "pip-audit", "-r",
                                      resolved, "--no-deps", "--disable-pip", "--format", "json",
                                      "--progress-spinner", "off"], root, from_pip_audit, str(Path(req).parent))
    for app in conf.get("npm", []):
        if (root / app / "package-lock.json").is_file():
            scan(f"npm audit {app}", ["npm", "audit", "--json"], root / app, from_npm_audit, app)
        elif skip:
            absent.append(f"{app}/package-lock.json")
        else:
            problems.append(f"npm audit {app}: no package-lock.json to audit")
    fs = [a for a in conf.get("fs", []) if there(f"trivy fs {a}", a)]
    configs = [*(str(p.relative_to(root)) for p in dockerfiles(root, conf)),
               *(c for c in conf.get("config", []) if there(f"trivy config {c}", c))]
    found_images = images(root, conf)
    trivy_bin = None
    if fs or configs or found_images:
        try:
            trivy_bin = binary("trivy")
        except tools.ToolError as e:
            problems.append(f"trivy: {e}")

    def trivy(sub: str) -> list[str]:
        return [trivy_bin, sub, "--quiet"]

    for app in fs if trivy_bin else []:
        scan(f"trivy fs {app}", [*trivy("fs"), "--scanners", "vuln", "--format", "json", app], root, from_trivy, app)
    for target in configs if trivy_bin else []:
        scan(f"trivy config {target}", [*trivy("config"), "--format", "json", target], root, from_trivy, target)
    for image in found_images if trivy_bin else []:
        scan(f"trivy image {image}", [*trivy("image"), "--format", "json", image], root, from_trivy, f"image {image}")
    if not skip and not any(conf.get(k) for k in ("pip", "npm", "fs", "config", "dockerfiles", "images")):
        problems.append("nothing to audit: name what to scan in crissp/testsuite/suites.json (audit)")
    return _report("audit", on, scanned, problems, findings, accepted, not_scanned=own_images(root, conf),
                   absent=absent)


def from_gitleaks(data: list, target: str) -> list[dict]:
    """Where a secret is, never what it is: the Secret and Match fields are not read."""
    out = []
    for leak in data or []:
        commit = (leak.get("Commit") or "")[:12]
        where = f"line {leak['StartLine']}" + (f" in {commit}" if commit else "")
        out.append({**_finding("gitleaks", target, leak["File"], where, leak["RuleID"], "HIGH",
                               "rotate it, then remove it from the history", leak.get("Description", ""), True),
                    "fingerprint": leak.get("Fingerprint", "")})
    return out


def secrets_all(root: Path, run, on: datetime.date, accepted: dict) -> dict:
    """The pinned gitleaks over the git history (over the files when there is no git). The project's own gitleaks
    configuration counts as gitleaks reads it: .gitleaks.toml, .gitleaksignore, gitleaks:allow."""
    findings, problems, scanned = [], [], []
    scan = _scanner(run, findings, problems, scanned)
    try:
        gitleaks = binary("gitleaks")
    except tools.ToolError as e:
        problems.append(f"gitleaks: {e}")
    else:
        history = (root / ".git").exists()
        scan("gitleaks git history" if history else "gitleaks files",
             [gitleaks, "git" if history else "dir", "--no-banner", "--redact", "--report-format", "json",
              "--report-path", "-", "--exit-code", "0", "--log-level", "warn", "."], root, from_gitleaks,
             "git history" if history else "files")
    return _report("secrets", on, scanned, problems, findings, accepted)


NOT_GREEN = {
    "audit": "Not green: update the package or image to the fixed version, or accept it for a while with a reason in "
             "crissp/testsuite/accepted-risks.json (at most 90 days).",
    "secrets": "Not green: a secret in git has leaked. Rotate it first, then remove it from the history. A finding that "
               "is no secret is allowed in .gitleaks.toml by its file and value ([[allowlists]], with a description "
               "saying why), never by its commit: a .gitleaksignore fingerprint misses in a shallow clone.",
    "sast": "Not green: change the code (each finding says why), or accept it for a while with a reason in "
            "crissp/testsuite/accepted-risks.json (at most 90 days).",
}


SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM"}


def from_semgrep(data: dict, target: str) -> list[dict]:
    """A finding names the file, the line, the rule and why; never the code it matched."""
    return [_finding("semgrep", target, r["path"], f"line {r['start']['line']}", r["check_id"].rsplit(".", 1)[-1],
                     SEVERITY.get(r["extra"]["severity"], "LOW"), "change the code", r["extra"].get("message", ""),
                     r["extra"]["severity"] == "ERROR")
            for r in data.get("results", [])]


def semgrep(*args: str) -> list[str]:
    return ["uv", "run", "--quiet", "--no-project", "--with", SEMGREP, "semgrep", *args]


def sast_all(root: Path, run, on: datetime.date, accepted: dict, conf: dict) -> dict:
    """The pinned Semgrep, offline, with crissp's rules and the project's own (audit.sast_rules), on the code the
    project names (audit.sast). The project's .semgrepignore counts; without one, Semgrep's defaults apply."""
    findings, problems, scanned, absent = [], [], [], []
    skip = conf.get("missing") == "skip"
    paths, own = [], []
    for path in conf.get("sast", []):
        if (root / path).exists():
            paths.append(path)
        elif skip:
            absent.append(path)
        else:
            problems.append(f"semgrep: {path} is not there")
    for rules in conf.get("sast_rules", []):
        if (root / rules).exists():
            own.append(rules)
        elif skip:
            absent.append(rules)
        else:
            problems.append(f"semgrep: no rules at {rules}")

    def parse(data: dict, target: str) -> list[dict]:
        problems.extend(f"semgrep: {e.get('type')}: {e.get('message', '')}".strip() for e in data.get("errors", [])
                        if e.get("level") == "error")
        return from_semgrep(data, target)

    if paths:
        configs = [x for rules in (str(RULES), *own) for x in ("--config", rules)]
        _scanner(run, findings, problems, scanned)(
            f"semgrep {' '.join(paths)}", semgrep("scan", *configs, "--json", "--metrics", "off",
                                                  "--disable-version-check", "--quiet", *paths), root, parse, "code")
    elif not conf.get("sast") and not skip:
        problems.append("nothing to scan: name the code in crissp/testsuite/suites.json (audit, sast)")
    return _report("sast", on, scanned, problems, findings, accepted, absent=absent)


def rules_test(root: Path, run) -> tuple[int, str]:
    """crissp's rules against their own tests (sast/tests): each must match what it should and leave the rest."""
    code, out, err = run(semgrep("--test", "--metrics", "off", "--config", str(RULES), str(RULES / "tests")), root)
    return code, (out + err).strip()


def render(report: dict) -> str:
    lines = [f"Scanned: {len(report['scanned'])} — " + "; ".join(report["scanned"])]
    for image in report["not_scanned"]:
        lines.append(f"note     not scanned yet (needs a Docker build): {image} — its base image and its dependencies are scanned above")
    for path in report.get("absent", []):
        lines.append(f"note     not there yet, not scanned: {path}")
    for p in report["problems"]:
        lines.append(f"PROBLEM  {p}")
    kind = report.get("kind", "audit")
    fix = "fixed in " if kind == "audit" else ""
    for f in report["blocking"]:
        lines.append(f"BLOCKING {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): "
                     f"{f['title']} — {fix}{f['fixed']}")
    listed = [f for f in report["findings"] if not f["blocks"]]
    for f in listed:
        note = f"accepted: {f['accepted']}" if f.get("accepted") else f"{fix}{f['fixed']}"
        lines.append(f"listed   {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): {note}")
    if report["blocking"] or report["problems"]:
        lines.append(NOT_GREEN[kind])
    elif kind == "secrets":
        lines.append("No secret found.")
    elif not report["scanned"]:
        lines.append(f"Nothing to {'scan' if kind == 'sast' else 'audit'} yet: none of the places suites.json names is here.")
    elif kind == "sast":
        lines.append(f"No unsafe code blocks ({len(listed)} listed for review).")
    else:
        lines.append(f"No known vulnerability blocks ({len(listed)} listed).")
    return "\n".join(lines)


SCANS = {"run": "audit", "secrets": "secrets", "sast": "sast", "rules": None}


def main(argv: list[str], root: Path | None = None) -> int:
    if len(argv) != 2 or argv[1] not in SCANS:
        print(__doc__, file=sys.stderr)
        return 2
    root = root or project.root()
    if argv[1] == "rules":  # the engine's own rules: no project needed
        code, said = rules_test(root, runner)
        print(said)
        return 0 if code == 0 else 1
    try:
        conf = project.load(root)["audit"] or {}
    except project.ConfigError as e:
        print(f"audit: {e}", file=sys.stderr)
        return 2
    risks = root / "crissp/testsuite/accepted-risks.json"
    accepted = json.loads(risks.read_text()) if risks.is_file() else {"accepted": []}
    if argv[1] == "secrets":
        report = secrets_all(root, runner, today(), accepted)
    elif argv[1] == "sast":
        report = sast_all(root, runner, today(), accepted, conf)
    else:
        report = run_all(root, runner, today(), accepted, conf)
    results = project.results(root)
    results.mkdir(parents=True, exist_ok=True)
    (results / f"{SCANS[argv[1]]}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(render(report))
    return 1 if report["blocking"] or report["problems"] else 0


if __name__ == "__main__":  # pragma: no cover — run by the audit step; main() is tested
    sys.exit(main(sys.argv))
