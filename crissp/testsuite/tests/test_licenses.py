"""crissp/testsuite/lib/audit.py licenses: every dependency's licence checked, and a CycloneDX SBOM of them all.
PyPI is stood in: never a real request in a test."""

import datetime
import importlib.util
import json
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("audit_for_licenses", LIB / "audit.py")
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

TODAY = datetime.date(2026, 11, 28)
NONE = {"accepted": []}
LOCK = {"lockfileVersion": 3, "packages": {
    "": {"name": "shop-web", "version": "1.0.0"},
    "node_modules/react": {"version": "19.2.0", "license": "MIT"},
    "node_modules/@scope/chart": {"version": "2.0.0", "license": "GPL-3.0-only"},
    "node_modules/eslint-thing": {"version": "1.0.0", "license": "AGPL-3.0-only", "dev": True},
    "node_modules/old": {"version": "0.1.0", "license": {"type": "MPL-2.0"}},
    "node_modules/twice": {"version": "0.2.0", "license": ["MIT", "Apache-2.0"]},
    "node_modules/nameless": {"version": "0.3.0"}}}
PYPI = {"fastapi==0.121.0": "MIT", "psycopg==3.2.0": "LGPL-3.0-only"}


def lookup(name, version):
    return PYPI[f"{name}=={version}"]


def uv(argv, cwd):
    """uv pip compile, stood in: the requirements resolved are the file as it is (here every pin is already there)."""
    assert argv[:3] == ["uv", "pip", "compile"] and "--python-version" in argv
    out = Path(argv[argv.index("-o") + 1])
    out.write_text((cwd / argv[-3]).read_text())
    return 0, "", ""


def unresolvable(argv, cwd):
    return 1, "", "No solution found: fastapi==0.1 and fastapi==0.2"


@pytest.fixture
def shop(tmp_path):
    (tmp_path / "app/frontend").mkdir(parents=True)
    (tmp_path / "app/frontend/package-lock.json").write_text(json.dumps(LOCK))
    (tmp_path / "app/backend").mkdir(parents=True)
    (tmp_path / "app/backend/requirements.txt").write_text(
        "# the backend\nfastapi==0.121.0\npsycopg[binary]==3.2.0  ; python_version >= '3.12'\n-r more.txt\n")
    (tmp_path / "VERSION").write_text("1.4.0\n")
    return tmp_path


CONF = {"pip": ["app/backend/requirements.txt"], "npm": ["app/frontend"]}


@pytest.mark.parametrize("expression, kind", [
    ("MIT", "permissive"), ("Apache-2.0", "permissive"), ("BSD-3-Clause", "permissive"), ("MIT OR GPL-3.0-only", "permissive"),
    ("(MIT AND GPL-2.0-only)", "copyleft"), ("GPL-2.0+", "copyleft"), ("LGPL-2.1-or-later", "weak copyleft"),
    ("MPL-2.0", "weak copyleft"), ("AGPL-3.0-only", "forbidden"), ("SSPL-1.0", "forbidden"), ("BUSL-1.1", "forbidden"),
    ("GPL-2.0-only WITH Classpath-exception-2.0", "copyleft"), ("", "unknown"), ("SEE LICENSE IN LICENSE", "unknown")])
def test_a_licence_expression_is_as_free_as_its_best_choice_and_its_worst_part(expression, kind):
    assert audit.kind(expression) == kind


def test_npm_components_come_from_the_lock_file_with_their_licence():
    found = {c["name"]: (c["version"], c["licence"], c["dev"]) for c in audit.npm_components(LOCK, "app/frontend")}
    assert found == {"react": ("19.2.0", "MIT", False), "@scope/chart": ("2.0.0", "GPL-3.0-only", False),
                     "eslint-thing": ("1.0.0", "AGPL-3.0-only", True), "old": ("0.1.0", "MPL-2.0", False),
                     "twice": ("0.2.0", "MIT OR Apache-2.0", False), "nameless": ("0.3.0", "", False)}


