"""crissp/deploy/helm/app: what the generic chart puts into the cluster, proven by rendering it, never by installing it.
Every product setting (name, images, domains, ports, env, which parts exist) comes from the values."""

import base64
import re
import subprocess

import pytest
import yaml
from conftest import CHART, HELM, one, pods, render

REDIRECTS = ["www.shop.test", "shop-other.test"]
SETS = ("product=shop", "image.repository=registry.test/team/shop", "image.version=1.2.3", "host=shop.test",
        "redirectHosts={www.shop.test,shop-other.test}", "imagePullSecrets[0].name=pull")


@pytest.fixture(scope="module")
def docs():
    return render(*SETS)


@pytest.fixture(scope="module")
def example():
    return render()


def kinds(docs):
    return sorted(f"{d['kind']}/{d['metadata']['name']}" for d in docs)


# ------------------------------------------------------------------------------------------------ lint and parts

@pytest.mark.parametrize("extra", [[], ["-f", str(CHART / "ci" / "backend-only-values.yaml")]])
def test_helm_lint_passes(extra):
    done = subprocess.run([HELM, "lint", str(CHART), *extra], capture_output=True, text=True, check=False)
    assert done.returncode == 0, done.stdout + done.stderr


def test_the_chart_holds_every_part(docs):
    for wanted in ("Deployment/shop-backend", "Deployment/shop-frontend", "StatefulSet/shop-postgresql",
                   "Service/shop-backend", "Service/shop-frontend", "Service/shop-postgresql",
                   "Secret/shop-secret", "ConfigMap/shop-config", "CronJob/shop-backup",
                   "PersistentVolumeClaim/shop-backup", "Ingress/shop", "Ingress/shop-redirect",
                   "Middleware/shop-headers", "Middleware/shop-body-size", "Middleware/shop-ratelimit",
                   "Middleware/shop-redirect", "NetworkPolicy/shop-app", "NetworkPolicy/shop-postgresql",
                   "NetworkPolicy/shop-backup", "NetworkPolicy/shop-backend-egress"):
        assert wanted in kinds(docs), wanted


def test_the_example_values_render_and_name_no_real_host(example):
    ing = one(example, "Ingress", "shop")
    assert ing["spec"]["rules"][0]["host"].endswith("example.org")


def test_a_product_with_only_a_backend_and_no_database():
    docs = render(values=[CHART / "ci" / "backend-only-values.yaml"])
    names = kinds(docs)
    assert "Deployment/shop-backend" in names and not any("frontend" in n or "postgresql" in n or "backup" in n
                                                          for n in names)
    (rule,) = one(docs, "Ingress", "shop")["spec"]["rules"]
    assert [(p["path"], p["backend"]["service"]["name"]) for p in rule["http"]["paths"]] == [("/", "shop-backend")]
    assert one(docs, "NetworkPolicy", "shop-app")["spec"]["podSelector"]["matchExpressions"][0]["values"] == ["backend"]
    egress = one(docs, "NetworkPolicy", "shop-app")["spec"]["egress"]
    assert sorted(p["port"] for r in egress for p in r["ports"]) == [53, 53]  # no database: only DNS
    (c,) = one(docs, "Deployment", "shop-backend")["spec"]["template"]["spec"]["containers"]
    assert not any(e["name"] in ("DATABASE_URL", "DB_PASSWORD", "PGHOST") for e in c["env"])


def test_a_static_site_with_only_a_frontend():
    docs = render("backend.enabled=false", "database.enabled=false")
    names = kinds(docs)
    assert "Deployment/shop-frontend" in names and "Deployment/shop-backend" not in names
    assert "NetworkPolicy/shop-backend-egress" not in names
    (rule,) = one(docs, "Ingress", "shop")["spec"]["rules"]
    assert [(p["path"], p["backend"]["service"]["name"]) for p in rule["http"]["paths"]] == [("/", "shop-frontend")]


def test_no_part_at_all_is_refused():
    with pytest.raises(AssertionError, match="enable at least one part"):
        render("backend.enabled=false", "frontend.enabled=false")
    with pytest.raises(AssertionError, match="host is empty"):
        render("host=")


# ------------------------------------------------------------------------------------------------ Traefik

