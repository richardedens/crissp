# crissp/deploy — the deployment template

A product that works the C.R.I.S.S.P. way deploys behind the **release gate**: only a commit that a green full run
(`crissp/check-all.sh`, at most 7 days old) and a green `crissp/check.sh` for every change since have tested, on a clean
tree. There is no bypass. This folder is what such a product needs to go to a Kubernetes cluster behind Traefik: a
generic Helm chart, the Terraform for the cluster side, the product's deploy settings and the checks that prove them.

| Path | What it is |
|---|---|
| `deploy.json` | The product's deploy settings, read by `crissp/deploy.sh`, `crissp/testsuite/lib/deploy_plan.py` and `cluster_plan.py`. Ships with neutral example values that stop a cluster deploy until they are filled in |
| `.env.production.example` | Names every setting `.env.production` holds, without a value |
| `helm/app/` | The chart: a backend, a frontend (nginx) and PostgreSQL with a nightly backup, behind Traefik, with NetworkPolicies |
| `terraform/` | The cluster side the chart needs, on the Kubernetes provider only: the namespace, the image pull secret, a default-deny NetworkPolicy, a ResourceQuota and a LimitRange |
| `check.sh` | The testsuite's deploy step: helm lint and template, terraform fmt and validate (when installed), and the tests |
| `tests/` | Structure tests: the chart rendered, the Terraform files read, no secret value, no private name |
| `requirements.txt` | What the tests need on top of `crissp/testsuite/requirements.txt` (a YAML reader) |

## Adopting it

