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
ERROR blocks; a WARNING is listed for review. The project's .semgrepignore counts, and so does its .gitignore (Semgrep
reads both); the build folders (lib/sources.py: dist, build, node_modules, …) are always left out, and trivy fs leaves
them out too: their lock files are not the project's (F-150).

DAST is OWASP ZAP (the image pinned by digest) against the app (audit.dast). With a compose file (compose) it starts a
throwaway stack of its own (compose project crissp-dast, built fresh) and removes it afterwards with its volumes, so
nothing the scan does stays; without one it scans the app that runs (targets, the app's local URLs). First a canary: a
page without any security header, served on this machine, on which ZAP must find something, else the scan proves
nothing. Then the baseline (zap-baseline.py: it looks, it never attacks) of every target, and on the throwaway stack:
- signin: first-run setup (setup: {path, body}; "{password}" in a body is a fresh random password), optionally a login,
  and the token from the answer (token, default access_token; header, default Authorization; scheme, default Bearer):
  ZAP sends it on every request (from a private mode-600 env file, never on a command line);
- api: the API scan (zap-api-scan.py, active) of the API definition (definition: its URL; format: openapi, soap or
  graphql).
rules is the project's ZAP rules file, IGNORE/WARN/FAIL per rule. It needs Docker. A high or medium risk blocks unless
accepted (accepted-risks.json: the rule's id and the site), and so does every rule the rules file makes FAIL; low and
informational are listed.

Licences: every package of the pip and npm places above with its licence (from the lock file; for pip from PyPI,
cached), into a CycloneDX SBOM. Forbidden (AGPL, SSPL, BUSL, non-commercial) and copyleft (GPL) licences block,
weak copyleft (LGPL, MPL, EPL) and an unknown licence are listed, a dev-only package is only listed; audit.licenses:
allow ({package: why}, for good), block (more SPDX ids), product (the SBOM's name).

    python3 crissp/testsuite/lib/audit.py run       scan, write crissp/testsuite/results/audit.json, exit 1 when anything blocks
    python3 crissp/testsuite/lib/audit.py secrets   the git history, into results/secrets.json, exit 1 on a secret
    python3 crissp/testsuite/lib/audit.py sast      the code (audit.sast), into results/sast.json, exit 1 on an ERROR
    python3 crissp/testsuite/lib/audit.py dast      the app (audit.dast), into results/dast.json, exit 1 on a high or medium risk
    python3 crissp/testsuite/lib/audit.py licenses  every dependency's licence into results/licenses.json and the SBOM
                                                    into results/sbom.cdx.json, exit 1 on a licence the product may not ship
    python3 crissp/testsuite/lib/audit.py rules     crissp's Semgrep rules against their own tests (sast/tests)
"""

import contextlib
import datetime
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import project
import sources
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
    return {
        "source": source,
        "target": target,
        "package": package,
        "installed": installed,
        "id": id_,
        "aliases": list(aliases),
        "severity": severity,
        "fixed": fixed,
        "title": title,
        "blocks": blocks,
    }


def from_pip_audit(data: dict, target: str) -> list[dict]:
    out, seen = [], set()
    for dep in data.get("dependencies", []):
        for v in dep.get("vulns", []):
            if (dep["name"], v["id"]) in seen:  # pip-audit can report one advisory twice
                continue
            seen.add((dep["name"], v["id"]))
            out.append(
                _finding(
                    "pip-audit",
                    target,
                    dep["name"],
                    dep["version"],
                    v["id"],
                    "UNKNOWN",
                    ", ".join(v.get("fix_versions", [])) or "no fix",
                    (v.get("description") or "").splitlines()[0][:160],
                    True,
                    v.get("aliases", []),
                )
            )
    return out


def from_npm_audit(data: dict, target: str) -> list[dict]:
    out = []
    for name, vuln in sorted(data.get("vulnerabilities", {}).items()):
        for via in vuln.get("via", []):
            if not isinstance(via, dict):  # only points at another package's advisory: counted there
                continue
            severity = via.get("severity", vuln.get("severity", "")).upper().replace("MODERATE", "MEDIUM")
            out.append(
                _finding(
                    "npm audit",
                    target,
                    name,
                    vuln.get("range", ""),
                    via["url"].rsplit("/", 1)[-1],
                    severity,
                    "fix available" if vuln.get("fixAvailable") else "no fix",
                    via.get("title", ""),
                    severity in BLOCKING,
                )
            )
    return out


def from_trivy(data: dict, target: str) -> list[dict]:
    out = []
    for result in data.get("Results") or []:
        for v in result.get("Vulnerabilities") or []:
            fixed = v.get("FixedVersion") or ""
            out.append(
                _finding(
                    "trivy",
                    target,
                    v["PkgName"],
                    v.get("InstalledVersion", ""),
                    v["VulnerabilityID"],
                    v["Severity"],
                    fixed or "no fix",
                    v.get("Title", ""),
                    v["Severity"] in BLOCKING and bool(fixed),
                )
            )
        for m in result.get("Misconfigurations") or []:
            if m.get("Status") == "FAIL":
                out.append(
                    _finding(
                        "trivy",
                        target,
                        result["Target"],
                        "",
                        m["ID"],
                        m["Severity"],
                        "change the config",
                        m.get("Title", ""),
                        m["Severity"] in BLOCKING,
                    )
                )
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


def _report(
    kind: str, on: datetime.date, scanned: list, problems: list, findings: list, accepted: dict, **more
) -> dict:
    findings, invalid = apply_accepted(findings, accepted, on)
    return {
        "kind": kind,
        "date": on.isoformat(),
        "scanned": scanned,
        "not_scanned": [],
        "absent": [],
        **more,
        "problems": problems + invalid,
        "findings": findings,
        "blocking": [f for f in findings if f["blocks"]],
    }


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
            code, _, err = run(
                ["uv", "pip", "compile", "--quiet", "--python-version", python, req, "-o", resolved], root
            )
            if code != 0:
                problems.append(
                    f"pip-audit {req}: could not resolve the requirements (exit {code}): {err.strip()[-300:]}"
                )
                continue
            scan(
                f"pip-audit {req}",
                [
                    "uv",
                    "run",
                    "--quiet",
                    "--no-project",
                    "--with",
                    PIP_AUDIT,
                    "pip-audit",
                    "-r",
                    resolved,
                    "--no-deps",
                    "--disable-pip",
                    "--format",
                    "json",
                    "--progress-spinner",
                    "off",
                ],
                root,
                from_pip_audit,
                str(Path(req).parent),
            )
    for app in conf.get("npm", []):
        if (root / app / "package-lock.json").is_file():
            scan(f"npm audit {app}", ["npm", "audit", "--json"], root / app, from_npm_audit, app)
        elif skip:
            absent.append(f"{app}/package-lock.json")
        else:
            problems.append(f"npm audit {app}: no package-lock.json to audit")
    fs = [a for a in conf.get("fs", []) if there(f"trivy fs {a}", a)]
    configs = [
        *(str(p.relative_to(root)) for p in dockerfiles(root, conf)),
        *(c for c in conf.get("config", []) if there(f"trivy config {c}", c)),
    ]
    found_images = images(root, conf)
    trivy_bin = None
    if fs or configs or found_images:
        try:
            trivy_bin = binary("trivy")
        except tools.ToolError as e:
            problems.append(f"trivy: {e}")

    def trivy(sub: str) -> list[str]:
        return [trivy_bin, sub, "--quiet"]

    unbuilt = [x for name in sources.BUILD for x in ("--skip-dirs", f"**/{name}")]  # F-150: no build folder's locks
    for app in fs if trivy_bin else []:
        scan(
            f"trivy fs {app}",
            [*trivy("fs"), "--scanners", "vuln", *unbuilt, "--format", "json", app],
            root,
            from_trivy,
            app,
        )
    for target in configs if trivy_bin else []:
        scan(f"trivy config {target}", [*trivy("config"), "--format", "json", target], root, from_trivy, target)
    for image in found_images if trivy_bin else []:
        scan(f"trivy image {image}", [*trivy("image"), "--format", "json", image], root, from_trivy, f"image {image}")
    if not skip and not any(conf.get(k) for k in ("pip", "npm", "fs", "config", "dockerfiles", "images")):
        problems.append("nothing to audit: name what to scan in crissp/testsuite/suites.json (audit)")
    return _report(
        "audit", on, scanned, problems, findings, accepted, not_scanned=own_images(root, conf), absent=absent
    )


def from_gitleaks(data: list, target: str) -> list[dict]:
    """Where a secret is, never what it is: the Secret and Match fields are not read."""
    out = []
    for leak in data or []:
        commit = (leak.get("Commit") or "")[:12]
        where = f"line {leak['StartLine']}" + (f" in {commit}" if commit else "")
        out.append(
            {
                **_finding(
                    "gitleaks",
                    target,
                    leak["File"],
                    where,
                    leak["RuleID"],
                    "HIGH",
                    "rotate it, then remove it from the history",
                    leak.get("Description", ""),
                    True,
                ),
                "fingerprint": leak.get("Fingerprint", ""),
            }
        )
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
        scan(
            "gitleaks git history" if history else "gitleaks files",
            [
                gitleaks,
                "git" if history else "dir",
                "--no-banner",
                "--redact",
                "--report-format",
                "json",
                "--report-path",
                "-",
                "--exit-code",
                "0",
                "--log-level",
                "warn",
                ".",
            ],
            root,
            from_gitleaks,
            "git history" if history else "files",
        )
    return _report("secrets", on, scanned, problems, findings, accepted)


ZAP = "ghcr.io/zaproxy/zaproxy:2.17.0@sha256:9624669db72f54d86c4b46a7064518bd9bf79d8c61a4c31befa9923489f328af"
RISK = {"3": "HIGH", "2": "MEDIUM", "1": "LOW", "0": "INFO"}  # ZAP's riskcode
LOCAL = re.compile(r"^(https?://)(localhost|127\.0\.0\.1)(?=[:/]|$)")


def reachable(url: str) -> bool:
    """Whether the app answers at all: any HTTP status is an answer; a refused connection is not."""
    if not url.startswith(("http://", "https://")):
        return False  # never a file: or another scheme, whatever suites.json says
    try:
        with urllib.request.urlopen(url, timeout=5):  # noqa: S310 — http(s) only, the project's own URL
            return True
    except urllib.error.HTTPError:
        return True
    except (OSError, ValueError):
        return False


def zap_rules(text: str) -> set[str]:
    """The ZAP rules a project's rules file (zap-baseline.py -c) makes FAIL: they block whatever their risk."""
    return {
        cols[0]
        for cols in (line.split("\t") for line in text.splitlines())
        if len(cols) > 1 and not cols[0].startswith("#") and cols[1].strip() == "FAIL"
    }


def from_zap(data: dict, target: str, fail: set[str]) -> list[dict]:
    """ZAP's alerts as findings, one per rule and site: a high or medium risk blocks, and a rule the project makes FAIL."""
    out = []
    for site in data.get("site", []):
        for a in site.get("alerts", []):
            severity = RISK.get(str(a.get("riskcode")), "UNKNOWN")
            uris = [i.get("uri", "") for i in a.get("instances", [])]
            name = a.get("alert") or a.get("name", "")
            out.append(
                _finding(
                    "zap",
                    target,
                    site.get("@name", target),
                    f"{a.get('count', len(uris))} URLs",
                    str(a.get("pluginid")),
                    severity,
                    "",
                    f"{name} (first at {uris[0]})" if uris else name,
                    severity in ("HIGH", "MEDIUM") or str(a.get("pluginid")) in fail,
                )
            )
    return out


ZAP_SCANS = {"baseline": "zap-baseline.py", "api": "zap-api-scan.py"}
STACK = "crissp-dast"  # the throwaway stack's compose project: containers, networks and volumes of its own


def _zap(root: Path, run, scan: list[str], rules: Path | None, platform: str, auth=None) -> tuple[dict | None, str]:
    """One ZAP scan (["baseline", url] or ["api", definition, format]): its JSON report, or None and why."""
    kind, url, *more = scan
    with (
        tempfile.TemporaryDirectory(prefix="crissp-zap-") as work,
        tempfile.TemporaryDirectory(prefix="crissp-zap-auth-") as private,
    ):
        os.chmod(work, 0o777)  # noqa: S103 — a private temp folder that ZAP, its own user, writes into
        network = ["--network", "host"] if platform.startswith("linux") else []
        seen = url if network else LOCAL.sub(r"\1host.docker.internal", url)
        args = ["-t", seen, *(["-f", *more] if more else []), "-J", "zap.json", "-I"]
        if rules:
            (Path(work) / "rules.tsv").write_text(rules.read_text())
            args += ["-c", "rules.tsv"]
        env = []
        if auth:  # the token in a private mode-600 file, never on a command line or in a log
            envfile = Path(private) / "auth.env"
            envfile.touch(mode=0o600)
            site = urllib.parse.urlsplit(seen).hostname
            envfile.write_text(
                f"ZAP_AUTH_HEADER={auth[0]}\nZAP_AUTH_HEADER_VALUE={auth[1]}\nZAP_AUTH_HEADER_SITE={site}\n"
            )
            env = ["--env-file", str(envfile)]
        code, out, err = run(
            ["docker", "run", "--rm", *network, *env, "-v", f"{work}:/zap/wrk:rw", ZAP, ZAP_SCANS[kind], *args], root
        )
        report = Path(work) / "zap.json"
        if not report.is_file():
            return None, f"ZAP could not scan {url} (exit {code}): {(err or out).strip()[-300:]}"
        return json.loads(report.read_text()), ""


@contextlib.contextmanager
def canary_server():
    """A page without a single security header, served on this machine: ZAP must find something on it."""

    class Page(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # the name http.server calls
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<!doctype html><title>crissp canary</title><p>No security header at all.")

        def log_message(self, *_):
            pass  # the scan's log stays the scan's

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Page)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/"
    finally:
        server.shutdown()
        server.server_close()


def _canary(root: Path, run, platform: str, canary) -> str:
    """Why the scan would prove nothing, or "" when ZAP found the canary's missing headers."""
    with canary() as url:
        report, why = _zap(root, run, ["baseline", url], None, platform)
    if report is None:
        return f"the canary: {why}"
    if not from_zap(report, url, set()):
        return "ZAP found nothing on the canary (a page without any security header): the scan proves nothing"
    return ""


def post_json(url: str, body: dict) -> dict:
    """POST body as JSON to the throwaway stack; its JSON answer ({} when it is empty)."""
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"not an http(s) URL: {url}")
    request = urllib.request.Request(  # noqa: S310 — http(s) only, checked above
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(request, timeout=30) as answer:  # noqa: S310 — http(s) only, checked above
        text = answer.read()
    return json.loads(text) if text.strip() else {}


def _signin(base: str, signin: dict, post) -> tuple[tuple[str, str] | None, str]:
    """Sign in through the app's first-run setup (and its login): the header ZAP sends, or None and why."""
    password = secrets.token_urlsafe(24)  # a fresh stack, a fresh password: never stored, never said

    def body(step: dict) -> dict:
        return json.loads(json.dumps(step.get("body", {})).replace("{password}", password))

    try:
        answer = post(base + signin["setup"]["path"], body(signin["setup"]))
        if signin.get("login"):
            answer = post(base + signin["login"]["path"], body(signin["login"]))
    except (OSError, ValueError, KeyError) as e:
        return None, f"signing in through first-run setup failed: {e}"
    token: object = answer
    for part in signin.get("token", "access_token").split("."):
        token = token.get(part) if isinstance(token, dict) else None
    if not isinstance(token, str) or not token:
        return None, f"signing in through first-run setup gave no token at {signin.get('token', 'access_token')}"
    return (signin.get("header", "Authorization"), f"{signin.get('scheme', 'Bearer')} {token}".strip()), ""


def _compose(root: Path, run, compose: Path, *args: str) -> tuple[int, str]:
    code, out, err = run(["docker", "compose", "-p", STACK, "-f", str(compose), *args], root)
    return code, (err or out).strip()[-300:]


def _stack(root: Path, run, compose: Path | None, targets: list[str], reach, problems: list) -> bool:
    """The app to scan: a throwaway stack when there is a compose file (whether it was started), else the running app."""
    if compose is None:
        down = [t for t in targets if not reach(t)]
        if down:
            problems.append(
                f"the app does not answer at {', '.join(down)}: start it first (docker compose up), or name its "
                "compose file in audit.dast.compose for a throwaway stack"
            )
        return False
    busy = [t for t in targets if reach(t)]
    if busy:
        problems.append(
            f"something already answers at {', '.join(busy)}: stop it (docker compose down); the scan starts a "
            "throwaway stack of its own"
        )
        return False
    code, said = _compose(root, run, compose, "up", "-d", "--build", "--wait")
    if code:
        problems.append(f"docker compose up could not start the throwaway stack (exit {code}): {said}")
    elif not all(reach(t) for t in targets):
        problems.append(f"the throwaway stack does not answer at {', '.join(t for t in targets if not reach(t))}")
    return True


def _place(root: Path, name: str | None, conf: dict, absent: list, problems: list) -> Path | None:
    """A file audit.dast names, when it names one and it is there."""
    if not name:
        return None
    if (root / name).is_file():
        return root / name
    (absent if conf.get("missing") == "skip" else problems).append(name)
    return None


def _setup(root: Path, dast: dict, conf: dict) -> tuple[list[str], list, list, Path | None, Path | None]:
    """The targets, what is absent, the problems before anything runs, the rules file and the compose file."""
    targets, absent, problems = dast.get("targets", []), [], []
    if not targets:
        absent.append("audit.dast.targets")
    problems += [f"not an http(s) URL: {t}" for t in targets if not t.startswith(("http://", "https://"))]
    rules = _place(root, dast.get("rules"), conf, absent, problems)
    compose = _place(root, dast.get("compose"), conf, absent, problems)
    if (dast.get("api") or dast.get("signin")) and compose is None and targets:
        problems.append(
            "the API scan and the sign-in run only against a throwaway stack: name its compose file in "
            "audit.dast.compose"
        )
    return targets, absent, problems, rules, compose


def _scans(root: Path, run, dast: dict, targets: list[str], rules, platform: str, post, findings, scanned) -> list:
    """The baseline of every target and, on the throwaway stack, the sign-in and the API scan; the problems."""
    auth = None
    if dast.get("signin"):
        origin = urllib.parse.urlsplit(targets[0])
        auth, why = _signin(f"{origin.scheme}://{origin.netloc}", dast["signin"], post)
        if auth is None:
            return [why]
    fail = zap_rules(rules.read_text()) if rules else set()
    scans = [["baseline", t] for t in targets]
    if dast.get("api"):
        scans.append(["api", dast["api"]["definition"], dast["api"].get("format", "openapi")])
    problems = []
    for scan in scans:
        report, why = _zap(root, run, scan, rules, platform, auth)
        if report is None:
            problems.append(why)
            continue
        findings.extend(from_zap(report, scan[1], fail))
        scanned.append(f"zap {scan[0]} {scan[1]}" + (" (signed in)" if auth else ""))
    return problems


def dast_all(
    root: Path,
    run,
    on: datetime.date,
    accepted: dict,
    conf: dict,
    reach=None,
    platform: str = sys.platform,
    post=None,
    canary=None,
) -> dict:
    """OWASP ZAP (pinned image) against the app: a canary first, then the baseline of every target and, on a
    throwaway compose stack (removed afterwards with its volumes), the sign-in and the API scan."""
    dast = conf.get("dast") or {}
    targets, absent, problems, rules, compose = _setup(root, dast, conf)
    findings, scanned = [], []
    if targets and not problems:
        why = _canary(root, run, platform, canary or canary_server)
        problems += [why] if why else []
    started = bool(targets) and not problems and _stack(root, run, compose, targets, reach or reachable, problems)
    if targets and not problems:
        problems += _scans(root, run, dast, targets, rules, platform, post or post_json, findings, scanned)
    if started:
        code, said = _compose(root, run, compose, "down", "-v", "--remove-orphans")
        problems += [f"docker compose down could not remove the throwaway stack (exit {code}): {said}"] if code else []
    return {**_report("dast", on, scanned, problems, findings, accepted), "absent": absent}


PERMISSIVE = re.compile(
    r"^(MIT(-0)?|BSD-\d-Clause.*|0BSD|Apache-[12]\.\d|ISC|Unlicense|Zlib|PSF-2\.0|Python-2\.0(\.1)?|"
    r"CC0-1\.0|CC-BY-[34]\.0|BlueOak-1\.0\.0|BSL-1\.0|WTFPL|X11|UPL-1\.0|Unicode-.*|OFL-1\.1|"
    r"Artistic-2\.0|HPND|MIT-CMU|NCSA|PostgreSQL)$",
    re.IGNORECASE,
)
WEAK = re.compile(r"^(LGPL-.*|MPL-.*|EPL-.*|CDDL-.*|CC-BY-SA-.*)$", re.IGNORECASE)
COPYLEFT = re.compile(r"^(GPL-.*|EUPL-.*|OSL-.*|CPAL-.*|RPL-.*)$", re.IGNORECASE)
FORBIDDEN = re.compile(r"^(AGPL-.*|SSPL-.*|BUSL-.*|Commons-Clause|CC-BY-NC.*|Elastic-2\.0|PolyForm-.*)$", re.IGNORECASE)
KINDS = ("permissive", "weak copyleft", "unknown", "copyleft", "forbidden")  # from best to worst
CLASSIFIERS = {
    "MIT License": "MIT",
    "BSD License": "BSD-3-Clause",
    "Apache Software License": "Apache-2.0",
    "ISC License (ISCL)": "ISC",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "The Unlicense (Unlicense)": "Unlicense",
    "GNU General Public License v2 (GPLv2)": "GPL-2.0-only",
    "GNU General Public License v3 (GPLv3)": "GPL-3.0-only",
    "GNU General Public License v2 or later (GPLv2+)": "GPL-2.0-or-later",
    "GNU Lesser General Public License v2 or later (LGPLv2+)": "LGPL-2.1-or-later",
    "GNU Lesser General Public License v3 (LGPLv3)": "LGPL-3.0-only",
    "GNU Affero General Public License v3": "AGPL-3.0-only",
}
PIN = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^]]*\])?==([^\s;#]+)")


def kind(expression: str) -> str:
    """How free a licence expression is: of OR the best choice counts, of AND (and WITH) the worst."""

    def one(spdx: str) -> str:
        spdx = spdx.strip("() ").removesuffix("+")
        for name, pattern in (
            ("forbidden", FORBIDDEN),
            ("copyleft", COPYLEFT),
            ("weak copyleft", WEAK),
            ("permissive", PERMISSIVE),
        ):
            if pattern.match(spdx):
                return name
        return "unknown"

    if not expression.strip():
        return "unknown"
    choices = [[one(t) for t in re.split(r"\s+(?:AND|WITH)\s+", part)] for part in re.split(r"\s+OR\s+", expression)]
    return min((max(c, key=KINDS.index) for c in choices), key=KINDS.index)


def _npm_licence(value) -> str:
    if isinstance(value, dict):
        return value.get("type", "")
    if isinstance(value, list):
        return " OR ".join(_npm_licence(v) for v in value)
    return value if isinstance(value, str) else ""


def npm_components(lock: dict, target: str) -> list[dict]:
    """Every package in a package-lock.json (v2, v3) with its licence, as the lock file records it."""
    out = []
    for key, p in lock.get("packages", {}).items():
        if not key:
            continue
        name = p.get("name") or key.rsplit("node_modules/", 1)[-1]
        out.append(
            {
                "ecosystem": "npm",
                "name": name,
                "version": p.get("version", ""),
                "licence": _npm_licence(p.get("license")),
                "dev": bool(p.get("dev") or p.get("devOptional")),
                "target": target,
            }
        )
    return out


def pypi_licence(info: dict) -> str:
    """A PyPI release's licence: its SPDX expression (PEP 639), else a short licence field, else its classifiers."""
    if info.get("license_expression"):
        return info["license_expression"]
    text = (info.get("license") or "").strip()
    if text and len(text) <= 40 and "\n" not in text and kind(text) != "unknown":
        return text
    named = [
        CLASSIFIERS.get(c.rsplit(" :: ", 1)[-1]) for c in info.get("classifiers", []) if c.startswith("License ::")
    ]
    return " OR ".join(sorted({n for n in named if n})) or text[:40]


def pip_components(text: str, target: str, lookup) -> tuple[list[dict], list[str]]:
    out, unpinned = [], []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = PIN.match(line)
        if not m:
            unpinned.append(f"{target}: {line} is not pinned (name==version): its licence cannot be known")
            continue
        out.append(
            {
                "ecosystem": "pypi",
                "name": m.group(1).lower(),
                "version": m.group(2),
                "licence": lookup(m.group(1), m.group(2)),
                "dev": False,
                "target": target,
            }
        )
    return out, unpinned


def pypi_lookup(cache: Path, fetcher=None):
    """name, version → its licence from PyPI's JSON, kept in the crissp cache (a release never changes)."""
    known = json.loads(cache.read_text()) if cache.is_file() else {}

    def lookup(name: str, version: str) -> str:
        key = f"{name.lower()}=={version}"
        if key not in known:
            url = f"https://pypi.org/pypi/{name}/{version}/json"
            known[key] = pypi_licence(json.loads((fetcher or tools.fetch)(url))["info"])
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(known, indent=1, sort_keys=True) + "\n")
        return known[key]

    return lookup


def purl(c: dict) -> str:
    name = c["name"].replace("@", "%40") if c["ecosystem"] == "npm" else c["name"]
    return f"pkg:{c['ecosystem']}/{name}@{c['version']}"


def sbom(components: list[dict], product: str, version: str, on: datetime.date) -> dict:
    """A CycloneDX 1.6 SBOM: every component with its version, purl and licence; dev-only ones are scope excluded."""
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "timestamp": f"{on.isoformat()}T00:00:00Z",
            "tools": {"components": [{"type": "application", "name": "crissp"}]},
            "component": {"type": "application", "name": product, "version": version},
        },
        "components": [
            {
                "type": "library",
                "name": c["name"],
                "version": c["version"],
                "purl": purl(c),
                "scope": "excluded" if c["dev"] else "required",
                **({"licenses": [{"expression": c["licence"]}]} if c["licence"] else {}),
            }
            for c in sorted(components, key=lambda c: (c["ecosystem"], c["name"], c["version"]))
        ],
    }