def test_the_product_is_served_by_traefik_on_its_host_with_a_certificate(docs):
    ing = one(docs, "Ingress", "shop")
    assert ing["spec"]["ingressClassName"] == "traefik"
    assert ing["metadata"]["annotations"]["cert-manager.io/cluster-issuer"] == "letsencrypt"
    assert ing["spec"]["tls"] == [{"hosts": ["shop.test"], "secretName": "shop-tls"}]
    (rule,) = ing["spec"]["rules"]
    assert rule["host"] == "shop.test"
    routes = {p["path"]: (p["pathType"], p["backend"]["service"]["name"]) for p in rule["http"]["paths"]}
    assert routes == {"/api": ("Prefix", "shop-backend"), "/": ("Prefix", "shop-frontend")}
    middlewares = ing["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.middlewares"].split(",")
    assert middlewares == ["shop-shop-headers@kubernetescrd", "shop-shop-body-size@kubernetescrd",
                           "shop-shop-ratelimit@kubernetescrd"]


def test_the_backend_path_and_the_issuer_follow_the_values():
    docs = render(*SETS, "backend.path=/v1", "clusterIssuer=")
    ing = one(docs, "Ingress", "shop")
    assert "cert-manager.io/cluster-issuer" not in ing["metadata"]["annotations"]
    assert ing["spec"]["rules"][0]["http"]["paths"][0]["path"] == "/v1"


def test_the_other_domains_go_to_the_host_permanently(docs):
    ing = one(docs, "Ingress", "shop-redirect")
    assert [r["host"] for r in ing["spec"]["rules"]] == REDIRECTS
    assert ing["spec"]["tls"] == [{"hosts": REDIRECTS, "secretName": "shop-redirect-tls"}]  # never blocks the host's
    assert ing["metadata"]["annotations"]["traefik.ingress.kubernetes.io/router.middlewares"] == \
        "shop-shop-redirect@kubernetescrd"
    redirect = one(docs, "Middleware", "shop-redirect")["spec"]["redirectRegex"]
    assert redirect == {"regex": "^https?://[^/]+(.*)$", "replacement": "https://shop.test${1}", "permanent": True}
    assert not [d for d in render("redirectHosts=null") if "redirect" in d["metadata"]["name"]]


def test_security_headers_upload_limit_and_rate_limit_are_traefik_middlewares(docs):
    headers = one(docs, "Middleware", "shop-headers")["spec"]["headers"]
    assert headers["stsSeconds"] == 31536000 and headers["frameDeny"] is True and headers["contentTypeNosniff"] is True
    assert headers["contentSecurityPolicy"].startswith("default-src 'self'")
    assert headers["referrerPolicy"] == "strict-origin-when-cross-origin"
    assert one(docs, "Middleware", "shop-body-size")["spec"] == {"buffering": {"maxRequestBodyBytes": 2097152}}
    assert one(docs, "Middleware", "shop-ratelimit")["spec"] == {"rateLimit": {"average": 20, "period": "1s", "burst": 100}}
    off = render(*SETS, "ingress.securityHeaders.enabled=false", "ingress.maxRequestBodyBytes=0", "ingress.rateLimit=null")
    assert not [d for d in off if d["kind"] == "Middleware" and d["metadata"]["name"] != "shop-redirect"]
    assert "traefik.ingress.kubernetes.io/router.middlewares" not in one(off, "Ingress", "shop")["metadata"]["annotations"]
    assert not [d for d in render(*SETS, "ingress.enabled=false") if d["kind"] in ("Ingress", "Middleware")]


# ------------------------------------------------------------------------------------------------ security

@pytest.mark.parametrize("variant", [(), ("backend.enabled=false",), ("frontend.enabled=false",),
                                     ("database.enabled=false",)])
def test_every_container_is_non_root_read_only_capped_and_probed(variant):
    docs = render(*SETS, *variant)
    seen = 0
    for d, pod in pods(docs):
        assert pod["securityContext"]["runAsNonRoot"] is True and pod["securityContext"]["runAsUser"] > 0
        assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
        assert pod["automountServiceAccountToken"] is False
        for c in pod.get("initContainers", []) + pod["containers"]:
            who, sc = f"{d['metadata']['name']}/{c['name']}", c.get("securityContext", {})
            assert sc.get("allowPrivilegeEscalation") is False, who
            assert sc.get("readOnlyRootFilesystem") is True, who
            assert sc.get("runAsNonRoot") is True, who
            assert sc.get("capabilities") == {"drop": ["ALL"]}, who
            assert c["resources"]["limits"]["memory"] and c["resources"]["requests"]["cpu"], who
            if d["kind"] != "CronJob":
                assert c["readinessProbe"] and c["livenessProbe"], who
            seen += 1
    assert seen >= 2


