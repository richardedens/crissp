"""crissp/deploy is a template for any product: it names no product, company, cluster, address or registry of a real
one, and holds no secret value. The names are kept here only as SHA-256 hashes of the lower-case word, so this test
does not name them either (as crissp/testsuite/tests/test_private_names.py does)."""

import hashlib
import ipaddress
import json
import re

import pytest
from conftest import DEPLOY

CRISSP = DEPLOY.parent
PRIVATE = {
    "a7e88c6179b8acc23fa52642b9d88e1c605b4c4edd580a496e8945b3b1117e15",
    "bcc017d98327ac5346afd954b28504e4ebc0f7d807415f2b9b190e59a1603273",
    "6a34ca257c90f92a08cc7c64ffe0dce14454f8382843761a9c574b3a9a00cb81",
    "9cc57c91e044a25c6ec91d81909c53781c9e144da095310b67a0ce7897f9f669",
    "0cbb043abe19b54d875da33d48de6c158a2d5c6cec48f6461e06322eff56455c",
    "b15bcefaebba6cbfb48780ceb810cc90d6f1d42efb0bf9fee384609d8f8b549b",
    "964ca863a05cf6824621ce8948c156f2699020dbed94cddccf079d0254b7ad89",
    "94014089d74724e3c1924940875db7429efde9bb9b6a53efc2dfc729ea85e4a0",
    "92fd26efa9d69872a0bf414ecbfffd063ce6f6ca1947829b0e2cc7189dd0d805",
}
OWNED = [p for p in DEPLOY.rglob("*") if p.is_file() and "__pycache__" not in p.parts and ".terraform" not in p.parts]
OWNED += [CRISSP / "deploy.sh", CRISSP / "testsuite/lib/cluster_plan.py", CRISSP / "testsuite/lib/deploy_plan.py",
          CRISSP / "testsuite/tests/test_cluster_plan.py", CRISSP / "testsuite/tests/test_deploy_plan.py"]
ALLOWED_ADDRESSES = {"0.0.0.0", "127.0.0.1"}


def private_words(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower())) | set(re.findall(r"[a-z0-9]+", text.lower()))
    return {w for w in words if hashlib.sha256(w.encode()).hexdigest() in PRIVATE}


def test_the_guard_finds_a_hashed_name_in_any_case_and_with_a_hyphen():
    name = "liquid" + "-" + "nitro"  # spelled in pieces, so this file never holds the word
    assert private_words(f"see {name.upper()}/x") == {name}
    assert private_words("a liquid, a nitro") == set()


@pytest.mark.parametrize("path", OWNED, ids=lambda p: str(p.relative_to(CRISSP)))
def test_no_private_name(path):
    assert not private_words(path.read_text()) and not private_words(str(path.relative_to(CRISSP))), path


@pytest.mark.parametrize("path", OWNED, ids=lambda p: str(p.relative_to(CRISSP)))
def test_no_public_address_of_a_real_machine(path):
    for found in re.findall(r"(?<![\d.])(\d{1,3}(?:\.\d{1,3}){3})(?![\d.])", path.read_text()):
        try:
            address = ipaddress.ip_address(found)
        except ValueError:
            continue  # four numbers that are no address (one above 255)
        assert found in ALLOWED_ADDRESSES or address.is_private, f"{path.name}: {found}"


SECRETISH = re.compile(r"(password|secret|token|api_?key)[\"']?\s*[:=]\s*[\"']?([^\s\"',}]{6,})", re.IGNORECASE)


@pytest.mark.parametrize("path", [p for p in OWNED if p.suffix in (".yaml", ".json", ".tf", ".example", ".md")
                                  or p.name.startswith(".env")], ids=lambda p: str(p.relative_to(CRISSP)))
def test_no_secret_value_in_a_template_or_setting(path):
    for key, value in SECRETISH.findall(path.read_text()):
        assert value.startswith(("var.", "$", "{{", "<", "true", "false", "sensitive")) or value.isupper(), \
            f"{path.name}: {key} has a value"


def test_the_example_env_has_no_value():
    for line in (DEPLOY / ".env.production.example").read_text().splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            assert value == "", key


def test_deploy_json_is_neutral_and_complete():
    settings = json.loads((DEPLOY / "deploy.json").read_text())
    c = settings["cluster"]
    for key in ("chart", "release", "namespace", "kubeContext", "domains", "image", "health", "pullSecret", "env"):
        assert key in c, key
    hosts = [c["domains"]["primary"], *c["domains"]["redirects"], c["image"]["repository"].split("/")[0],
             re.sub(r"^https://", "", c["health"]).split("/")[0]]
    assert all(h.endswith("example.org") for h in hosts), hosts
    assert (CRISSP.parent / c["chart"]).is_dir() and (CRISSP.parent / c["terraform"]).is_dir()
    assert (CRISSP.parent / c["env"]["example"]).is_file()
    assert settings["compose"]["services"]


def test_the_readme_says_how_to_adopt_it():
    readme = (DEPLOY / "README.md").read_text()
    for needed in ("deploy.json", ".env.production", "--cluster-plan", "--cluster", "release gate", "terraform",
                   "check.sh", "helm/app", "NetworkPolic"):
        assert needed in readme, needed


def test_no_file_here_is_a_real_tfvars_state_or_env():
    names = [p.name for p in OWNED]
    assert not [n for n in names if n.endswith((".tfstate", ".tfplan")) or n in ("terraform.tfvars", ".env.production")]


def test_check_sh_runs_every_guard_and_skips_terraform_visibly():
    text = (DEPLOY / "check.sh").read_text()
    for step in ("helm lint", "helm template", "terraform fmt -check", "validate", "pytest",
                 "skipped: terraform not installed"):
        assert step in text, step
    assert "set -x" not in text and "brew install" not in text and "apt-get" not in text


def test_the_tests_never_install_apply_or_push():
    words = ("helm " + "install", "helm " + "upgrade", "terraform " + "apply", "docker " + "push", "kubectl " + "apply")
    for path in (DEPLOY / "tests").glob("*.py"):
        assert not [w for w in words if w in path.read_text()], path.name
