"""What crissp/deploy.sh --cluster does and whether it may go at all: the decisions, kept out of the shell so they can be
tested. Everything about the product (chart, release, namespace, kube context, domains, images, health URL, which
settings are secrets) is in crissp/deploy/deploy.json; nothing about a product, a cluster or a registry is written here.

A cluster deploy is, in this order, and nothing in the registry or the cluster changes before the product owner's yes:
1. the release gate (release.py check) and the release notes, as for the local deploy;
2. deploy.json is filled in (no example names left) and .env.production (never in git, never in an image) holds every
   required setting, following its rules; a missing or wrong one stops it here, named, never shown;
3. terraform plan of crissp/deploy/terraform (the namespace, the image pull secret, a default-deny NetworkPolicy, the
   quota), with a private variables file; skipped, visibly, when terraform is not installed;
4. the yes; then terraform apply of exactly that plan;
5. every part's image built for the platform (linux/amd64) and pushed as <repository>:<part>-<version>-<commit>, so a
   node never keeps running an old build under a reused tag;
6. without Terraform: the namespace (created if missing) and the pull secret (copied from the one configured source
   namespace, or it must already be there);
7. helm upgrade --install with a private values file (mode 600, removed afterwards); the secrets never reach a log;
8. rollout status of every part, then the health URL from outside.

    python3 crissp/testsuite/lib/cluster_plan.py plan   [--config deploy.json] [--env .env.production] --version V --commit C
        the plan: read-only, prints the steps and the stops (exit 1 when something stops it)
    python3 crissp/testsuite/lib/cluster_plan.py shell  [--config …] --version V     the settings as shell variables
    python3 crissp/testsuite/lib/cluster_plan.py values [--config …] [--env …] --version TAG --out FILE
    python3 crissp/testsuite/lib/cluster_plan.py tfvars [--config …] [--env …] --version V --out FILE
        write a private file (mode 600) for helm or terraform: only for deploy.sh, and only when nothing stops it
"""