def test_every_writable_folder_is_its_own_mount(docs):
    for name, wanted in (("shop-frontend", {"/tmp", "/var/cache/nginx", "/etc/nginx/conf.d"}), ("shop-backend", {"/tmp"})):
        (c,) = one(docs, "Deployment", name)["spec"]["template"]["spec"]["containers"]
        assert {m["mountPath"] for m in c["volumeMounts"]} == wanted
    pg = one(docs, "StatefulSet", "shop-postgresql")["spec"]["template"]["spec"]["containers"][0]
    assert {m["mountPath"] for m in pg["volumeMounts"]} >= {"/var/lib/postgresql/data", "/var/run/postgresql", "/tmp"}


def test_the_images_ports_and_probes_come_from_the_values(docs):
    images = {c["name"]: c["image"] for _, pod in pods(docs) for c in pod["containers"]}
    assert images["backend"] == "registry.test/team/shop:backend-1.2.3"
    assert images["frontend"] == "registry.test/team/shop:frontend-1.2.3"
    for _, pod in pods(docs):
        assert pod["imagePullSecrets"] == [{"name": "pull"}]
    other = render(*SETS, "backend.port=9000", "backend.health=/healthz", "frontend.port=8081")
    (b,) = one(other, "Deployment", "shop-backend")["spec"]["template"]["spec"]["containers"]
    assert b["ports"] == [{"name": "http", "containerPort": 9000}] and b["readinessProbe"]["httpGet"]["path"] == "/healthz"
    rule = one(other, "NetworkPolicy", "shop-app")["spec"]["ingress"][0]
    assert sorted(p["port"] for p in rule["ports"]) == [8081, 9000]


def test_every_resource_carries_the_product_s_labels(docs):
    for d in docs:
        labels = d["metadata"]["labels"]
        assert labels["app.kubernetes.io/name"] == "shop" and labels["app.kubernetes.io/instance"] == "shop", d["kind"]


# ------------------------------------------------------------------------------------------------ the database

def test_the_backend_finds_postgresql_through_the_secret(docs):
    (c,) = one(docs, "Deployment", "shop-backend")["spec"]["template"]["spec"]["containers"]
    env = {e["name"]: e for e in c["env"]}
    assert env["DB_PASSWORD"]["valueFrom"]["secretKeyRef"] == {"name": "shop-secret", "key": "DB_PASSWORD"}
    assert env["DATABASE_URL"]["value"] == "postgresql://app:$(DB_PASSWORD)@shop-postgresql:5432/app"
    assert env["PGHOST"]["value"] == "shop-postgresql" and env["APP_VERSION"]["value"] == "1.2.3"
    assert {r.get("secretRef", r.get("configMapRef"))["name"] for r in c["envFrom"]} == {"shop-secret", "shop-config"}