def licence_findings(components: list[dict], policy: dict) -> list[dict]:
    """A licence a product may not ship blocks: forbidden (AGPL, SSPL, BUSL, non-commercial) and copyleft (GPL), and
    whatever licenses.block names. Weak copyleft and an unknown licence are listed. A dev-only package never ships:
    listed whatever its licence. licenses.allow: {package: why} allows a package for good."""
    allow, block = policy.get("allow", {}), set(policy.get("block", []))
    out = []
    for c in components:
        found = kind(c["licence"]) if not set(re.split(r"[\s()]+", c["licence"])) & block else "forbidden"
        if found == "permissive":
            continue
        severity = {"forbidden": "CRITICAL", "copyleft": "HIGH", "weak copyleft": "MEDIUM", "unknown": "MEDIUM"}[found]
        why = allow.get(c["name"])
        blocks = found in ("forbidden", "copyleft") and not c["dev"] and not why
        out.append(
            {
                **_finding(
                    "licence",
                    c["target"],
                    c["name"],
                    c["version"],
                    c["licence"] or "no licence",
                    severity,
                    f"allowed: {why}" if why else "dev only, never shipped" if c["dev"] else "",
                    f"{found} licence",
                    blocks,
                )
            }
        )
    return out


def licenses_all(root: Path, run, on: datetime.date, accepted: dict, conf: dict, lookup) -> tuple[dict, dict]:
    """The licences of every dependency the audit names (pip: requirements files, resolved with every transitive
    package as the CVE audit does; npm: folders with a lock file), and the SBOM of them all."""
    components, problems, scanned, absent = [], [], [], []
    for place in conf.get("npm", []):
        lock = root / place / "package-lock.json"
        if not lock.is_file():
            (absent if conf.get("missing") == "skip" else problems).append(f"{place}/package-lock.json")
            continue
        components += npm_components(json.loads(lock.read_text()), place)
        scanned.append(f"licences {place}/package-lock.json")
    for place in conf.get("pip", []):
        req = root / place
        if not req.is_file():
            (absent if conf.get("missing") == "skip" else problems).append(place)
            continue
        with tempfile.TemporaryDirectory(prefix="licenses-") as tmp:
            resolved = Path(tmp) / "resolved.txt"
            code, _, err = run(
                [
                    "uv",
                    "pip",
                    "compile",
                    "--quiet",
                    "--python-version",
                    conf.get("python", PYTHON),
                    place,
                    "-o",
                    str(resolved),
                ],
                root,
            )
            text = resolved.read_text() if code == 0 and resolved.is_file() else None
        if text is None:
            problems.append(f"{place}: could not resolve the requirements (exit {code}): {err.strip()[-300:]}")
            continue
        try:
            found, unpinned = pip_components(text, place, lookup)
        except (OSError, ValueError, KeyError) as e:
            problems.append(f"{place}: the licences could not be read from PyPI: {e}")
            continue
        components += found
        problems += unpinned
        scanned.append(f"licences {place}")
    policy = conf.get("licenses") or {}
    report = {
        **_report("licenses", on, scanned, problems, licence_findings(components, policy), accepted),
        "absent": absent,
        "components": len(components),
    }
    version = (root / "VERSION").read_text().strip() if (root / "VERSION").is_file() else ""
    return report, sbom(components, policy.get("product") or root.resolve().name, version, on)


