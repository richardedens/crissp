"""crissp's own gitleaks configuration (.gitleaks.toml at the repository root): a made-up value in a test is allowed by
what it is (its file and its value), never by the commit it is in. A commit-bound fingerprint in .gitleaksignore breaks
as soon as the history looks different: a shallow clone (CI, a cloud container) sees the line in its top commit."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TEST = "crissp/testsuite/tests/test_cluster_plan.py"


def config():
    return tomllib.loads((ROOT / ".gitleaks.toml").read_text())


def made_up_key():
    (value,) = re.findall(r'GOOD = \{\s+"DB_PASSWORD": "([^"]+)"', (ROOT / TEST).read_text())
    return value


def test_the_default_rules_stay_on():
    assert config()["extend"]["useDefault"] is True


def test_the_made_up_key_in_the_cluster_plan_test_is_allowed_by_file_and_value():
    allow = [a for a in config()["allowlists"] if any(re.search(p, TEST) for p in a.get("paths", []))]
    (entry,) = allow
    assert entry["condition"] == "AND" and entry["description"]
    assert any(re.search(r, made_up_key()) for r in entry["regexes"])
    # only that value: a real key in the same file is still found
    assert not any(re.search(r, "db-secret-" + "9f8e7d6c5b4a3928") for r in entry["regexes"])
    assert not any(re.search(p, "app/backend/settings.py") for p in entry["paths"])


def test_no_finding_is_ignored_by_its_commit():
    lines = (ROOT / ".gitleaksignore").read_text().splitlines() if (ROOT / ".gitleaksignore").exists() else []
    assert [line for line in lines if line.strip() and not line.startswith("#")] == []