1. **Fill in `deploy.json`** (it never holds a secret):

   | Setting | What it is |
   |---|---|
   | `product` | The product's name: labels, messages |
   | `compose.file`, `compose.services` | The local Docker Compose stack: each service with the paths that go into its image (`inputs`: an exact path, a folder ending in `/`, or a glob) and the ones that do not (`exclude`). No compose file: `crissp/deploy.sh` says there is nothing to deploy locally |
   | `compose.url`, `compose.port`, `compose.health` | Where the local stack answers (`{port}` from the setting in `.env` or the default) and the paths checked after a rebuild |
   | `cluster.chart`, `cluster.release` | The chart (`crissp/deploy/helm/app`) and the Helm release name |
   | `cluster.namespace`, `cluster.kubeContext` | Where it goes. The context is required: a deploy never goes to whatever cluster happens to be current |
   | `cluster.kubeconfig` | A kubeconfig path relative to the repository; empty: `KUBECONFIG`, else `~/.kube/config` |
   | `cluster.domains` | `primary` (the address) and `redirects` (other domains, sent there with a 301) |
   | `cluster.image` | `repository` (one per product; the parts are tags `<part>-<version>-<commit>`), `platform` (`linux/amd64`), `parts` (`backend`, `frontend` → their build folders; leave one out and the chart leaves it out) |
   | `cluster.health` | The https:// URL checked from outside after the rollout |
   | `cluster.pullSecret` | `name` of the image pull secret; `sourceNamespace`: without Terraform, the one namespace it is copied from when missing (empty: it must already be there) |
   | `cluster.terraform` | The Terraform folder (`crissp/deploy/terraform`) |
   | `cluster.values` | Extra chart values that are no secret (e.g. `{"database": {"enabled": false}}`) |
   | `cluster.env` | `file` (`.env.production`), `example`, which keys are `secrets` (into the chart's Secret) and `settings` (its ConfigMap), which are `required`, their `rules` (`minLength`, `prefix`, `pattern` + `message`), and the `registry` keys Terraform's pull secret is made from |

   The example names (`example.org` and friends, RFC 2606) stop a cluster deploy until they are replaced.
2. **Make `.env.production`** at the repository's root from `.env.production.example`. It is never in git and never in an
   image (`.gitignore`: `.env.*`; every `.dockerignore`). Secrets only reach the cluster through a private values file.
3. **Adapt the chart's values** in `helm/app/values.yaml` where the product differs (ports, health paths, the user
   its images run as, the writable folders, resources, the backend's way out).
4. **Prove it**: `crissp/deploy/check.sh`, then `crissp/deploy.sh --cluster-plan`.

## What `crissp/deploy.sh` does

- **No flag**: the local Docker Compose stack. Without a compose file it says so and stops. Otherwise the release gate,
  the release notes (`VERSION` and the top section of `CHANGELOG.md`), then only the services whose inputs changed since
  the last deployed commit, one at a time with `docker compose up -d --build --no-deps <service>`, the health checks,
  and the record (`crissp/testsuite/results/deploy.json`). `--plan` shows it without changing anything.
- **`--cluster-plan`**: what a cluster deploy would do and what stops it (deploy.json not filled in, a missing or wrong
  setting in `.env.production` — by name, never by value —, no kubeconfig). It changes nothing and prints no secret.
- **`--cluster`**, in this order, nothing changed before your yes:
  1. the release gate and the release notes;
  2. the plan above; any stop ends it here;
  3. `terraform plan` of `crissp/deploy/terraform` with a private variables file (the registry credentials come from
     `.env.production`); when terraform is not installed: `skipped: terraform not installed`;
  4. a y/N;
  5. `terraform apply` of exactly that plan;
  6. every part's image built for the platform and pushed as `<repository>:<part>-<version>-<commit>`;
  7. without Terraform: the namespace (created if missing) and the pull secret (copied from `cluster.pullSecret.sourceNamespace`,
     or it must already be there);
  8. `helm upgrade --install` with a private values file (mode 600 in a private folder, removed however it ends);
  9. `rollout status` of every part, then the health URL.

## The chart (`helm/app`)

Every resource runs as non-root with the runtime's seccomp profile, no service account token, no privilege escalation,
no capabilities and a read-only root file system (the folders a part writes are its own `emptyDir`s); every container
has requests, limits and (except the backup job) readiness and liveness probes. NetworkPolicies: the parts take traffic
only from the ingress controller's namespaces; PostgreSQL only from the backend and the backup and nothing out; the
backup only out to PostgreSQL and DNS; the backend out only on the configured ports and never to the private ranges;
the frontend has no way out. The namespace's default-deny comes from Terraform (or `networkPolicy.defaultDeny`).

| Value | What it is |
|---|---|
| `product` | `app.kubernetes.io/name` of every resource |
| `image` | `repository`, `version` (deploy.sh sets `<version>-<commit>`), `pullPolicy` |
| `imagePullSecrets` | The pull secret(s) in the namespace |
| `versionEnv` | The variable the backend gets the version in (empty: none) |
| `host`, `redirectHosts` | The address; the other domains, 301 to it, on their own certificate |
| `clusterIssuer` | cert-manager's ClusterIssuer (empty: no certificate annotation) |
| `ingress` | `enabled`, `className` (traefik), `maxRequestBodyBytes`, `rateLimit`, `securityHeaders` (HSTS, frame deny, nosniff, referrer and permissions policy, CSP) — all Traefik Middlewares |
| `backend` | `enabled`, `replicas`, `port`, `path` (sent to it when there is a frontend), `health`, `runAsUser`, `writablePaths`, `resources` |
| `frontend` | `enabled`, `replicas`, `port`, `health`, `runAsUser`, `proxiesBackend`, `writablePaths`, `resources` |
| `env` | Settings for the backend that are no secret (ConfigMap) |
| `secrets`, `secretKeys` | Secrets for the backend, filled only by deploy.sh; an upgrade without a value keeps the cluster's; the keys the Secret always has |
| `database` | PostgreSQL: `enabled`, `image`, `name`, `user`, `passwordKey`, `urlEnv`, `runAsUser`, `storage`, `storageClassName`, `resources` |
| `backup` | The nightly `pg_dump`: `enabled`, `schedule`, `storage`, `storageClassName`, `keepDays` (the volume is kept on uninstall) |
| `networkPolicy` | `enabled`, `defaultDeny`, `ingressControllerNamespaces`, `backendEgress` (`ports`, `except`) |

Restore: `pg_restore -h <release>-postgresql -U <user> -d postgres --clean --create <database>.dump`.

## Terraform (`terraform/`)

The Kubernetes provider only, version pinned exactly, no cloud resources. Variables (each described in
`variables.tf`): `kubeconfig_path`, `kube_context`, `namespace`, `labels`, `pod_security` (restricted: the chart meets
it), `pull_secret_name`, `create_pull_secret`, `registry_server`, `registry_username` and `registry_password`
(sensitive, never in a file in git), `default_deny`, `quota`, `container_defaults`. Outputs: `namespace`,
`pull_secret_name`, `default_deny`. `terraform.tfvars.example` shows a manual run's variables; real `*.tfvars`, state
and plans are git-ignored (they hold the pull secret). The state is local by default: a team keeps it in a backend of
its own choosing, which is the product's decision, not the template's.

## The checks

`crissp/deploy/check.sh` is the testsuite's deploy step: `helm lint` and `helm template` with the example values and
every `helm/app/ci/*-values.yaml`; `terraform fmt -check` and `terraform validate` in a throwaway copy when terraform is
installed, otherwise a visible `skipped: terraform not installed`; and pytest on `tests/`. It exits non-zero on any
real failure and never installs, applies, pushes or talks to a cluster.