NOT_GREEN = {
    "audit": "Not green: update the package or image to the fixed version, or accept it for a while with a reason in "
    "crissp/testsuite/accepted-risks.json (at most 90 days).",
    "secrets": "Not green: a secret in git has leaked. Rotate it first, then remove it from the history. A finding that "
    "is no secret is allowed in .gitleaks.toml by its file and value ([[allowlists]], with a description "
    "saying why), never by its commit: a .gitleaksignore fingerprint misses in a shallow clone.",
    "sast": "Not green: change the code (each finding says why), or accept it for a while with a reason in "
    "crissp/testsuite/accepted-risks.json (at most 90 days).",
    "dast": "Not green: fix what the running app says (a header, a cookie flag, a leak), or accept it for a while with "
    "a reason in crissp/testsuite/accepted-risks.json (at most 90 days). A rule that does not apply goes into "
    "the project's ZAP rules file (audit.dast.rules) as IGNORE, with why.",
    "licenses": "Not green: replace the package, or allow it for good with why in suites.json (audit.licenses.allow: "
    "{package: why}) once it is clear the product may ship it.",
}


SEVERITY = {"ERROR": "HIGH", "WARNING": "MEDIUM"}


def from_semgrep(data: dict, target: str) -> list[dict]:
    """A finding names the file, the line, the rule and why; never the code it matched."""
    return [
        _finding(
            "semgrep",
            target,
            r["path"],
            f"line {r['start']['line']}",
            r["check_id"].rsplit(".", 1)[-1],
            SEVERITY.get(r["extra"]["severity"], "LOW"),
            "change the code",
            r["extra"].get("message", ""),
            r["extra"]["severity"] == "ERROR",
        )
        for r in data.get("results", [])
    ]


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
        problems.extend(
            f"semgrep: {e.get('type')}: {e.get('message', '')}".strip()
            for e in data.get("errors", [])
            if e.get("level") == "error"
        )
        return from_semgrep(data, target)

    if paths:
        configs = [x for rules in (str(RULES), *own) for x in ("--config", rules)]
        # F-150: never build output, also when the project's own .semgrepignore leaves Semgrep's defaults out
        excludes = [x for name in sources.BUILD for x in ("--exclude", name)]
        _scanner(run, findings, problems, scanned)(
            f"semgrep {' '.join(paths)}",
            semgrep(
                "scan",
                *configs,
                *excludes,
                "--json",
                "--metrics",
                "off",
                "--disable-version-check",
                "--quiet",
                *paths,
            ),
            root,
            parse,
            "code",
        )
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
        lines.append(
            f"note     not scanned yet (needs a Docker build): {image} — its base image and its dependencies are scanned above"
        )
    for path in report.get("absent", []):
        lines.append(f"note     not there yet, not scanned: {path}")
    for p in report["problems"]:
        lines.append(f"PROBLEM  {p}")
    kind = report.get("kind", "audit")
    fix = "fixed in " if kind == "audit" else ""
    for f in report["blocking"]:
        lines.append(
            f"BLOCKING {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): "
            f"{f['title']}" + (f" — {fix}{f['fixed']}" if f["fixed"] else "")
        )
    listed = [f for f in report["findings"] if not f["blocks"]]
    for f in listed:
        note = f"accepted: {f['accepted']}" if f.get("accepted") else f"{fix}{f['fixed']}" or f["title"]
        lines.append(f"listed   {f['severity']:<8} {f['id']}  {f['package']} {f['installed']}  ({f['target']}): {note}")
    if report["blocking"] or report["problems"]:
        lines.append(NOT_GREEN[kind])
    elif kind == "secrets":
        lines.append("No secret found.")
    elif not report["scanned"]:
        lines.append(
            f"Nothing to {'scan' if kind == 'sast' else 'audit'} yet: none of the places suites.json names is here."
        )
    elif kind == "sast":
        lines.append(f"No unsafe code blocks ({len(listed)} listed for review).")
    elif kind == "dast":
        lines.append(f"No high or medium risk on the app ({len(listed)} listed).")
    elif kind == "licenses":
        n = report["components"]
        lines.append(
            f"No licence blocks: {n} component{'' if n == 1 else 's'} in results/sbom.cdx.json ({len(listed)} listed)."
        )
    else:
        lines.append(f"No known vulnerability blocks ({len(listed)} listed).")
    return "\n".join(lines)


SCANS = {"run": "audit", "secrets": "secrets", "sast": "sast", "dast": "dast", "licenses": "licenses", "rules": None}


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
    elif argv[1] == "dast":
        report = dast_all(root, runner, today(), accepted, conf)
    elif argv[1] == "licenses":
        cache = tools.cache(dict(os.environ)).parent / "licenses" / "pypi.json"
        report, bom = licenses_all(root, runner, today(), accepted, conf, pypi_lookup(cache))
    else:
        report = run_all(root, runner, today(), accepted, conf)
    results = project.results(root)
    results.mkdir(parents=True, exist_ok=True)
    if argv[1] == "licenses":
        (results / "sbom.cdx.json").write_text(json.dumps(bom, indent=1) + "\n")
    (results / f"{SCANS[argv[1]]}.json").write_text(json.dumps(report, indent=1) + "\n")
    print(render(report))
    return 1 if report["blocking"] or report["problems"] else 0


if __name__ == "__main__":  # pragma: no cover — run by the audit step; main() is tested
    sys.exit(main(sys.argv))