def test_a_pypi_licence_is_its_spdx_expression_else_a_short_licence_else_its_classifiers():
    assert audit.pypi_licence({"license_expression": "Apache-2.0", "license": "whatever"}) == "Apache-2.0"
    assert audit.pypi_licence({"license": "MIT"}) == "MIT"
    full = "Permission is hereby granted, free of charge, to any person obtaining a copy\nof this software"
    assert audit.pypi_licence({"license": full, "classifiers": ["License :: OSI Approved :: MIT License",
                                                                 "Programming Language :: Python"]}) == "MIT"
    assert audit.pypi_licence({"classifiers": ["License :: OSI Approved :: BSD License",
                                               "License :: OSI Approved :: Apache Software License"]}) == \
        "Apache-2.0 OR BSD-3-Clause"
    assert audit.pypi_licence({"license": "Custom terms", "classifiers": []}) == "Custom terms"
    assert audit.pypi_licence({}) == ""


def test_pypi_is_asked_once_per_release_and_kept_in_the_cache(tmp_path):
    asked = []

    def fetch(url):
        asked.append(url)
        return json.dumps({"info": {"license_expression": "MIT"}}).encode()

    cache = tmp_path / "cache/licenses/pypi.json"
    assert audit.pypi_lookup(cache, fetch)("FastAPI", "0.121.0") == "MIT"
    assert audit.pypi_lookup(cache, fetch)("fastapi", "0.121.0") == "MIT"
    assert asked == ["https://pypi.org/pypi/FastAPI/0.121.0/json"]
    assert json.loads(cache.read_text()) == {"fastapi==0.121.0": "MIT"}


def test_copyleft_and_forbidden_licences_block_weak_and_unknown_are_listed_dev_only_never_blocks(shop):
    report, _ = audit.licenses_all(shop, uv, TODAY, NONE, CONF, lookup)
    rows = sorted((f["package"], f["id"], f["severity"], f["blocks"]) for f in report["findings"])
    assert rows == [("@scope/chart", "GPL-3.0-only", "HIGH", True),
                    ("eslint-thing", "AGPL-3.0-only", "CRITICAL", False),
                    ("nameless", "no licence", "MEDIUM", False),
                    ("old", "MPL-2.0", "MEDIUM", False),
                    ("psycopg", "LGPL-3.0-only", "MEDIUM", False)]
    assert report["scanned"] == ["licences app/frontend/package-lock.json", "licences app/backend/requirements.txt"]
    assert report["components"] == 8 and report["problems"] == []
    said = audit.render(report)
    assert "BLOCKING HIGH     GPL-3.0-only  @scope/chart 2.0.0  (app/frontend): copyleft licence" in said
    assert "dev only, never shipped" in said and "audit.licenses.allow" in said


def test_a_package_allowed_with_why_and_more_licences_blocked_by_the_project(shop):
    conf = {**CONF, "licenses": {"allow": {"@scope/chart": "bought a commercial licence (contract 12)"},
                                 "block": ["MPL-2.0"]}}
    report, _ = audit.licenses_all(shop, uv, TODAY, NONE, conf, lookup)
    assert [(f["package"], f["severity"]) for f in report["blocking"]] == [("old", "CRITICAL")]
    chart = next(f for f in report["findings"] if f["package"] == "@scope/chart")
    assert not chart["blocks"] and chart["fixed"] == "allowed: bought a commercial licence (contract 12)"


