"""crissp/testsuite/lib/audit.py dast: the passive OWASP ZAP baseline (pinned image) against the running app. Docker,
ZAP and the app are stood in: never a real container in a test."""

import datetime
import importlib.util
import json
import urllib.error
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("audit_for_dast", LIB / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

TODAY = datetime.date(2026, 11, 28)
NONE = {"accepted": []}
ZAP = {
    "site": [
        {
            "@name": "http://127.0.0.1:8080",
            "alerts": [
                {
                    "pluginid": "10038",
                    "alert": "Content Security Policy (CSP) Header Not Set",
                    "riskcode": "2",
                    "count": "3",
                    "instances": [{"uri": "http://127.0.0.1:8080/"}, {"uri": "http://127.0.0.1:8080/a"}],
                },
                {
                    "pluginid": "10010",
                    "alert": "Cookie No HttpOnly Flag",
                    "riskcode": "1",
                    "count": "1",
                    "instances": [{"uri": "http://127.0.0.1:8080/login"}],
                },
                {"pluginid": "40012", "alert": "Cross Site Scripting (Reflected)", "riskcode": "3", "instances": []},
            ],
        }
    ]
}


class Docker:
    """Docker, stood in: `docker run` writes the ZAP report it was given into the mounted folder; records every call."""

    def __init__(self, report=ZAP, up=0):
        self.report, self.up, self.calls, self.rules = report, up, [], None

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        if argv[:2] == ["docker", "run"]:
            work = Path(argv[argv.index("-v") + 1].split(":")[0])
            if "-c" in argv:
                self.rules = (work / "rules.tsv").read_text()
            if self.report is not None:
                (work / "zap.json").write_text(json.dumps(self.report))
                return 0, "", ""
            return 3, "", "zap: cannot reach the target"
        if argv[:3] == ["docker", "compose", "-f"]:
            return (self.up, "", "no such service") if "up" in argv else (0, "", "")
        raise AssertionError(argv)


def up(*_):
    return True


CONF = {"dast": {"targets": ["http://127.0.0.1:8080"]}}


def test_the_baseline_scans_the_app_with_the_pinned_image_and_a_high_risk_blocks(tmp_path):
    docker = Docker()
    report = audit.dast_all(tmp_path, docker, TODAY, NONE, CONF, reach=up, platform="linux")
    assert report["scanned"] == ["zap baseline http://127.0.0.1:8080"] and report["problems"] == []
    rows = [(f["id"], f["severity"], f["blocks"], f["package"], f["installed"]) for f in report["findings"]]
    assert rows == [
        ("10038", "MEDIUM", False, "http://127.0.0.1:8080/", "3 URLs"),
        ("10010", "LOW", False, "http://127.0.0.1:8080/login", "1 URLs"),
        ("40012", "HIGH", True, "http://127.0.0.1:8080", "0 URLs"),
    ]
    (run,) = docker.calls
    assert run[:5] == ["docker", "run", "--rm", "--network", "host"] and audit.ZAP in run
    assert audit.ZAP.startswith("ghcr.io/zaproxy/zaproxy:") and "@sha256:" in audit.ZAP  # pinned by digest
    assert run[run.index(audit.ZAP) + 1 :] == ["zap-baseline.py", "-t", "http://127.0.0.1:8080", "-J", "zap.json", "-I"]
    said = audit.render(report)
    assert "BLOCKING HIGH     40012" in said and "Cross Site Scripting (Reflected)" in said
    assert "listed   MEDIUM   10038" in said and "accepted-risks.json" in said


def test_on_a_mac_the_container_reaches_the_app_through_the_docker_host(tmp_path):
    docker = Docker({"site": []})
    report = audit.dast_all(tmp_path, docker, TODAY, NONE, CONF, reach=up, platform="darwin")
    (run,) = docker.calls
    assert "--network" not in run and "http://host.docker.internal:8080" in run
    assert audit.render(report).splitlines()[-1] == "No high risk on the running app (0 listed)."


def test_the_projects_own_zap_rules_are_used_and_a_fail_rule_blocks(tmp_path):
    (tmp_path / "zap").mkdir()
    (tmp_path / "zap/rules.tsv").write_text("# rule\tACTION\twhy\n10038\tFAIL\t(CSP)\n10010\tIGNORE\t(test cookie)\n")
    docker = Docker()
    conf = {"dast": {**CONF["dast"], "rules": "zap/rules.tsv"}}
    report = audit.dast_all(tmp_path, docker, TODAY, NONE, conf, reach=up, platform="linux")
    assert docker.rules.startswith("# rule") and docker.calls[0][-2:] == ["-c", "rules.tsv"]
    assert {f["id"] for f in report["blocking"]} == {"10038", "40012"}
    assert audit.zap_rules("10038\tFAIL\n# 1\tFAIL\nbroken\n2\tWARN\n") == {"10038"}


def test_a_rules_file_that_is_not_there_is_absent_or_a_problem(tmp_path):
    conf = {"dast": {**CONF["dast"], "rules": "zap/rules.tsv"}}
    assert audit.dast_all(tmp_path, Docker(), TODAY, NONE, {**conf, "missing": "skip"}, reach=up)["absent"] == [
        "zap/rules.tsv"
    ]
    assert audit.dast_all(tmp_path, Docker(), TODAY, NONE, conf, reach=up)["problems"][0] == "zap/rules.tsv"


def test_an_app_that_is_not_up_is_started_with_compose_and_stopped_again(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    answers = iter([False, True])  # down at first, up once compose started it
    docker = Docker({"site": []})
    conf = {"dast": {**CONF["dast"], "compose": "docker-compose.yml"}}
    report = audit.dast_all(tmp_path, docker, TODAY, NONE, conf, reach=lambda _: next(answers), platform="linux")
    assert report["problems"] == [] and report["scanned"]
    assert [c[3:5] for c in docker.calls if c[1] == "compose"] == [
        [str(tmp_path / "docker-compose.yml"), "up"],
        [str(tmp_path / "docker-compose.yml"), "down"],
    ]


def test_an_app_that_is_already_up_is_left_running(tmp_path):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    docker = Docker({"site": []})
    audit.dast_all(tmp_path, docker, TODAY, NONE, {"dast": {**CONF["dast"], "compose": "docker-compose.yml"}}, reach=up)
    assert not [c for c in docker.calls if c[1] == "compose"]


def test_an_app_that_does_not_answer_is_a_problem_never_a_pass(tmp_path):
    report = audit.dast_all(tmp_path, Docker(), TODAY, NONE, CONF, reach=lambda _: False)
    assert report["problems"] == [
        "the app does not answer at http://127.0.0.1:8080: start it first (docker compose up)"
    ]
    assert report["scanned"] == [] and "Not green" in audit.render(report)
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    conf = {"dast": {**CONF["dast"], "compose": "docker-compose.yml"}}
    docker = Docker(up=1)
    report = audit.dast_all(tmp_path, docker, TODAY, NONE, conf, reach=lambda _: False)
    assert report["problems"] == ["docker compose up could not start the app (exit 1): no such service"]
    assert [c[4] for c in docker.calls] == ["up"]  # it started nothing, so it stops nothing


def test_a_zap_that_writes_no_report_is_a_problem(tmp_path):
    report = audit.dast_all(tmp_path, Docker(report=None), TODAY, NONE, CONF, reach=up)
    assert report["problems"] == ["ZAP could not scan http://127.0.0.1:8080 (exit 3): zap: cannot reach the target"]


def test_without_targets_there_is_nothing_to_scan(tmp_path):
    report = audit.dast_all(tmp_path, Docker(), TODAY, NONE, {}, reach=up)
    assert report["absent"] == ["audit.dast.targets"] and report["scanned"] == []
    assert "Nothing to" in audit.render(report)


def test_a_finding_is_accepted_for_a_while_like_any_other(tmp_path):
    accepted = {
        "accepted": [
            {
                "id": "40012",
                "package": "http://127.0.0.1:8080",
                "why": "a test page, gone in E9",
                "by": "PO",
                "since": "2026-11-20",
                "until": "2026-12-20",
            }
        ]
    }
    report = audit.dast_all(tmp_path, Docker(), TODAY, accepted, CONF, reach=up)
    assert report["blocking"] == []


def test_reachable_is_any_answer_and_never_a_refused_connection(monkeypatch):
    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(audit.urllib.request, "urlopen", lambda url, timeout: Answer())
    assert audit.reachable("http://127.0.0.1:8080")
    assert not audit.reachable("file:///etc/passwd")  # never another scheme

    def refused(url, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(audit.urllib.request, "urlopen", refused)
    assert not audit.reachable("http://127.0.0.1:8080")

    def status(url, timeout):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    monkeypatch.setattr(audit.urllib.request, "urlopen", status)
    assert audit.reachable("http://127.0.0.1:8080")


def test_main_runs_dast_into_its_own_results(tmp_path, monkeypatch, capsys):
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    (tmp_path / "crissp/testsuite/suites.json").write_text(json.dumps({"steps": [], "audit": CONF}))
    monkeypatch.setattr(audit, "runner", Docker({"site": []}))
    monkeypatch.setattr(audit, "reachable", up)
    assert audit.main(["audit.py", "dast"], tmp_path) == 0
    assert json.loads((tmp_path / "crissp/testsuite/results/dast.json").read_text())["kind"] == "dast"
    assert "No high risk" in capsys.readouterr().out


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def refused(url, timeout):
        raise AssertionError(f"a test opened {url}")

    monkeypatch.setattr(audit.urllib.request, "urlopen", refused)