def test_postgresql_keeps_its_data_and_is_backed_up_every_night(docs):
    pg = one(docs, "StatefulSet", "shop-postgresql")
    assert pg["spec"]["volumeClaimTemplates"][0]["spec"]["resources"]["requests"]["storage"] == "5Gi"
    env = {e["name"]: e for e in pg["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert env["POSTGRES_PASSWORD"]["valueFrom"]["secretKeyRef"]["key"] == "DB_PASSWORD"
    backup = one(docs, "CronJob", "shop-backup")
    assert backup["spec"]["schedule"] == "45 2 * * *" and backup["spec"]["concurrencyPolicy"] == "Forbid"
    script = backup["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["args"][0]
    assert "pg_dump -Fc" in script and "KEEP_DAYS" in script and ".partial" in script
    assert one(docs, "PersistentVolumeClaim", "shop-backup")["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert "CronJob/shop-backup" not in kinds(render(*SETS, "backup.enabled=false"))


# ------------------------------------------------------------------------------------------------ secrets

def test_no_secret_value_is_in_the_chart_and_given_ones_are_encoded():
    values = yaml.safe_load((CHART / "values.yaml").read_text())
    assert values["secrets"] == {}
    secret = one(render(*SETS, "secrets.DB_PASSWORD=s3cret", "secrets.APP_SECRET_KEY=k"), "Secret", "shop-secret")
    assert base64.b64decode(secret["data"]["DB_PASSWORD"]).decode() == "s3cret"
    assert base64.b64decode(secret["data"]["APP_SECRET_KEY"]).decode() == "k"
    empty = one(render(*SETS, "secretKeys={MAIL_PASSWORD}"), "Secret", "shop-secret")
    assert empty["data"] == {"DB_PASSWORD": "", "MAIL_PASSWORD": ""}  # the database's key is always there


def test_a_changed_secret_rolls_the_backend():
    def checksum(*s):
        return one(render(*SETS, *s), "Deployment", "shop-backend")["spec"]["template"]["metadata"]["annotations"][
            "checksum/secret"]
    assert checksum("secrets.A=1") != checksum("secrets.A=2")


def test_the_settings_go_to_the_configmap(docs):
    config = one(render(*SETS, "env.MAIL_HOST=smtp.shop.test"), "ConfigMap", "shop-config")["data"]
    assert config["MAIL_HOST"] == "smtp.shop.test" and config["APP_ENV"] == "production"


# ------------------------------------------------------------------------------------------------ network policies

def test_only_the_ingress_controller_reaches_the_parts_and_only_backend_and_backup_reach_postgresql(docs):
    app = one(docs, "NetworkPolicy", "shop-app")
    assert app["spec"]["podSelector"]["matchExpressions"] == [
        {"key": "app.kubernetes.io/component", "operator": "In", "values": ["backend", "frontend"]}]
    assert app["spec"]["policyTypes"] == ["Ingress", "Egress"]
    (rule,) = app["spec"]["ingress"]
    assert rule["from"] == [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "traefik"}}}]
    assert sorted(p["port"] for p in rule["ports"]) == [8000, 8080]
    assert sorted(p["port"] for r in app["spec"]["egress"] for p in r["ports"]) == [53, 53, 5432]
    pg = one(docs, "NetworkPolicy", "shop-postgresql")
    assert pg["spec"]["ingress"][0]["from"][0]["podSelector"]["matchExpressions"] == [
        {"key": "app.kubernetes.io/component", "operator": "In", "values": ["backend", "backup"]}]
    assert pg["spec"]["egress"] == []
    backup = one(docs, "NetworkPolicy", "shop-backup")
    assert backup["spec"]["ingress"] == [] and sorted(p["port"] for r in backup["spec"]["egress"] for p in r["ports"]) == [
        53, 53, 5432]


def test_the_backend_s_way_out_skips_the_private_ranges(docs):
    out = one(docs, "NetworkPolicy", "shop-backend-egress")
    (rule,) = out["spec"]["egress"]
    assert rule["to"] == [{"ipBlock": {"cidr": "0.0.0.0/0", "except": ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]}}]
    assert [p["port"] for p in rule["ports"]] == [443]
    assert "NetworkPolicy/shop-backend-egress" not in kinds(render(*SETS, "networkPolicy.backendEgress.ports=null"))


def test_a_frontend_that_proxies_may_reach_the_backend_and_a_default_deny_can_be_had():
    docs = render(*SETS, "frontend.proxiesBackend=true", "networkPolicy.defaultDeny=true")
    app = one(docs, "NetworkPolicy", "shop-app")
    assert len(app["spec"]["ingress"]) == 2 and 8000 in [p["port"] for r in app["spec"]["egress"] for p in r["ports"]]
    deny = one(docs, "NetworkPolicy", "shop-default-deny")
    assert deny["spec"] == {"podSelector": {}, "policyTypes": ["Ingress", "Egress"]}
    assert not [d for d in render(*SETS, "networkPolicy.enabled=false") if d["kind"] == "NetworkPolicy"]


def test_every_workload_is_covered_by_a_network_policy(docs):
    components = {d["spec"]["template"]["metadata"]["labels"]["app.kubernetes.io/component"] if "template" in d["spec"]
                  else "backup" for d, _ in pods(docs)}
    covered = set()
    for np in (d for d in docs if d["kind"] == "NetworkPolicy"):
        sel = np["spec"]["podSelector"]
        covered |= {sel.get("matchLabels", {}).get("app.kubernetes.io/component")}
        for e in sel.get("matchExpressions", []):
            covered |= set(e["values"])
    assert components <= covered, components - covered


# ------------------------------------------------------------------------------------------------ values documented

def test_every_value_is_documented_in_values_yaml_and_the_readme():
    text = (CHART / "values.yaml").read_text()
    lines = text.splitlines()
    readme = (CHART.parents[1] / "README.md").read_text()
    for i, line in enumerate(lines):
        m = re.match(r"^([A-Za-z]\w*):", line)
        if m:
            above = lines[i - 1]  # a comment, or the key it is grouped with (host, then redirectHosts)
            assert above.startswith("#") or re.match(r"^[A-Za-z]\w*:", above), f"{m.group(1)} has no comment in values.yaml"
            assert re.search(rf"^#.*\b{m.group(1)}:", text, re.MULTILINE), f"{m.group(1)}: no comment says what it is"
            assert f"`{m.group(1)}" in readme, f"{m.group(1)} is not in crissp/deploy/README.md"
