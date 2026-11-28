"""crissp/testsuite/lib/audit.py dast: OWASP ZAP (pinned image) against the app, a canary first, on a throwaway compose
stack signed in through first-run setup, with the API scan. Docker, ZAP and the app are stood in: never a real
container in a test (the canary's page is real: it is served on this machine)."""

import datetime
import http.client
import importlib.util
import json
import urllib.error
import urllib.parse
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("audit_for_dast", LIB / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

TODAY = datetime.date(2026, 11, 28)
NONE = {"accepted": []}
APP = "http://127.0.0.1:8080"
ZAP = {
    "site": [
        {
            "@name": APP,
            "alerts": [
                {
                    "pluginid": "10038",
                    "alert": "Content Security Policy (CSP) Header Not Set",
                    "riskcode": "2",
                    "count": "3",
                    "instances": [{"uri": f"{APP}/"}, {"uri": f"{APP}/a"}],
                },
                {
                    "pluginid": "10010",
                    "alert": "Cookie No HttpOnly Flag",
                    "riskcode": "1",
                    "count": "1",
                    "instances": [{"uri": f"{APP}/login"}],
                },
                {"pluginid": "40012", "alert": "Cross Site Scripting (Reflected)", "riskcode": "3", "instances": []},
            ],
        }
    ]
}
CANARY = {"site": [{"@name": "canary", "alerts": [{"pluginid": "10021", "riskcode": "1", "alert": "X-Content-Type"}]}]}
CLEAN = {"site": []}


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def refused(url, timeout):
        raise AssertionError(f"a test opened {url}")

    monkeypatch.setattr(audit.urllib.request, "urlopen", refused)


class Docker:
    """Docker, stood in: `docker run` writes the ZAP report for what it scans into the mounted folder (the canary's
    page gets CANARY); `docker compose` answers `up`; records every call, the rules and the auth env file it saw."""

    def __init__(self, report=ZAP, up=0, down=0, canary=CANARY, api=CLEAN):
        self.report, self.up, self.down, self.canary, self.api = report, up, down, canary, api
        self.calls, self.rules, self.env = [], None, None

    def __call__(self, argv, cwd):
        self.calls.append(argv)
        if argv[:2] == ["docker", "run"]:
            work = Path(argv[argv.index("-v") + 1].split(":")[0])
            if "-c" in argv:
                self.rules = (work / "rules.tsv").read_text()
            if "--env-file" in argv:
                envfile = Path(argv[argv.index("--env-file") + 1])
                self.env = (envfile.read_text(), envfile.stat().st_mode & 0o777)
            target = argv[argv.index("-t") + 1]
            canary = urllib.parse.urlsplit(target).port not in (8080, None)
            report = self.canary if canary else self.api if "zap-api-scan.py" in argv else self.report
            if report is None:
                return 3, "", "zap: cannot reach the target"
            (work / "zap.json").write_text(json.dumps(report))
            return 0, "", ""
        if argv[:4] == ["docker", "compose", "-p", audit.STACK]:
            if "up" in argv:
                return self.up, "", "no such service"
            return self.down, "", "volume in use"
        raise AssertionError(argv)

    def scans(self):
        return [c for c in self.calls if c[1] == "run"]

    def compose(self):
        return [c[6] for c in self.calls if c[1] == "compose"]


def up(*_):
    return True


def canary():
    """The canary's page, stood in: an address that is not the app's."""

    class Serve:
        def __enter__(self):
            return "http://127.0.0.1:9999/"

        def __exit__(self, *_):
            return False

    return Serve()


def stack(answers):
    """The throwaway stack: down until compose started it."""
    answers = iter(answers)
    return lambda _: next(answers)


def dast(root, docker, conf, **kw):
    kw.setdefault("reach", up)
    kw.setdefault("platform", "linux")
    kw.setdefault("canary", canary)
    return audit.dast_all(root, docker, TODAY, kw.pop("accepted", NONE), conf, **kw)


CONF = {"dast": {"targets": [APP]}}


def with_compose(tmp_path, **more):
    (tmp_path / "docker-compose.yml").write_text("services: {}\n")
    return {"dast": {**CONF["dast"], "compose": "docker-compose.yml", **more}}


def test_the_baseline_scans_the_app_with_the_pinned_image_and_high_and_medium_block(tmp_path):
    docker = Docker()
    report = dast(tmp_path, docker, CONF)
    assert report["scanned"] == [f"zap baseline {APP}"] and report["problems"] == []
    rows = [(f["id"], f["severity"], f["blocks"], f["package"], f["installed"]) for f in report["findings"]]
    assert rows == [
        ("10038", "MEDIUM", True, APP, "3 URLs"),
        ("10010", "LOW", False, APP, "1 URLs"),
        ("40012", "HIGH", True, APP, "0 URLs"),
    ]
    assert report["findings"][0]["title"] == f"Content Security Policy (CSP) Header Not Set (first at {APP}/)"
    canary_run, run = docker.scans()
    assert canary_run[canary_run.index(audit.ZAP) + 1 :][:3] == ["zap-baseline.py", "-t", "http://127.0.0.1:9999/"]
    assert run[:5] == ["docker", "run", "--rm", "--network", "host"] and audit.ZAP in run
    assert audit.ZAP.startswith("ghcr.io/zaproxy/zaproxy:") and "@sha256:" in audit.ZAP  # pinned by digest
    assert run[run.index(audit.ZAP) + 1 :] == ["zap-baseline.py", "-t", APP, "-J", "zap.json", "-I"]
    said = audit.render(report)
    assert "BLOCKING HIGH     40012" in said and "BLOCKING MEDIUM   10038" in said
    assert "listed   LOW      10010" in said and "accepted-risks.json" in said


def test_a_canary_comes_first_and_a_zap_that_finds_nothing_on_it_proves_nothing(tmp_path):
    docker = Docker(canary=CLEAN)
    report = dast(tmp_path, docker, CONF)
    assert report["problems"] == [
        "ZAP found nothing on the canary (a page without any security header): the scan proves nothing"
    ]
    assert report["scanned"] == [] and len(docker.scans()) == 1
    report = dast(tmp_path, Docker(canary=None), CONF)
    assert report["problems"] == [
        "the canary: ZAP could not scan http://127.0.0.1:9999/ (exit 3): zap: cannot reach the target"
    ]


def test_the_canary_is_a_real_page_without_any_security_header():
    with audit.canary_server() as url:
        where = urllib.parse.urlsplit(url)
        conn = http.client.HTTPConnection(where.hostname, where.port, timeout=5)
        conn.request("GET", "/")
        answer = conn.getresponse()
        assert answer.status == 200 and b"canary" in answer.read()
        assert answer.getheader("Content-Security-Policy") is None and answer.getheader("X-Frame-Options") is None
        conn.close()


def test_on_a_mac_the_container_reaches_the_app_through_the_docker_host(tmp_path):
    docker = Docker(CLEAN)
    report = dast(tmp_path, docker, CONF, platform="darwin")
    run = docker.scans()[-1]
    assert "--network" not in run and "http://host.docker.internal:8080" in run
    assert audit.render(report).splitlines()[-1] == "No high or medium risk on the app (0 listed)."


def test_the_projects_own_zap_rules_are_used_and_a_fail_rule_blocks(tmp_path):
    (tmp_path / "zap").mkdir()
    (tmp_path / "zap/rules.tsv").write_text("# rule\tACTION\twhy\n10010\tFAIL\t(cookie)\n10038\tIGNORE\t(CSP)\n")
    docker = Docker()
    report = dast(tmp_path, docker, {"dast": {**CONF["dast"], "rules": "zap/rules.tsv"}})
    assert docker.rules.startswith("# rule") and docker.calls[-1][-2:] == ["-c", "rules.tsv"]
    assert "-c" not in docker.scans()[0]  # the canary is scanned without the project's rules
    assert {f["id"] for f in report["blocking"]} == {"10038", "10010", "40012"}
    assert audit.zap_rules("10038\tFAIL\n# 1\tFAIL\nbroken\n2\tWARN\n") == {"10038"}


def test_a_file_audit_dast_names_that_is_not_there_is_absent_or_a_problem(tmp_path):
    conf = {"dast": {**CONF["dast"], "rules": "zap/rules.tsv", "compose": "compose.yml"}}
    report = dast(tmp_path, Docker(), {**conf, "missing": "skip"})
    assert report["absent"] == ["zap/rules.tsv", "compose.yml"]
    assert dast(tmp_path, Docker(), conf)["problems"] == ["zap/rules.tsv", "compose.yml"]


def test_with_a_compose_file_the_scan_runs_on_a_throwaway_stack_removed_with_its_volumes(tmp_path):
    docker = Docker(CLEAN)
    report = dast(tmp_path, docker, with_compose(tmp_path), reach=stack([False, True]))
    assert report["problems"] == [] and report["scanned"] == [f"zap baseline {APP}"]
    compose = [c for c in docker.calls if c[1] == "compose"]
    assert compose == [
        [
            "docker",
            "compose",
            "-p",
            "crissp-dast",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "up",
            "-d",
            "--build",
            "--wait",
        ],
        [
            "docker",
            "compose",
            "-p",
            "crissp-dast",
            "-f",
            str(tmp_path / "docker-compose.yml"),
            "down",
            "-v",
            "--remove-orphans",
        ],
    ]


def test_an_app_that_already_answers_is_never_the_throwaway_stack(tmp_path):
    docker = Docker()
    report = dast(tmp_path, docker, with_compose(tmp_path))
    assert report["problems"] == [
        f"something already answers at {APP}: stop it (docker compose down); the scan starts a throwaway stack of "
        "its own"
    ]
    assert docker.compose() == [] and len(docker.scans()) == 1  # the canary only


def test_a_stack_that_does_not_start_or_answer_is_a_problem_and_is_still_removed(tmp_path):
    docker = Docker(up=1)
    report = dast(tmp_path, docker, with_compose(tmp_path), reach=lambda _: False)
    assert report["problems"] == ["docker compose up could not start the throwaway stack (exit 1): no such service"]
    assert docker.compose() == ["up", "down"]
    docker = Docker(down=1)
    report = dast(tmp_path, docker, with_compose(tmp_path), reach=lambda _: False)
    assert report["problems"] == [
        f"the throwaway stack does not answer at {APP}",
        "docker compose down could not remove the throwaway stack (exit 1): volume in use",
    ]


def test_an_app_that_does_not_answer_is_a_problem_never_a_pass(tmp_path):
    report = dast(tmp_path, Docker(), CONF, reach=lambda _: False)
    assert report["problems"] == [
        f"the app does not answer at {APP}: start it first (docker compose up), or name its compose file in "
        "audit.dast.compose for a throwaway stack"
    ]
    assert report["scanned"] == [] and "Not green" in audit.render(report)


def test_the_stack_is_signed_in_through_first_run_setup_and_zap_sends_the_token(tmp_path):
    posted = []

    def post(url, body):
        posted.append((url, body))
        return {"data": {"token": "t0k3n"}} if url.endswith("/login") else {}

    signin = {
        "setup": {"path": "/api/setup", "body": {"email": "dast@example.org", "password": "{password}"}},
        "login": {"path": "/api/login", "body": {"email": "dast@example.org", "password": "{password}"}},
        "token": "data.token",
    }
    docker = Docker(CLEAN)
    report = dast(tmp_path, docker, with_compose(tmp_path, signin=signin), reach=stack([False, True]), post=post)
    assert report["scanned"] == [f"zap baseline {APP} (signed in)"]
    (setup, setup_body), (login, login_body) = posted
    assert (setup, login) == (f"{APP}/api/setup", f"{APP}/api/login")
    password = setup_body["password"]
    assert len(password) >= 32 and login_body["password"] == password  # fresh per run, the same for its login
    text, mode = docker.env
    assert text == "ZAP_AUTH_HEADER=Authorization\nZAP_AUTH_HEADER_VALUE=Bearer t0k3n\nZAP_AUTH_HEADER_SITE=127.0.0.1\n"
    assert mode == 0o600 and not any("t0k3n" in a for c in docker.calls for a in c)  # never on a command line
    assert "--env-file" not in docker.scans()[0]  # the canary is scanned without it


def test_a_sign_in_that_fails_or_gives_no_token_is_a_problem(tmp_path):
    def refused(url, body):
        raise urllib.error.HTTPError(url, 409, "Conflict", {}, None)

    signin = {"setup": {"path": "/api/setup"}, "header": "X-Token", "scheme": ""}
    conf = with_compose(tmp_path, signin=signin)
    report = dast(tmp_path, Docker(), conf, reach=stack([False, True]), post=refused)
    assert report["problems"] == ["signing in through first-run setup failed: HTTP Error 409: Conflict"]
    report = dast(tmp_path, Docker(), conf, reach=stack([False, True]), post=lambda url, body: {"other": 1})
    assert report["problems"] == ["signing in through first-run setup gave no token at access_token"]
    docker = Docker(CLEAN)
    dast(tmp_path, docker, conf, reach=stack([False, True]), post=lambda url, body: {"access_token": "abc"})
    assert "ZAP_AUTH_HEADER=X-Token\nZAP_AUTH_HEADER_VALUE=abc\n" in docker.env[0]


def test_the_api_is_scanned_on_the_throwaway_stack(tmp_path):
    api = {"definition": f"{APP}/openapi.json"}
    docker = Docker(CLEAN, api=ZAP)
    report = dast(tmp_path, docker, with_compose(tmp_path, api=api), reach=stack([False, True]))
    assert report["scanned"] == [f"zap baseline {APP}", f"zap api {APP}/openapi.json"]
    run = docker.scans()[-1]
    assert run[run.index(audit.ZAP) + 1 :] == [
        "zap-api-scan.py",
        "-t",
        f"{APP}/openapi.json",
        "-f",
        "openapi",
        "-J",
        "zap.json",
        "-I",
    ]
    assert {f["id"] for f in report["blocking"]} == {"10038", "40012"}


def test_the_api_scan_and_the_sign_in_never_run_against_an_app_crissp_did_not_start(tmp_path):
    docker = Docker()
    report = dast(tmp_path, docker, {"dast": {**CONF["dast"], "api": {"definition": f"{APP}/openapi.json"}}})
    assert report["problems"] == [
        "the API scan and the sign-in run only against a throwaway stack: name its compose file in audit.dast.compose"
    ]
    assert docker.calls == []


def test_a_zap_that_writes_no_report_is_a_problem(tmp_path):
    report = dast(tmp_path, Docker(report=None), CONF)
    assert report["problems"] == [f"ZAP could not scan {APP} (exit 3): zap: cannot reach the target"]


def test_without_targets_there_is_nothing_to_scan_and_a_target_is_http(tmp_path):
    docker = Docker()
    report = dast(tmp_path, docker, {})
    assert report["absent"] == ["audit.dast.targets"] and report["scanned"] == [] and docker.calls == []
    assert "Nothing to" in audit.render(report)
    report = dast(tmp_path, docker, {"dast": {"targets": ["file:///etc/passwd"]}})
    assert report["problems"] == ["not an http(s) URL: file:///etc/passwd"] and docker.calls == []


def test_a_finding_is_accepted_for_a_while_by_its_rule_and_site(tmp_path):
    accepted = {
        "accepted": [
            {
                "id": i,
                "package": APP,
                "why": "a test page, gone in E9",
                "by": "PO",
                "since": "2026-11-20",
                "until": "2026-12-20",
            }
            for i in ("40012", "10038")
        ]
    }
    assert dast(tmp_path, Docker(), CONF, accepted=accepted)["blocking"] == []


def test_reachable_is_any_answer_and_never_a_refused_connection(monkeypatch):
    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(audit.urllib.request, "urlopen", lambda url, timeout: Answer())
    assert audit.reachable(APP)
    assert not audit.reachable("file:///etc/passwd")  # never another scheme

    def refused(url, timeout):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr(audit.urllib.request, "urlopen", refused)
    assert not audit.reachable(APP)

    def status(url, timeout):
        raise urllib.error.HTTPError(url, 404, "not found", {}, None)

    monkeypatch.setattr(audit.urllib.request, "urlopen", status)
    assert audit.reachable(APP)


def test_post_json_sends_json_and_reads_the_answer(monkeypatch):
    sent = []

    class Answer:
        def __init__(self, body):
            self.body = body

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return self.body

    def urlopen(request, timeout):
        sent.append((request.full_url, request.get_method(), request.data, request.get_header("Content-type")))
        return Answer(b'{"access_token": "x"}' if request.full_url.endswith("/login") else b"")

    monkeypatch.setattr(audit.urllib.request, "urlopen", urlopen)
    assert audit.post_json(f"{APP}/login", {"a": 1}) == {"access_token": "x"}
    assert audit.post_json(f"{APP}/setup", {}) == {}
    assert sent[0] == (f"{APP}/login", "POST", b'{"a": 1}', "application/json")
    with pytest.raises(ValueError, match="not an http"):
        audit.post_json("file:///etc/passwd", {})


def test_main_runs_dast_into_its_own_results(tmp_path, monkeypatch, capsys):
    (tmp_path / "crissp/testsuite").mkdir(parents=True)
    (tmp_path / "crissp/testsuite/suites.json").write_text(json.dumps({"steps": [], "audit": CONF}))
    monkeypatch.setattr(audit, "runner", Docker(CLEAN))
    monkeypatch.setattr(audit, "reachable", up)
    monkeypatch.setattr(audit, "canary_server", canary)
    assert audit.main(["audit.py", "dast"], tmp_path) == 0
    assert json.loads((tmp_path / "crissp/testsuite/results/dast.json").read_text())["kind"] == "dast"
    assert "No high or medium risk" in capsys.readouterr().out
