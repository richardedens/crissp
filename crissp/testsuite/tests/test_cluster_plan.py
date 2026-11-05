"""crissp/deploy.sh --cluster: what stops a cluster deploy before anything changes, what goes into the private values
and Terraform files (and what never goes into a log), and the steps it takes. Every product-specific setting comes from
crissp/deploy/deploy.json; nothing about a product, a cluster or a registry is written in the code."""

import copy
import importlib.util
import json
import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

SUITE = Path(__file__).resolve().parents[1]
CRISSP = SUITE.parent
ROOT = CRISSP.parent
LIB = SUITE / "lib" / "cluster_plan.py"
DEPLOY_SH = CRISSP / "deploy.sh"
DEPLOY_JSON = CRISSP / "deploy" / "deploy.json"


def _module():
    spec = importlib.util.spec_from_file_location("cluster_plan_under_test", LIB)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cp = _module()

# A filled-in product: reserved test names only (RFC 2606), never a real host.
CONFIG = {
    "product": "shop",
    "cluster": {
        "chart": "crissp/deploy/helm/app",
        "release": "shop",
        "namespace": "shop",
        "kubeContext": "shop-cluster",
        "kubeconfig": "",
        "domains": {"primary": "shop.test", "redirects": ["www.shop.test"]},
        "image": {"repository": "registry.test/team/shop", "platform": "linux/amd64",
                  "parts": {"backend": "app/backend", "frontend": "app/frontend"}},
        "health": "https://shop.test/api/health",
        "pullSecret": {"name": "registry-credentials", "sourceNamespace": ""},
        "terraform": "crissp/deploy/terraform",
        "values": {"database": {"enabled": True}},
        "env": {
            "file": ".env.production",
            "example": "crissp/deploy/.env.production.example",
            "secrets": ["DB_PASSWORD", "APP_SECRET_KEY", "MAIL_PASSWORD"],
            "settings": ["MAIL_HOST", "MAIL_USER"],
            "required": ["DB_PASSWORD", "APP_SECRET_KEY", "MAIL_HOST"],
            "rules": {"DB_PASSWORD": {"minLength": 20}, "APP_SECRET_KEY": {"minLength": 32},
                      "MAIL_HOST": {"pattern": "[a-z0-9.-]+", "message": "MAIL_HOST must be a host name"}},
            "registry": {"server": "REGISTRY_SERVER", "username": "REGISTRY_USERNAME", "password": "REGISTRY_PASSWORD"},
        },
    },
}
GOOD = {
    "DB_PASSWORD": "db-secret-0123456789abcdef",
    "APP_SECRET_KEY": "app-secret-0123456789abcdef0123456789",
    "MAIL_PASSWORD": "mail-secret-value",
    "MAIL_HOST": "smtp.shop.test",
    "MAIL_USER": "hello@shop.test",
    "REGISTRY_SERVER": "registry.test",
    "REGISTRY_USERNAME": "robot",
    "REGISTRY_PASSWORD": "registry-secret-value",
}
SECRETS = ("db-secret-0123456789abcdef", "app-secret-0123456789abcdef0123456789", "mail-secret-value",
           "registry-secret-value")


def cfg(**cluster):
    out = copy.deepcopy(CONFIG)
    out["cluster"].update(cluster)
    return out


# ------------------------------------------------------------------------------------------------ the settings