def test_the_sbom_is_cyclonedx_with_every_component_its_purl_and_licence(shop):
    _, bom = audit.licenses_all(shop, uv, TODAY, NONE, {**CONF, "licenses": {"product": "Shop"}}, lookup)
    assert (bom["bomFormat"], bom["specVersion"]) == ("CycloneDX", "1.6")
    assert bom["metadata"]["component"] == {"type": "application", "name": "Shop", "version": "1.4.0"}
    by = {c["name"]: c for c in bom["components"]}
    assert by["@scope/chart"]["purl"] == "pkg:npm/%40scope/chart@2.0.0"
    assert by["fastapi"] == {"type": "library", "name": "fastapi", "version": "0.121.0", "purl": "pkg:pypi/fastapi@0.121.0",
                             "scope": "required", "licenses": [{"expression": "MIT"}]}
    assert by["eslint-thing"]["scope"] == "excluded" and "licenses" not in by["nameless"]
    assert audit.licenses_all(shop / "app", uv, TODAY, NONE, {}, lookup)[1]["metadata"]["component"] == {
        "type": "application", "name": "app", "version": ""}


def test_a_place_that_is_not_there_is_absent_or_a_problem_and_an_unpinned_line_is_a_problem(tmp_path):
    conf = {"pip": ["app/backend/requirements.txt"], "npm": ["app/frontend"]}
    report, _ = audit.licenses_all(tmp_path, uv, TODAY, NONE, {**conf, "missing": "skip"}, lookup)
    assert report["absent"] == ["app/frontend/package-lock.json", "app/backend/requirements.txt"]
    assert "Nothing to" in audit.render(report)
    report, _ = audit.licenses_all(tmp_path, uv, TODAY, NONE, conf, lookup)
    assert report["problems"] == ["app/frontend/package-lock.json", "app/backend/requirements.txt"]
    (tmp_path / "app/backend").mkdir(parents=True)
    (tmp_path / "app/backend/requirements.txt").write_text("fastapi>=0.100\n")
    report, _ = audit.licenses_all(tmp_path, uv, TODAY, NONE, {"pip": conf["pip"]}, lookup)
    assert report["problems"] == ["app/backend/requirements.txt: fastapi>=0.100 is not pinned (name==version): its "
                                  "licence cannot be known"]


def test_requirements_are_resolved_with_every_transitive_package_first(shop):
    report, _ = audit.licenses_all(shop, unresolvable, TODAY, NONE, {"pip": CONF["pip"]}, lookup)
    assert report["problems"] == ["app/backend/requirements.txt: could not resolve the requirements (exit 1): No "
                                  "solution found: fastapi==0.1 and fastapi==0.2"]
    assert report["scanned"] == []


def test_pypi_that_cannot_answer_is_a_problem_never_a_pass(shop):
    def offline(name, version):
        raise OSError("network unreachable")

    report, _ = audit.licenses_all(shop, uv, TODAY, NONE, {"pip": CONF["pip"]}, offline)
    assert report["problems"] == ["app/backend/requirements.txt: the licences could not be read from PyPI: "
                                  "network unreachable"]


def test_a_clean_report_says_where_the_sbom_is(shop):
    (shop / "app/backend/requirements.txt").write_text("fastapi==0.121.0\n")
    report, _ = audit.licenses_all(shop, uv, TODAY, NONE, {"pip": CONF["pip"]}, lookup)
    assert audit.render(report).splitlines()[-1] == "No licence blocks: 1 component in results/sbom.cdx.json (0 listed)."


def test_main_writes_the_licences_and_the_sbom(shop, monkeypatch, capsys):
    (shop / "crissp/testsuite").mkdir(parents=True)
    (shop / "crissp/testsuite/suites.json").write_text(json.dumps({"steps": [], "audit": CONF}))
    monkeypatch.setenv("CRISSP_CACHE", str(shop / "cache"))
    monkeypatch.setattr(audit, "pypi_lookup", lambda cache, fetcher=None: lookup)
    monkeypatch.setattr(audit, "runner", uv)
    assert audit.main(["audit.py", "licenses"], shop) == 1  # the GPL chart blocks
    results = shop / "crissp/testsuite/results"
    assert json.loads((results / "licenses.json").read_text())["kind"] == "licenses"
    assert json.loads((results / "sbom.cdx.json").read_text())["bomFormat"] == "CycloneDX"
    assert "BLOCKING" in capsys.readouterr().out