import argparse
import copy
import json
import os
import re
import shlex
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("CRISSP_ROOT") or os.getcwd()).resolve()  # the project; never this file's place
CONFIG = ROOT / "crissp" / "deploy" / "deploy.json"
PARTS = ("backend", "frontend")  # the parts the chart (crissp/deploy/helm/app) knows
_NAME = re.compile(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?")
_EXAMPLE = re.compile(r"(^|\.)example\.(com|org|net)$|\.example$")  # RFC 2606: never a real product


def load_config(path: Path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise ValueError(f"{path}: deploy.json is missing (crissp/deploy/deploy.json names what is deployed where)")
    except json.JSONDecodeError as e:
        raise ValueError(f"{path}: deploy.json is not valid JSON ({e.msg}, line {e.lineno})")


def _c(config: dict) -> dict:
    return config.get("cluster", {})


def _host(address: str) -> str:
    return re.sub(r"^[a-z]+://", "", address).split("/")[0].split(":")[0].lower()


def config_stops(config: dict) -> list[str]:
    """What in deploy.json stops a cluster deploy, by setting name."""
    c = _c(config)
    out = []
    for key in ("release", "namespace"):
        if not _NAME.fullmatch(str(c.get(key, ""))):
            out.append(f"cluster.{key} must be a Kubernetes name (lower case letters, digits and -)")
    if not c.get("kubeContext"):
        out.append("cluster.kubeContext is empty in deploy.json: name the context, so a deploy never goes to whatever "
                   "cluster happens to be current")
    if not c.get("chart") or not (ROOT / c.get("chart", "")).is_dir():
        out.append(f"cluster.chart: no chart at {c.get('chart') or '(empty)'}")
    image, domains = c.get("image", {}), c.get("domains", {})
    hosts = [domains.get("primary", ""), *domains.get("redirects", []), _host(image.get("repository", "")),
             _host(c.get("health", ""))]
    if not domains.get("primary"):
        out.append("cluster.domains.primary is empty in deploy.json")
    if not image.get("repository"):
        out.append("cluster.image.repository is empty in deploy.json")
    if any(h and _EXAMPLE.search(h) for h in hosts):
        out.append("deploy.json still holds the example settings (example.org and friends): fill in the product's "
                   "domains, image repository and health URL")
    parts = image.get("parts", {})
    if not parts:
        out.append("cluster.image.parts is empty: name the parts to build (backend, frontend) and their build folders")
    for part in parts:
        if part not in PARTS:
            out.append(f"cluster.image.parts: the chart knows {' and '.join(PARTS)}, not {part}")
    if not str(c.get("health", "")).startswith("https://"):
        out.append("cluster.health must be an https:// address (the health URL checked from outside)")
    if "secrets" in c.get("values", {}):
        out.append("cluster.values may not hold secrets: they come from .env.production (cluster.env.secrets)")
    return out


def read_env(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def env_stops(env: dict[str, str] | None, config: dict) -> list[str]:
    """Why .env.production stops this deploy, by setting name; never a value."""
    e = _c(config).get("env", {})
    name = Path(e.get("file", ".env.production")).name
    if env is None:
        return [f"{name} is missing: copy {e.get('example', '.env.production.example')} and fill it in (never commit it)"]
    out = [f"{k} is empty in {name}" for k in e.get("required", []) if not env.get(k, "").strip()]
    for key, rule in e.get("rules", {}).items():
        value = env.get(key, "")
        if not value:
            continue
        if "minLength" in rule and len(value) < rule["minLength"]:
            out.append(f"{key} must be at least {rule['minLength']} characters")
        if "prefix" in rule and not value.startswith(rule["prefix"]):
            out.append(f"{key} must start with {rule['prefix']}")
        if "pattern" in rule and not re.fullmatch(rule["pattern"], value.strip()):
            out.append(rule.get("message") or f"{key} does not have the expected form")
    return out


def stops(env: dict[str, str] | None, config: dict) -> list[str]:
    return config_stops(config) + env_stops(env, config)


def commit_stops(commit: str) -> list[str]:
    if re.fullmatch(r"[0-9a-f]{7,40}", commit):
        return []
    return ["no commit to deploy: commit first (the image tag carries the commit)"]


def image_version(version: str, commit: str) -> str:
    return f"{version}-{commit[:8]}"


def images(config: dict, tag: str) -> list[tuple[str, str, str]]:
    """(part, image, build folder) for every part, in the chart's order."""
    image = _c(config)["image"]
    return [(p, f"{image['repository']}:{p}-{tag}", image["parts"][p]) for p in PARTS if p in image["parts"]]


def _merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else copy.deepcopy(v)
    return out


def values(env: dict[str, str], config: dict, tag: str) -> dict:
    """The private values file: the settings and secrets of .env.production, and what deploy.json says about the
    product. An empty optional setting is left out, so the chart (or the cluster) keeps what it has."""
    c, e = _c(config), _c(config).get("env", {})
    parts = c["image"]["parts"]
    out = {
        "product": config.get("product", c["release"]),
        "image": {"repository": c["image"]["repository"], "version": tag},
        "host": c["domains"]["primary"],
        "redirectHosts": list(c["domains"].get("redirects", [])),
        "imagePullSecrets": [{"name": c["pullSecret"]["name"]}] if c.get("pullSecret", {}).get("name") else [],
        "env": {k: env[k] for k in e.get("settings", []) if env.get(k)},
        "secrets": {k: env[k] for k in e.get("secrets", []) if env.get(k)},
    }
    out = _merge(out, {p: {"enabled": p in parts} for p in PARTS})
    return _merge(out, c.get("values", {}))


def tfvars(env: dict[str, str], config: dict, kubeconfig: Path | None) -> dict:
    """The private Terraform variables: the cluster side (crissp/deploy/terraform) the chart needs."""
    c = _c(config)
    reg = {k: env.get(v, "") for k, v in c.get("env", {}).get("registry", {}).items()}
    out = {
        "namespace": c["namespace"],
        "kube_context": c["kubeContext"],
        "labels": {"app.kubernetes.io/part-of": config.get("product", c["release"])},
        "pull_secret_name": c.get("pullSecret", {}).get("name", ""),
        "create_pull_secret": bool(reg.get("server") and reg.get("username") and reg.get("password")),
        "registry_server": reg.get("server", ""),
        "registry_username": reg.get("username", ""),
        "registry_password": reg.get("password", ""),
    }
    if kubeconfig:
        out["kubeconfig_path"] = str(kubeconfig)
    return out


def write_private(path: Path, data: dict) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(data, f)
    os.chmod(path, 0o600)


def find_kubeconfig(root: Path, environ: dict[str, str], config: dict) -> Path | None:
    """KUBECONFIG, else cluster.kubeconfig (relative to the repository), else ~/.kube/config. Found, never read."""
    configured = _c(config).get("kubeconfig", "")
    home = environ.get("HOME", "")
    candidates = [environ.get("KUBECONFIG", ""), str(root / configured) if configured else "",
                  str(Path(home) / ".kube" / "config") if home else ""]
    return next((Path(c) for c in candidates if c and Path(c).is_file()), None)


def render_plan(env: dict[str, str] | None, config: dict, version: str, commit: str, kubeconfig: str | None,
                terraform: bool) -> str:
    c = _c(config)
    ns, release, ctx = c.get("namespace", "?"), c.get("release", "?"), c.get("kubeContext", "?")
    committed = not commit_stops(commit)
    tag = image_version(version, commit) if committed else f"{version}-<commit>"
    lines = [(f"Cluster deploy of {config.get('product', release)} {version} (commit {commit[:8] if committed else commit}) "
             f"to context {ctx}, "
             f"namespace {ns}"), "", "Steps, after the release gate:"]
    pull = c.get("pullSecret", {})
    if terraform:
        lines += [(f"  terraform plan in {c.get('terraform')} (namespace {ns}, pull secret {pull.get('name')}, "
                  "default-deny NetworkPolicy, ResourceQuota, LimitRange; private variables file)"),
                  "  your yes (y/N), then:",
                  "  terraform apply of exactly that plan"]
    else:
        lines += [f"  skipped: terraform not installed ({c.get('terraform')} is not applied)", "  your yes (y/N), then:"]
    try:
        for _, image, folder in images(config, tag):
            lines.append(f"  docker buildx build --platform {c['image'].get('platform', 'linux/amd64')} --push -t "
                         f"{image} {folder}")
    except KeyError:
        lines.append("  (no images: cluster.image is incomplete)")
    if not terraform:
        lines.append(f"  namespace {ns} (created if missing)")
        if pull.get("sourceNamespace"):
            lines.append(f"  pull secret {pull.get('name')} (copied from namespace {pull['sourceNamespace']} when missing)")
        else:
            lines.append(f"  pull secret {pull.get('name')} must already be in namespace {ns} (or set "
                         "cluster.pullSecret.sourceNamespace, or install terraform)")
    parts = [p for p in PARTS if p in c.get("image", {}).get("parts", {})]
    lines += [(f"  helm upgrade --install {release} {c.get('chart')} --namespace {ns} --kube-context {ctx} "
              "-f <private values, mode 600, removed afterwards>"),
              f"  kubectl -n {ns} rollout status " + " and ".join(f"deployment/{release}-{p}" for p in parts),
              f"  curl {c.get('health')}",
              "", f"kubeconfig: {kubeconfig}" if kubeconfig else "kubeconfig: none found"]
    found = stops(env, config) + commit_stops(commit)
    found += ([] if kubeconfig else [("no kubeconfig found: set KUBECONFIG or cluster.kubeconfig in "
                                                         "deploy.json")])
    if found:
        lines += ["", "Stops:"] + [f"  - {s}" for s in found]
        lines += ["", "Not deploying: nothing in the registry or the cluster is changed."]
    else:
        lines += ["", "Nothing stops it."]
    return "\n".join(lines)


def render_shell(config: dict, kubeconfig: str | None) -> str:
    c = _c(config)
    pull = c.get("pullSecret", {})
    pairs = {"CP_PRODUCT": config.get("product", c.get("release", "")), "CP_RELEASE": c.get("release", ""),
             "CP_NAMESPACE": c.get("namespace", ""), "CP_CONTEXT": c.get("kubeContext", ""),
             "CP_KUBECONFIG": kubeconfig or "", "CP_CHART": c.get("chart", ""),
             "CP_PARTS": " ".join(p for p in PARTS if p in c.get("image", {}).get("parts", {})),
             "CP_PLATFORM": c.get("image", {}).get("platform", "linux/amd64"), "CP_HEALTH": c.get("health", ""),
             "CP_PULL_SECRET": pull.get("name", ""), "CP_PULL_SOURCE": pull.get("sourceNamespace", ""),
             "CP_TERRAFORM": c.get("terraform", "")}
    return "\n".join(f"{k}={shlex.quote(v)}" for k, v in pairs.items())


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="cluster_plan.py")
    parser.add_argument("command", choices=("plan", "shell", "values", "tfvars"))
    parser.add_argument("--config", default=str(CONFIG))
    parser.add_argument("--env")
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", default="")
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    try:
        config = load_config(Path(args.config))
    except ValueError as e:
        print(f"Not deploying: {e}", file=sys.stderr)
        return 1
    path = Path(args.env) if args.env else ROOT / _c(config).get("env", {}).get("file", ".env.production")
    env = read_env(path.read_text()) if path.is_file() else None
    found = find_kubeconfig(ROOT, dict(os.environ), config)
    kubeconfig = str(found) if found else None
    if args.command == "plan":
        print(render_plan(env, config, args.version, args.commit, kubeconfig, shutil.which("terraform") is not None))
        return 1 if stops(env, config) or commit_stops(args.commit) or kubeconfig is None else 0
    if args.command == "shell":
        print(render_shell(config, kubeconfig))
        return 0
    if stops(env, config) or not args.out:
        print("Not writing: run the plan first (crissp/deploy.sh --cluster-plan).", file=sys.stderr)
        return 1
    data = values(env, config, args.version) if args.command == "values" else tfvars(env, config, found)
    write_private(Path(args.out), data)
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import project
    sys.stdout, sys.stderr = project.Speaking(sys.stdout), project.Speaking(sys.stderr)  # F-04: the names a person can type
    sys.exit(main(sys.argv[1:]))
