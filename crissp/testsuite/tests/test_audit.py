"""crissp/testsuite/lib/audit.py: every dependency and image CVE-tested; a known vulnerability stops a release."""

import datetime
import importlib.util
import json
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("audit_under_test", LIB / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

TODAY = datetime.date(2026, 11, 1)
# what an example shop asks its audit to scan (crissp/testsuite/suites.json, audit)
CONF = {"pip": ["app/backend/requirements.txt"], "npm": ["app/frontend"], "fs": ["app/backend", "app/frontend"],
        "dockerfiles": ["app/*/Dockerfile"], "config": ["helm/shop"], "images": ["docker-compose.yml", "helm/shop/values.yaml"],
        "own_images": {"values": "helm/shop/values.yaml", "parts": ["backend", "frontend"]}}

PIP = {"dependencies": [
    {"name": "fastapi", "version": "0.121.0", "vulns": []},
    {"name": "starlette", "version": "0.40.0", "vulns": [
        {"id": "GHSA-f96h-pmfr-66vw", "fix_versions": ["0.40.1", "0.41.0"], "aliases": ["CVE-2024-47874"],
         "description": "Starlette Denial of service (DoS) via multipart/form-data\nmore text"}]},
    {"name": "local-pkg", "skip_reason": "not on PyPI"}]}
NPM = {"vulnerabilities": {
    "vite": {"name": "vite", "severity": "high", "range": "6.0.0 - 6.0.8", "fixAvailable": True, "via": [
        {"source": 1102385, "name": "vite", "title": "Vite allows server.fs.deny bypass", "severity": "high",
         "url": "https://github.com/advisories/GHSA-x574-m823-4x7w", "range": ">=6.0.0 <6.0.9"}]},
    "esbuild": {"name": "esbuild", "severity": "moderate", "range": "<=0.24.2", "fixAvailable": False, "via": [
        {"source": 1102341, "name": "esbuild", "title": "esbuild dev server", "severity": "moderate",
         "url": "https://github.com/advisories/GHSA-67mh-4wv8-2f99", "range": "<=0.24.2"}]},
    "vite-plugin": {"name": "vite-plugin", "severity": "high", "range": "*", "fixAvailable": True, "via": ["vite"]}}}
TRIVY = {"Results": [
    {"Target": "python:3.13-slim (debian 12.12)", "Vulnerabilities": [
        {"VulnerabilityID": "CVE-2025-0001", "PkgName": "libssl3", "InstalledVersion": "3.0.15", "FixedVersion": "3.0.16",
         "Severity": "CRITICAL", "Title": "openssl: something"},
        {"VulnerabilityID": "CVE-2025-0002", "PkgName": "zlib1g", "InstalledVersion": "1.2.13", "FixedVersion": "",
         "Severity": "HIGH", "Title": "zlib: no fix yet"},
        {"VulnerabilityID": "CVE-2025-0003", "PkgName": "tar", "InstalledVersion": "1.34", "FixedVersion": "1.35",
         "Severity": "LOW"}]},
    {"Target": "Dockerfile", "Misconfigurations": [
        {"ID": "DS002", "Title": "Image user should not be 'root'", "Severity": "HIGH", "Status": "FAIL"},
        {"ID": "DS026", "Title": "No HEALTHCHECK defined", "Severity": "LOW", "Status": "FAIL"},
        {"ID": "DS001", "Title": "':latest' tag used", "Severity": "MEDIUM", "Status": "PASS"}]},
    {"Target": "requirements.txt"}]}


def test_pip_audit_findings_always_block_because_pypi_gives_no_severity():
    (f,) = audit.from_pip_audit(PIP, "app/backend")
    assert f == {"source": "pip-audit", "target": "app/backend", "package": "starlette", "installed": "0.40.0",
                 "id": "GHSA-f96h-pmfr-66vw", "aliases": ["CVE-2024-47874"], "severity": "UNKNOWN",
                 "fixed": "0.40.1, 0.41.0", "title": "Starlette Denial of service (DoS) via multipart/form-data",
                 "blocks": True}


def test_a_vulnerability_reported_twice_counts_once():
    twice = {"dependencies": [{**PIP["dependencies"][1], "vulns": PIP["dependencies"][1]["vulns"] * 2}]}
    assert len(audit.from_pip_audit(twice, "app/backend")) == 1


def test_npm_findings_block_from_high_and_name_the_advisory():
    found = audit.from_npm_audit(NPM, "app/frontend")
    assert [(f["package"], f["id"], f["severity"], f["blocks"], f["fixed"]) for f in found] == [
        ("esbuild", "GHSA-67mh-4wv8-2f99", "MEDIUM", False, "no fix"),
        ("vite", "GHSA-x574-m823-4x7w", "HIGH", True, "fix available"),
    ]  # vite-plugin only points at vite: counted once, at vite
    assert found[1]["installed"] == "6.0.0 - 6.0.8"


def test_trivy_blocks_high_and_critical_with_a_fix_and_failing_misconfigurations():
    found = audit.from_trivy(TRIVY, "image python:3.13-slim")
    rows = [(f["id"], f["severity"], f["blocks"]) for f in found]
    assert rows == [("CVE-2025-0001", "CRITICAL", True), ("CVE-2025-0002", "HIGH", False), ("CVE-2025-0003", "LOW", False),
                    ("DS002", "HIGH", True), ("DS026", "LOW", False)]
    assert found[0]["fixed"] == "3.0.16" and found[1]["fixed"] == "no fix"
    assert found[3]["package"] == "Dockerfile" and found[3]["source"] == "trivy"
    assert audit.from_trivy({}, "x") == []


def risk(**kw):
    return {"id": "CVE-2025-0001", "package": "libssl3", "why": "the TLS code is not reachable: nginx terminates TLS "
            "in Traefik", "by": "the product owner", "since": "2026-10-20", "until": "2026-12-01", **kw}


def test_an_accepted_risk_passes_until_its_date():
    found = audit.from_trivy(TRIVY, "image")
    out, problems = audit.apply_accepted(found, {"accepted": [risk()]}, TODAY)
    assert problems == []
    hit = next(f for f in out if f["id"] == "CVE-2025-0001")
    assert hit["blocks"] is False and hit["accepted"].startswith("the product owner until 2026-12-01: the TLS code")
    later, problems = audit.apply_accepted(found, {"accepted": [risk()]}, datetime.date(2026, 12, 2))
    assert next(f for f in later if f["id"] == "CVE-2025-0001")["blocks"] is True
    assert problems == ["accepted risk CVE-2025-0001 (libssl3) expired on 2026-12-01: fix it or accept it again"]


def test_an_acceptance_also_matches_an_alias_and_only_its_package():
    (f,) = audit.from_pip_audit(PIP, "app/backend")
    out, _ = audit.apply_accepted([f], {"accepted": [risk(id="CVE-2024-47874", package="starlette")]}, TODAY)
    assert out[0]["blocks"] is False
    out, _ = audit.apply_accepted([f], {"accepted": [risk(id="CVE-2024-47874", package="fastapi")]}, TODAY)
    assert out[0]["blocks"] is True


@pytest.mark.parametrize("entry,message", [
    (risk(why=""), "needs id, package, why, by, since and until"),
    (risk(until="soon"), "dates are YYYY-MM-DD"),
    (risk(since="2026-08-01", until="2026-12-01"), "at most 90 days"),
    (risk(since="2026-12-01", until="2026-11-01"), "ends before it starts"),
])
def test_an_acceptance_needs_a_reason_a_person_and_a_short_end_date(entry, message):
    out, problems = audit.apply_accepted(audit.from_trivy(TRIVY, "image"), {"accepted": [entry]}, TODAY)
    assert len(problems) == 1 and message in problems[0]
    assert next(f for f in out if f["id"] == "CVE-2025-0001")["blocks"] is True


def test_the_images_are_every_one_the_dockerfiles_compose_and_chart_name(tmp_path):
    (tmp_path / "app/backend").mkdir(parents=True)
    (tmp_path / "app/backend/Dockerfile").write_text("FROM python:3.13-slim\nRUN x\n")
    (tmp_path / "app/frontend").mkdir(parents=True)
    (tmp_path / "app/frontend/Dockerfile").write_text(
        "FROM node:22-alpine AS build\nFROM --platform=linux/amd64 nginxinc/nginx-unprivileged:1.29-alpine\n"
        "COPY --from=build /a /b\nFROM build AS again\nFROM scratch\n")
    (tmp_path / "docker-compose.yml").write_text("services:\n  postgres:\n    image: postgres:17-alpine\n"
                                                 "  backend:\n    build: ./app/backend\n")
    (tmp_path / "helm/shop").mkdir(parents=True)
    (tmp_path / "helm/shop/values.yaml").write_text(
        "image:\n  repository: example/shop  # one repository\n  version: \"0.1.0\"\n"
        "postgresql:\n  image: postgres:16-alpine  # old\nx: 1\n")
    assert audit.images(tmp_path, CONF) == ["nginxinc/nginx-unprivileged:1.29-alpine", "node:22-alpine",
                                      "postgres:16-alpine", "postgres:17-alpine", "python:3.13-slim"]
    assert audit.own_images(tmp_path, CONF) == ["example/shop:backend-0.1.0", "example/shop:frontend-0.1.0"]


class Runner:
    """The scanners, stood in: answers per command name; records every call."""

    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def __call__(self, argv, cwd):
        self.calls.append((argv, cwd))
        key = max((k for k in self.answers if k in " ".join(argv)), key=len)  # the most specific
        code, out = self.answers[key]
        return code, out if isinstance(out, str) else json.dumps(out), "stderr text"


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app/backend").mkdir(parents=True)
    (tmp_path / "app/backend/requirements.txt").write_text("fastapi==0.121.0\n")
    (tmp_path / "app/backend/Dockerfile").write_text("FROM python:3.13-slim\n")
    (tmp_path / "app/frontend").mkdir(parents=True)
    (tmp_path / "app/frontend/package-lock.json").write_text("{}")
    (tmp_path / "app/frontend/Dockerfile").write_text("FROM nginxinc/nginx-unprivileged:1.29-alpine\n")
    (tmp_path / "helm/shop").mkdir(parents=True)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    return tmp_path


def test_the_charts_own_images_are_named_as_not_scanned_yet(repo):
    (repo / "helm/shop/values.yaml").write_text("image:\n  repository: example/shop\n  version: \"1\"\n")
    report = audit.run_all(repo, Runner(CLEAN), TODAY, accepted={"accepted": []}, conf=CONF)
    assert report["not_scanned"] == ["example/shop:backend-1", "example/shop:frontend-1"]
    assert report["problems"] == []
    assert "not scanned yet (needs a Docker build): example/shop:backend-1" in audit.render(report)


def test_requirements_that_cannot_be_resolved_are_a_problem(repo):
    report = audit.run_all(repo, Runner({**CLEAN, "pip compile": (1, "")}), TODAY, accepted={"accepted": []}, conf=CONF)
    assert any(p.startswith("pip-audit app/backend/requirements.txt: could not resolve") for p in report["problems"])


CLEAN = {"pip compile": (0, ""), "pip-audit": (0, {"dependencies": []}), "npm audit": (0, {"vulnerabilities": {}}),
         "trivy": (0, {"Results": []})}


def test_a_clean_run_scans_everything_and_passes(repo):
    runner = Runner(CLEAN)
    report = audit.run_all(repo, runner, TODAY, accepted={"accepted": []}, conf=CONF)
    assert report["blocking"] == [] and report["problems"] == []
    scanned = report["scanned"]
    assert scanned == ["pip-audit app/backend/requirements.txt", "npm audit app/frontend",
                       "trivy fs app/backend", "trivy fs app/frontend",
                       "trivy config app/backend/Dockerfile", "trivy config app/frontend/Dockerfile",
                       "trivy config helm/shop",
                       "trivy image nginxinc/nginx-unprivileged:1.29-alpine", "trivy image python:3.13-slim"]
    commands = [" ".join(a) for a, _ in runner.calls]
    assert any("--severity" not in c and "trivy image" in c and "--format json" in c for c in commands)
    compile_ = next(c for c in commands if "pip compile" in c)
    assert "app/backend/requirements.txt" in compile_ and "--python-version 3.14" in compile_
    pip = next(c for c in commands if "pip-audit" in c and "-r" in c)
    assert "--no-deps" in pip and "--disable-pip" in pip and "--format json" in pip
    assert report["not_scanned"] == []
    assert all("--exit-code" not in c for c in commands)  # the verdict is ours, from the JSON


def test_findings_block_and_say_what_to_do(repo):
    image, config = {"Results": TRIVY["Results"][:1]}, {"Results": TRIVY["Results"][1:2]}
    runner = Runner({**CLEAN, "pip-audit": (1, PIP), "trivy image": (0, image), "trivy config": (0, config)})
    report = audit.run_all(repo, runner, TODAY, accepted={"accepted": []}, conf=CONF)
    ids = sorted({f["id"] for f in report["blocking"]})
    assert ids == ["CVE-2025-0001", "DS002", "GHSA-f96h-pmfr-66vw"]
    text = audit.render(report)
    assert "BLOCKING" in text and "starlette 0.40.0" in text and "fixed in 0.40.1, 0.41.0" in text
    assert "accepted-risks.json" in text


def test_a_scanner_that_fails_or_is_missing_is_a_problem_never_a_pass(repo):
    runner = Runner({**CLEAN, "pip-audit": (2, "Traceback: no network"), "npm audit": (1, "")})
    report = audit.run_all(repo, runner, TODAY, accepted={"accepted": []}, conf=CONF)
    assert any(p.startswith("pip-audit app/backend/requirements.txt could not run") for p in report["problems"])
    assert any(p.startswith("npm audit app/frontend could not run") for p in report["problems"])
    (repo / "app/frontend/package-lock.json").unlink()
    report = audit.run_all(repo, Runner(CLEAN), TODAY, accepted={"accepted": []}, conf=CONF)
    assert "npm audit app/frontend: no package-lock.json to audit" in report["problems"]


def test_the_command_line_writes_the_report_and_exits_on_what_blocks(repo, monkeypatch, capsys):
    results = repo / "crissp/testsuite/results"
    (repo / "crissp/testsuite").mkdir(parents=True)
    (repo / "crissp/testsuite/suites.json").write_text(json.dumps({"product": "Shop", "audit": CONF}))
    monkeypatch.setenv("CRISSP_ROOT", str(repo))
    monkeypatch.setattr(audit, "today", lambda: TODAY)
    monkeypatch.setattr(audit, "runner", Runner(CLEAN))
    assert audit.main(["audit.py", "run"]) == 0  # no accepted-risks.json yet: nothing accepted
    assert json.loads((results / "audit.json").read_text())["blocking"] == []
    assert "No known vulnerability blocks" in capsys.readouterr().out
    (repo / "crissp/testsuite/accepted-risks.json").write_text('{"accepted": []}')
    monkeypatch.setattr(audit, "runner", Runner({**CLEAN, "pip-audit": (1, PIP)}))
    assert audit.main(["audit.py", "run"]) == 1
    assert audit.main(["audit.py"]) == 2
    (repo / "crissp/testsuite/suites.json").write_text("{")
    assert audit.main(["audit.py", "run"]) == 2 and "audit: crissp/testsuite/suites.json is not valid JSON" in capsys.readouterr().err


def test_an_audit_with_nothing_to_scan_is_a_problem_never_a_pass(tmp_path):
    report = audit.run_all(tmp_path, Runner(CLEAN), TODAY, accepted={"accepted": []}, conf={})
    assert report["problems"] == ["nothing to audit: name what to scan in crissp/testsuite/suites.json (audit)"]
    assert audit.own_images(tmp_path, {"own_images": {"values": "missing.yaml", "parts": ["x"]}}) == []


def test_this_repository_audits_its_pinned_tools():
    conf = audit.project.load(LIB.parents[2])["audit"]
    assert conf == {"pip": ["crissp/testsuite/requirements.txt", "crissp/deploy/requirements.txt"]}


def test_the_real_runner_returns_code_and_output(tmp_path):
    code, out, err = audit.runner(["sh", "-c", "echo out; echo err >&2; exit 3"], tmp_path)
    assert (code, out.strip(), err.strip()) == (3, "out", "err")
    code, out, err = audit.runner(["no-such-scanner-xyz"], tmp_path)
    assert code == 127 and "not installed" in err
    assert isinstance(audit.today(), datetime.date)


def test_the_accepted_risks_file_in_the_repository_is_valid_and_names_no_one_s_product():
    data = json.loads((LIB.parent / "accepted-risks.json").read_text())
    _, problems = audit.apply_accepted([], data, datetime.date.today())
    assert problems == []


def test_the_report_shows_problems_and_what_was_accepted_and_why():
    found, _ = audit.apply_accepted(audit.from_trivy(TRIVY, "image"), {"accepted": [risk()]}, TODAY)
    text = audit.render({"scanned": ["trivy image x"], "not_scanned": [], "problems": ["npm audit app/frontend: no package-lock.json"],
                         "findings": found, "blocking": [f for f in found if f["blocks"]]})
    assert "PROBLEM  npm audit app/frontend: no package-lock.json" in text
    assert "accepted: the product owner until 2026-12-01: the TLS code" in text
    assert text.splitlines()[-1].startswith("Not green")
