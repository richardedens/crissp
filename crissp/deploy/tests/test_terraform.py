"""crissp/deploy/terraform: the cluster side the chart needs, on the Kubernetes provider only, proven by reading the
files (python-hcl2 is not one of the testsuite's tools, so these are structural checks; terraform fmt -check and
terraform validate run in crissp/deploy/check.sh when terraform is installed)."""

import re

import pytest
from conftest import TERRAFORM

FILES = sorted(TERRAFORM.glob("*.tf"))
TEXT = "\n".join(f.read_text() for f in FILES)


def blocks(kind: str) -> dict[str, str]:
    """name → body of every top-level `kind "name" {…}` (or `kind "type" "name"` for resources: "type.name")."""
    out = {}
    for m in re.finditer(rf'^{kind} "([^"]+)"(?: "([^"]+)")? \{{\n(.*?)^\}}', TEXT, re.MULTILINE | re.DOTALL):
        out[f"{m.group(1)}.{m.group(2)}" if m.group(2) else m.group(1)] = m.group(3)
    return out


def _strip(text: str) -> str:
    """The text without strings, ${…} and comments, for counting braces."""
    text = re.sub(r'"(?:[^"\\]|\\.)*"', '""', text)
    return re.sub(r"#.*", "", text)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_every_file_parses_braces_brackets_and_quotes_balance(path):
    text = path.read_text()
    assert text.count('"') % 2 == 0, path.name
    bare = _strip(text)
    for o, c in ("{}", "[]", "()"):
        depth = 0
        for ch in bare:
            depth += (ch == o) - (ch == c)
            assert depth >= 0, f"{path.name}: {c} without {o}"
        assert depth == 0, f"{path.name}: {o} not closed"
    assert text.endswith("\n") and "\t" not in text  # as terraform fmt leaves it


def test_the_module_has_its_files():
    assert {f.name for f in FILES} == {"versions.tf", "providers.tf", "variables.tf", "main.tf", "outputs.tf"}
    assert (TERRAFORM / "terraform.tfvars.example").is_file()


def test_the_provider_is_kubernetes_only_and_pinned_exactly():
    assert re.search(r'source\s+=\s+"hashicorp/kubernetes"', TEXT)
    assert re.search(r'version\s+=\s+"= \d+\.\d+\.\d+"', TEXT)
    assert re.search(r'required_version\s+=\s+">= 1\.\d+', TEXT)
    providers = set(re.findall(r'^provider "([^"]+)"', TEXT, re.MULTILINE))
    assert providers == {"kubernetes"}
    kinds = {name.split(".")[0] for name in blocks("resource")}
    assert all(k.startswith("kubernetes_") for k in kinds), kinds  # no cloud provider's resources
    assert not re.search(r"\b(aws|google|azurerm|digitalocean|hcloud)_", TEXT)


def test_the_cluster_side_the_chart_needs_is_there():
    resources = blocks("resource")
    assert set(resources) == {"kubernetes_namespace_v1.product", "kubernetes_secret_v1.pull",
                              "kubernetes_network_policy_v1.default_deny", "kubernetes_resource_quota_v1.product",
                              "kubernetes_limit_range_v1.product"}
    ns = resources["kubernetes_namespace_v1.product"]
    assert "pod-security.kubernetes.io/enforce" in ns and "var.labels" in ns
    deny = resources["kubernetes_network_policy_v1.default_deny"]
    assert "pod_selector {}" in deny and 'policy_types = ["Ingress", "Egress"]' in deny
    pull = resources["kubernetes_secret_v1.pull"]
    assert 'type = "kubernetes.io/dockerconfigjson"' in pull and "var.registry_password" in pull
    assert "count = var.create_pull_secret ? 1 : 0" in pull  # a sensitive value can never decide a count


def test_every_variable_has_a_description_and_a_type_and_secrets_are_sensitive():
    variables = blocks("variable")
    assert variables
    for name, body in variables.items():
        assert re.search(r'description\s+=\s+"\S', body), name
        assert re.search(r"\btype\s+=", body), name
    for name in ("registry_password", "registry_username"):
        assert re.search(r"sensitive\s+=\s+true", variables[name]), name
        assert re.search(r'default\s+=\s+""', variables[name]), name  # never a value in the repository


def test_every_variable_used_is_declared_and_every_declared_one_is_used():
    declared = set(blocks("variable"))
    used = set(re.findall(r"\bvar\.([a-z_]+)", TEXT))
    assert used == declared, (used - declared, declared - used)


def test_every_output_has_a_description():
    outputs = blocks("output")
    assert {"namespace", "pull_secret_name"} <= set(outputs)
    for name, body in outputs.items():
        assert re.search(r'description\s+=\s+"\S', body) and "value" in body, name


def test_the_example_tfvars_is_neutral_holds_no_secret_and_names_only_declared_variables():
    text = (TERRAFORM / "terraform.tfvars.example").read_text()
    names = set(re.findall(r"^([a-z_]+)\s+=", text, re.MULTILINE))
    assert names and names <= set(blocks("variable"))
    assert "registry_password" not in names and "registry_username" not in names
    hosts = re.findall(r'"([a-z0-9.-]+\.[a-z]+)"', text)
    assert all(h.endswith("example.org") for h in hosts), hosts


def test_state_plans_and_real_variables_are_never_in_git():
    ignore = (TERRAFORM / ".gitignore").read_text().splitlines()
    for rule in (".terraform/", "*.tfstate", "*.tfstate.*", "*.tfplan", "*.tfvars", "*.tfvars.json", "!*.tfvars.example"):
        assert rule in ignore, rule