def test_nothing_product_specific_is_written_in_the_code():
    text = LIB.read_text()
    for name in ("CLUSTER =", "NAMESPACE =", "REPOSITORY =", "HOST =", "LOAD_BALANCER"):
        assert name not in text, name
    assert not re.search(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", text)  # no address of any cluster


def test_the_settings_are_read_from_deploy_json():
    loaded = cp.load_config(DEPLOY_JSON)
    for key in ("chart", "release", "namespace", "kubeContext", "domains", "image", "health", "pullSecret", "env"):
        assert key in loaded["cluster"], key


def test_the_example_deploy_json_is_neutral_and_never_deploys():
    """The settings that ship with C.R.I.S.S.P. are reserved example names: they stop a deploy until filled in."""
    example = cp.load_config(DEPLOY_JSON)
    found = cp.config_stops(example)
    assert any("example" in s and "deploy.json" in s for s in found), found


def test_a_filled_in_config_has_no_stops():
    assert cp.config_stops(CONFIG) == []


@pytest.mark.parametrize("change, stop", [
    ({"kubeContext": ""}, "cluster.kubeContext is empty in deploy.json"),
    ({"namespace": "Not A Namespace"}, "cluster.namespace must be a Kubernetes name"),
    ({"release": ""}, "cluster.release must be a Kubernetes name"),
    ({"domains": {"primary": "app.example.org", "redirects": []}}, "still holds the example settings"),
    ({"image": {"repository": "registry.example.com/x/y", "platform": "linux/amd64", "parts": {"backend": "b"}}},
     "still holds the example settings"),
    ({"image": {"repository": "registry.test/x", "platform": "linux/amd64", "parts": {"worker": "w"}}},
     "cluster.image.parts: the chart knows backend and frontend, not worker"),
    ({"image": {"repository": "registry.test/x", "platform": "linux/amd64", "parts": {}}},
     "cluster.image.parts is empty"),
    ({"health": "http://shop.test/api/health"}, "cluster.health must be an https:// address"),
    ({"values": {"secrets": {"A": "b"}}}, "cluster.values may not hold secrets"),
])
def test_each_wrong_setting_stops_it_by_name(change, stop):
    assert any(stop in s for s in cp.config_stops(cfg(**change))), cp.config_stops(cfg(**change))


def test_a_missing_or_broken_deploy_json_is_said_plainly(tmp_path):
    with pytest.raises(ValueError, match="deploy.json is missing"):
        cp.load_config(tmp_path / "deploy.json")
    (tmp_path / "deploy.json").write_text("{nope")
    with pytest.raises(ValueError, match="deploy.json is not valid JSON"):
        cp.load_config(tmp_path / "deploy.json")


# ------------------------------------------------------------------------------------------------ .env.production

def test_the_env_file_is_read_without_quotes_comments_or_export():
    text = "# comment\nexport A=1\nB=\"two words\"\nC='x=y'\n\nD=\n"
    assert cp.read_env(text) == {"A": "1", "B": "two words", "C": "x=y", "D": ""}


def test_a_complete_env_has_no_stops():
    assert cp.env_stops(GOOD, CONFIG) == []


def test_each_missing_or_wrong_setting_stops_the_deploy_by_name_never_by_value():
    bad = {**GOOD, "DB_PASSWORD": "short", "APP_SECRET_KEY": "", "MAIL_HOST": "Not A Host!"}
    found = cp.env_stops(bad, CONFIG)
    assert "APP_SECRET_KEY is empty in .env.production" in found
    assert "DB_PASSWORD must be at least 20 characters" in found
    assert "MAIL_HOST must be a host name" in found
    assert not any("short" in s or "Not A Host" in s for s in found)


def test_a_prefix_rule_and_a_pattern_without_its_own_message():
    rules = cfg(env={**CONFIG["cluster"]["env"], "rules": {"APP_SECRET_KEY": {"prefix": "live_"},
                                                             "MAIL_HOST": {"pattern": "[0-9]+"}}})
    found = cp.env_stops(GOOD, rules)
    assert "APP_SECRET_KEY must start with live_" in found
    assert "MAIL_HOST does not have the expected form" in found


def test_without_the_file_the_only_stop_says_how_to_make_it():
    assert cp.env_stops(None, CONFIG) == [
        ".env.production is missing: copy crissp/deploy/.env.production.example and fill it in (never commit it)"]


def test_the_example_env_names_every_setting_and_holds_no_value():
    real = cp.load_config(DEPLOY_JSON)["cluster"]["env"]
    example = cp.read_env((ROOT / real["example"]).read_text())
    named = set(real["secrets"]) | set(real["settings"]) | set(real["required"]) | set(real["registry"].values())
    assert named <= set(example)
    assert all(v == "" for v in example.values())


# ------------------------------------------------------------------------------------------------ images and values

def test_the_image_tag_carries_the_commit_so_a_node_never_runs_an_old_build():
    assert cp.image_version("0.1.0", "abcdef0123456789") == "0.1.0-abcdef01"
    assert cp.images(CONFIG, "0.1.0-abcdef01") == [
        ("backend", "registry.test/team/shop:backend-0.1.0-abcdef01", "app/backend"),
        ("frontend", "registry.test/team/shop:frontend-0.1.0-abcdef01", "app/frontend")]


def test_the_values_carry_the_settings_the_secrets_and_which_parts_exist():
    v = cp.values(GOOD, CONFIG, "0.1.0-abcdef01")
    assert v["image"] == {"repository": "registry.test/team/shop", "version": "0.1.0-abcdef01"}
    assert v["host"] == "shop.test" and v["redirectHosts"] == ["www.shop.test"]
    assert v["imagePullSecrets"] == [{"name": "registry-credentials"}]
    assert v["backend"] == {"enabled": True} and v["frontend"] == {"enabled": True}
    assert v["env"] == {"MAIL_HOST": "smtp.shop.test", "MAIL_USER": "hello@shop.test"}
    assert v["secrets"] == {"DB_PASSWORD": GOOD["DB_PASSWORD"], "APP_SECRET_KEY": GOOD["APP_SECRET_KEY"],
                            "MAIL_PASSWORD": GOOD["MAIL_PASSWORD"]}
    assert v["database"] == {"enabled": True}  # from cluster.values
    assert "REGISTRY_PASSWORD" not in json.dumps(v)  # the registry is Terraform's, never the chart's


def test_a_product_without_a_frontend_says_so_to_the_chart():
    only = cfg(image={"repository": "registry.test/x", "platform": "linux/amd64", "parts": {"backend": "."}})
    assert cp.values(GOOD, only, "1")["frontend"] == {"enabled": False}
    assert [i[0] for i in cp.images(only, "1")] == ["backend"]


def test_an_optional_setting_left_empty_is_not_passed():
    v = cp.values({**GOOD, "MAIL_USER": "", "MAIL_PASSWORD": ""}, CONFIG, "1")
    assert "MAIL_USER" not in v["env"] and "MAIL_PASSWORD" not in v["secrets"]  # the cluster keeps what it has


def test_the_private_files_are_written_for_the_owner_only(tmp_path):
    path = tmp_path / "values.json"
    cp.write_private(path, cp.values(GOOD, CONFIG, "0.1.0-abcdef01"))
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert json.loads(path.read_text())["secrets"]["MAIL_PASSWORD"] == "mail-secret-value"


def test_the_terraform_variables_come_from_the_settings_and_the_env(tmp_path):
    t = cp.tfvars(GOOD, CONFIG, tmp_path / "kubeconfig")
    assert t["namespace"] == "shop" and t["kube_context"] == "shop-cluster"
    assert t["kubeconfig_path"] == str(tmp_path / "kubeconfig")
    assert t["pull_secret_name"] == "registry-credentials" and t["create_pull_secret"] is True
    assert (t["registry_server"], t["registry_username"], t["registry_password"]) == (
        "registry.test", "robot", "registry-secret-value")
    assert t["labels"]["app.kubernetes.io/part-of"] == "shop"
    without = cp.tfvars({k: v for k, v in GOOD.items() if not k.startswith("REGISTRY_")}, CONFIG, None)
    assert without["create_pull_secret"] is False and without["registry_password"] == ""
    assert "kubeconfig_path" not in without


# ------------------------------------------------------------------------------------------------ the kubeconfig

def test_the_kubeconfig_is_kubeconfig_then_the_configured_one_then_the_default(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (tmp_path / "home/.kube").mkdir(parents=True)
    (tmp_path / "home/.kube/config").write_text("x")
    assert cp.find_kubeconfig(root, {"HOME": str(tmp_path / "home")}, CONFIG) == tmp_path / "home/.kube/config"
    (root / "kube.yml").write_text("x")
    assert cp.find_kubeconfig(root, {"HOME": str(tmp_path / "home")}, cfg(kubeconfig="kube.yml")) == root / "kube.yml"
    (tmp_path / "own.yml").write_text("x")
    assert cp.find_kubeconfig(root, {"KUBECONFIG": str(tmp_path / "own.yml")}, CONFIG) == tmp_path / "own.yml"
    assert cp.find_kubeconfig(tmp_path / "nowhere", {"HOME": str(tmp_path / "nohome")}, CONFIG) is None


# ------------------------------------------------------------------------------------------------ the plan

def test_the_plan_names_every_step_and_no_secret():
    text = cp.render_plan(GOOD, CONFIG, version="0.1.0", commit="abcdef0123456789", kubeconfig="/k/config",
                          terraform=True)
    for step in ("terraform plan", "terraform apply", "crissp/deploy/terraform",
                 "docker buildx build --platform linux/amd64 --push -t registry.test/team/shop:backend-0.1.0-abcdef01 app/backend",
                 "registry.test/team/shop:frontend-0.1.0-abcdef01",
                 "helm upgrade --install shop crissp/deploy/helm/app --namespace shop --kube-context shop-cluster",
                 "kubectl -n shop rollout status deployment/shop-backend", "deployment/shop-frontend",
                 "https://shop.test/api/health", "context shop-cluster"):
        assert step in text, step
    assert not any(s in text for s in SECRETS)


def test_without_terraform_the_plan_says_it_is_skipped_and_what_happens_instead():
    text = cp.render_plan(GOOD, CONFIG, "0.1.0", "a" * 40, "/k/config", terraform=False)
    assert "skipped: terraform not installed" in text
    assert "namespace shop (created if missing)" in text
    assert "pull secret registry-credentials must already be in namespace shop" in text
    copied = cp.render_plan(GOOD, cfg(pullSecret={"name": "pull", "sourceNamespace": "shared"}), "0.1.0", "a" * 40,
                            "/k/config", terraform=False)
    assert "pull secret pull (copied from namespace shared when missing)" in copied


def test_the_plan_shows_the_stops_and_says_nothing_will_change():
    text = cp.render_plan({**GOOD, "DB_PASSWORD": ""}, CONFIG, "0.1.0", "a" * 40, kubeconfig=None, terraform=True)
    assert "DB_PASSWORD is empty in .env.production" in text
    assert "no kubeconfig found: set KUBECONFIG or cluster.kubeconfig in deploy.json" in text
    assert "Not deploying: nothing in the registry or the cluster is changed." in text


def test_the_shell_variables_carry_the_settings_quoted():
    lines = cp.render_shell(CONFIG, "/k/my config").splitlines()
    assert "CP_RELEASE=shop" in lines and "CP_NAMESPACE=shop" in lines and "CP_CONTEXT=shop-cluster" in lines
    assert "CP_KUBECONFIG='/k/my config'" in lines and "CP_PARTS='backend frontend'" in lines
    assert "CP_CHART=crissp/deploy/helm/app" in lines and "CP_HEALTH=https://shop.test/api/health" in lines
    assert "CP_PULL_SECRET=registry-credentials" in lines and "CP_PULL_SOURCE=''" in lines
    assert "CP_TERRAFORM=crissp/deploy/terraform" in lines and "CP_PLATFORM=linux/amd64" in lines


# ------------------------------------------------------------------------------------------------ the command line

def _files(tmp_path, env=GOOD, config=CONFIG):
    (tmp_path / "deploy.json").write_text(json.dumps(config))
    (tmp_path / ".env.production").write_text("\n".join(f"{k}={v}" for k, v in env.items()))
    return ["--config", str(tmp_path / "deploy.json"), "--env", str(tmp_path / ".env.production")]


def test_the_plan_runs_from_the_command_line_without_secrets(tmp_path):
    args = _files(tmp_path)
    done = subprocess.run(["python3", str(LIB), "plan", *args, "--version", "0.1.0", "--commit", "b" * 40],
                          capture_output=True, text=True, check=False,
                          env={**os.environ, "KUBECONFIG": str(tmp_path / "deploy.json")})
    assert done.returncode == 0, done.stdout + done.stderr
    assert "helm upgrade --install shop" in done.stdout and not any(s in done.stdout for s in SECRETS)
    missing = subprocess.run(["python3", str(LIB), "plan", "--config", args[1], "--env", str(tmp_path / "nope"),
                              "--version", "0.1.0", "--commit", "b" * 40], capture_output=True, text=True, check=False)
    assert missing.returncode == 1 and ".env.production is missing" in missing.stdout


def test_the_plan_command_answers_1_with_stops_or_without_a_kubeconfig_and_0_when_clear(tmp_path, monkeypatch, capsys):
    args = ["plan", *_files(tmp_path), "--version", "0.1.0", "--commit", "c" * 40]
    monkeypatch.setenv("KUBECONFIG", str(tmp_path / "deploy.json"))  # any file that exists stands in for it
    assert cp.main(args) == 0 and "Nothing stops it." in capsys.readouterr().out
    monkeypatch.setattr(cp, "find_kubeconfig", lambda root, environ, config: None)
    assert cp.main(args) == 1 and "no kubeconfig found" in capsys.readouterr().out


def test_a_broken_config_stops_every_command(tmp_path, capsys):
    (tmp_path / "deploy.json").write_text("{")
    assert cp.main(["plan", "--config", str(tmp_path / "deploy.json"), "--version", "1"]) == 1
    assert "deploy.json is not valid JSON" in capsys.readouterr().err


def test_the_values_and_tfvars_commands_write_only_after_a_clean_plan(tmp_path, monkeypatch):
    args = _files(tmp_path)
    monkeypatch.setenv("KUBECONFIG", str(tmp_path / "deploy.json"))
    out = tmp_path / "values.json"
    assert cp.main(["values", *args, "--version", "0.1.0-abcdef01", "--out", str(out)]) == 0
    assert json.loads(out.read_text())["image"]["version"] == "0.1.0-abcdef01"
    assert stat.S_IMODE(out.stat().st_mode) == 0o600
    tf = tmp_path / "vars.json"
    assert cp.main(["tfvars", *args, "--version", "x", "--out", str(tf)]) == 0
    assert json.loads(tf.read_text())["registry_password"] == "registry-secret-value"
    bad = _files(tmp_path, env={"DB_PASSWORD": ""})
    assert cp.main(["values", *bad, "--version", "x", "--out", str(tmp_path / "no.json")]) == 1
    assert cp.main(["tfvars", *bad, "--version", "x", "--out", str(tmp_path / "no.json")]) == 1
    assert cp.main(["values", *args, "--version", "x"]) == 1  # no --out
    assert not (tmp_path / "no.json").exists()


def test_the_shell_command_prints_the_settings(tmp_path, monkeypatch, capsys):
    args = _files(tmp_path)
    monkeypatch.setenv("KUBECONFIG", str(tmp_path / "deploy.json"))
    assert cp.main(["shell", *args, "--version", "x"]) == 0
    out = capsys.readouterr().out
    assert "CP_RELEASE=shop" in out and not any(s in out for s in SECRETS)


def test_run_as_a_script_it_exits_with_main(tmp_path, monkeypatch):
    import runpy
    import sys
    monkeypatch.setattr(sys, "argv", ["cluster_plan.py", "plan", "--config", str(tmp_path / "none.json"),
                                      "--version", "0.1.0"])
    with pytest.raises(SystemExit) as done:
        runpy.run_path(str(LIB), run_name="__main__")
    assert done.value.code == 1


def test_helm_renders_the_chart_with_the_private_values(tmp_path):
    import shutil
    if shutil.which("helm") is None:
        pytest.skip("helm is not installed")
    out = tmp_path / "values.json"
    cp.write_private(out, cp.values(GOOD, CONFIG, "0.1.0-abcdef01"))
    done = subprocess.run(["helm", "template", "shop", str(ROOT / CONFIG["cluster"]["chart"]), "-n", "shop", "-f", str(out)],
                          capture_output=True, text=True, check=True)
    assert "registry.test/team/shop:backend-0.1.0-abcdef01" in done.stdout
    assert "MAIL_HOST: \"smtp.shop.test\"" in done.stdout
    assert "host: shop.test" in done.stdout


# ------------------------------------------------------------------------------------------------ deploy.sh itself

def _cluster_sh():
    text = DEPLOY_SH.read_text()
    return text[text.index("deploy_cluster()"):]


def test_deploy_sh_takes_the_cluster_route_only_after_the_gate_and_a_yes():
    text = DEPLOY_SH.read_text()
    assert "--cluster)" in text
    cluster = _cluster_sh()
    gate = cluster.index("release.py\" check")
    assert gate < cluster.index("terraform") < cluster.index("read -r") < cluster.index("apply")
    assert cluster.index("read -r") < cluster.index("docker buildx") < cluster.index("helm upgrade")
    assert cluster.index("helm upgrade") < cluster.index("rollout status") < cluster.index("$CP_HEALTH")
    assert "set -x" not in text  # a trace would print the secrets


def test_deploy_sh_keeps_its_private_files_private_and_removes_them():
    cluster = _cluster_sh()
    assert "umask 077" in cluster and "mktemp -d" in cluster
    assert "trap 'rm -rf \"$PRIVATE\"' EXIT" in cluster
    assert "values --config" in cluster and "tfvars --config" in cluster
    assert '-out="$PRIVATE/' in cluster  # the terraform plan holds the secrets too


def test_deploy_sh_skips_terraform_visibly_when_it_is_not_installed():
    cluster = _cluster_sh()
    assert "command -v terraform" in cluster and "skipped: terraform not installed" in cluster


def test_deploy_sh_names_no_product_cluster_or_namespace_to_hunt_in():
    text = DEPLOY_SH.read_text()
    assert "for source in" not in text and "NS=" not in text
    assert "$CP_PULL_SOURCE" in _cluster_sh()  # one configured source namespace, or none
    assert "--kube-context \"$CP_CONTEXT\"" in _cluster_sh() and "--context \"$CP_CONTEXT\"" in _cluster_sh()


def test_deploy_sh_rolls_out_every_part_it_built():
    cluster = _cluster_sh()
    assert "for part in $CP_PARTS" in cluster
    assert 'rollout status "deployment/$CP_RELEASE-$part"' in cluster


def test_without_a_commit_the_plan_stops_and_shows_no_broken_tag():
    text = cp.render_plan(GOOD, CONFIG, "0.1.0", "(no commit yet)", "/k/config", terraform=True)
    assert "no commit to deploy: commit first (the image tag carries the commit)" in text
    assert "(no comm" not in text.replace("(no commit yet)", "") and "<commit>" in text


def test_an_empty_chart_domain_or_repository_stops_it_by_name():
    found = cp.config_stops(cfg(chart="crissp/deploy/helm/none", domains={"redirects": []},
                                image={"repository": "", "parts": {"backend": "."}}))
    assert "cluster.chart: no chart at crissp/deploy/helm/none" in found
    assert "cluster.domains.primary is empty in deploy.json" in found
    assert "cluster.image.repository is empty in deploy.json" in found


def test_an_incomplete_image_setting_is_said_in_the_plan():
    text = cp.render_plan(GOOD, cfg(image={"parts": {"backend": "."}}), "0.1.0", "a" * 40, "/k", terraform=True)
    assert "(no images: cluster.image is incomplete)" in text
