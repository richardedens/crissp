"""Every dependency and every image CVE-tested: what blocks a release, and what is accepted for a while.

The audit step runs the scanners the project names (crissp/testsuite/suites.json, audit) and decides from their JSON
(never from their exit codes):
- pip        requirements files, resolved with every transitive package, then pip-audit (PyPI advisories, OSV). PyPI
             gives no severity, so every finding blocks. `python`: the Python they are resolved for (default 3.14).
- npm        folders with a package-lock.json: npm audit, every package. High and critical block; the rest is listed.
- fs         folders whose lock files trivy fs scans; config: what trivy config checks (a chart, Terraform), together
             with the `dockerfiles` (globs); images: files whose image: lines name images (a compose file, chart
             values), scanned with trivy image together with every Dockerfile's FROM. own_images: {values, parts} the
             chart's own images, named as not scanned yet (they need a build). High and critical block when a fix
             exists (vulnerabilities) or the check fails (misconfigurations); the rest is listed.
A scanner that cannot run is a problem, never a pass. crissp/testsuite/accepted-risks.json accepts a finding for at most
90 days, with why and by whom; an expired or incomplete acceptance is a problem and accepts nothing.

    python3 crissp/testsuite/lib/audit.py run     scan, write crissp/testsuite/results/audit.json, exit 1 when anything blocks
"""

import datetime
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project  # noqa: E402

BLOCKING = ("CRITICAL", "HIGH")
MAX_DAYS = 90
NEEDED = ("id", "package", "why", "by", "since", "until")
PIP_AUDIT = "pip-audit==2.10.1"
PYTHON = "3.14"  # what pip-audit resolves for, unless the project names another


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


def run_all(root: Path, run, on: datetime.date, accepted: dict, conf: dict) -> dict:
    """Every scan the project's audit configuration names (suites.json, audit), and what they found."""
    findings, problems, scanned = [], [], []

    def scan(label: str, argv: list[str], cwd: Path, parse, target: str) -> None:
        code, out, err = run(argv, cwd)
        try:
            data = json.loads(out)
        except ValueError:
            problems.append(f"{label} could not run (exit {code}): {(err or out).strip()[-300:]}")
            return
        findings.extend(parse(data, target))
        scanned.append(label)

    python = str(conf.get("python") or PYTHON)
    for req in conf.get("pip", []):
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
        else:
            problems.append(f"npm audit {app}: no package-lock.json to audit")

    def trivy(sub: str) -> list[str]:
        return ["trivy", sub, "--quiet"]

    for app in conf.get("fs", []):
        scan(f"trivy fs {app}", [*trivy("fs"), "--scanners", "vuln", "--format", "json", app], root, from_trivy, app)
    for target in [*(str(p.relative_to(root)) for p in dockerfiles(root, conf)), *conf.get("config", [])]:
        scan(f"trivy config {target}", [*trivy("config"), "--format", "json", target], root, from_trivy, target)
    for image in images(root, conf):
        scan(f"trivy image {image}", [*trivy("image"), "--format", "json", image], root, from_trivy, f"image {image}")
    if not any(conf.get(k) for k in ("pip", "npm", "fs", "config", "dockerfiles", "images")):
        problems.append("nothing to audit: name what to scan in crissp/testsuite/suites.json (audit)")
    findings, invalid = apply_accepted(findings, accepted, on)
    return {"date": on.isoformat(), "scanned": scanned, "not_scanned": own_images(root, conf), "problems": problems + invalid,
            "findings": findings,
            "blocking": [f for f in findings if f["blocks"]]}


def render(report: dict) -> str:
    lines = [f"Scanned: {len(report['scanned'])} — " + "; ".join(report["scanned"])]
    for image in report["not_scanned"]:
        lines.append(f"note     not scanned yet (needs a Docker build): {image} — its base image and its dependencies are scanned above")
    for p in report["problems"]:
        lines.append(f"PROBLEM  {p}")
    for f in report["blocking"]:
        lines.append(f"BLOCKING {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): "
                     f"{f['title']} — fixed in {f['fixed']}")
    listed = [f for f in report["findings"] if not f["blocks"]]
    for f in listed:
        note = f"accepted: {f['accepted']}" if f.get("accepted") else f"fixed in {f['fixed']}"
        lines.append(f"listed   {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): {note}")
    if report["blocking"] or report["problems"]:
        lines.append("Not green: update the package or image to the fixed version, or accept it for a while with a "
                     "reason in crissp/testsuite/accepted-risks.json (at most 90 days).")
    else:
        lines.append(f"No known vulnerability blocks ({len(listed)} listed).")
    return "\n".join(lines)


def main(argv: list[str], root: Path | None = None) -> int:
    if argv[1:] != ["run"]:
        print(__doc__, file=sys.stderr)
        return 2
    root = root or project.root()
    try:
        conf = project.load(root)["audit"] or {}
    except project.ConfigError as e:
        print(f"audit: {e}", file=sys.stderr)
        return 2
    risks = root / "crissp/testsuite/accepted-risks.json"
    accepted = json.loads(risks.read_text()) if risks.is_file() else {"accepted": []}
    report = run_all(root, runner, today(), accepted, conf)
    results = project.results(root)
    results.mkdir(parents=True, exist_ok=True)
    (results / "audit.json").write_text(json.dumps(report, indent=1) + "\n")
    print(render(report))
    return 1 if report["blocking"] or report["problems"] else 0


if __name__ == "__main__":  # pragma: no cover — run by the audit step; main() is tested
    sys.exit(main(sys.argv))
