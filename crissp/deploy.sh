#!/usr/bin/env bash
# Deploy the product, behind the release gate. What is deployed where is in crissp/deploy/deploy.json.
#
#   crissp/deploy.sh                  release gate → release notes → rebuild the compose services that changed → health → record
#   crissp/deploy.sh --plan           what it would rebuild and why, and what would stop it (changes nothing)
#   crissp/deploy.sh --cluster-plan   what a cluster deploy would do and what stops it (changes nothing)
#   crissp/deploy.sh --cluster        release gate → .env.production → terraform plan → y/N → terraform apply →
#                                     images (linux/amd64) pushed → helm upgrade --install → rollout status → health URL
#
# Release gate: only a commit that a green full run (crissp/check-all.sh, at most 7 days old) and a green crissp/check.sh for
# every change since tested, on a clean tree (crissp/testsuite/lib/release.py). There is no way around it.
# Release notes: VERSION is a version and the top section of CHANGELOG.md is about it.
# Local: only the services whose files changed since the last deployed commit (crissp/testsuite/results/deploy.json),
# each with `docker compose up -d --build --no-deps <service>` (never without --no-deps: compose would recreate the
# others as dependencies). crissp/testsuite/lib/deploy_plan.py decides; this script only carries it out.
# Cluster: crissp/testsuite/lib/cluster_plan.py decides; secrets go only through private files (mode 600, removed).
set -euo pipefail
ENGINE="$(cd "$(dirname "$0")" && pwd)"  # the framework: this repository's crissp/, or an installed crissp's engine
export CRISSP_ROOT="${CRISSP_ROOT:-$(dirname "$ENGINE")}"  # the project: crissp sets it, else the folder above
ROOT="$CRISSP_ROOT"
PLAN="$ENGINE/testsuite/lib/deploy_plan.py"
CLUSTER_PLAN="$ENGINE/testsuite/lib/cluster_plan.py"
CONFIG="$ROOT/crissp/deploy/deploy.json"

BLUE='\033[0;34m'; GREEN='\033[0;32m'; RED='\033[0;31m'; NC='\033[0m'
log() { echo -e "${BLUE}[..]${NC} $*"; }; ok() { echo -e "${GREEN}[ok]${NC} $*"; }
die() { echo -e "${RED}[xx]${NC} $*" >&2; exit 1; }

healthy() {  # healthy <url>: up to a minute for a 2xx answer
  local i
  for i in $(seq 1 30); do
    if curl -fsS --max-time 5 -o /dev/null "$1" 2>/dev/null; then return 0; fi
    [ "$i" = 30 ] || sleep 2
  done
  return 1
}

head_commit() { git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo "(no commit yet)"; }
version() { tr -d '[:space:]' < "$ROOT/VERSION" 2>/dev/null || echo "(no VERSION)"; }

deploy_cluster() {  # the decisions are in cluster_plan.py; this only carries them out
  local version commit tag answer tf=0 vars
  log "Release gate: is exactly this code fully tested?"
  python3 "$ENGINE/testsuite/lib/release.py" check || die "Not deploying. Run crissp/check.sh or crissp/check-all.sh first."
  python3 "$ENGINE/testsuite/lib/impact.py" release-notes || die "Not deploying: write the release notes of this version first."
  version="$(version)"; commit="$(head_commit)"
  python3 "$CLUSTER_PLAN" plan --config "$CONFIG" --version "$version" --commit "$commit" || die "Not deploying: see the stops above."
  tag="$version-${commit:0:8}"
  vars="$(python3 "$CLUSTER_PLAN" shell --config "$CONFIG" --version "$version")" || die "The settings could not be read."
  CP_PRODUCT=""; CP_RELEASE=""; CP_NAMESPACE=""; CP_CONTEXT=""; CP_KUBECONFIG=""; CP_CHART=""; CP_PARTS=""
  CP_PLATFORM=""; CP_HEALTH=""; CP_PULL_SECRET=""; CP_PULL_SOURCE=""; CP_TERRAFORM=""
  eval "$vars"
  export KUBECONFIG="$CP_KUBECONFIG"

  # Every file that holds a secret lives in one private folder, removed however this ends.
  PRIVATE="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/crissp-deploy.XXXXXX")"
  trap 'rm -rf "$PRIVATE"' EXIT

  if command -v terraform >/dev/null 2>&1 && [ -d "$ROOT/$CP_TERRAFORM" ]; then
    tf=1
    log "terraform plan: the cluster side ($CP_TERRAFORM: namespace, pull secret, default-deny NetworkPolicy, quota)"
    python3 "$CLUSTER_PLAN" tfvars --config "$CONFIG" --version "$version" --out "$PRIVATE/cluster.tfvars.json" \
      || die "The Terraform variables could not be written."
    terraform -chdir="$ROOT/$CP_TERRAFORM" init -input=false >/dev/null || die "terraform init failed."
    terraform -chdir="$ROOT/$CP_TERRAFORM" plan -input=false -var-file="$PRIVATE/cluster.tfvars.json" \
      -out="$PRIVATE/cluster.tfplan" || die "terraform plan failed: nothing was changed."
  else
    echo "skipped: terraform not installed (or no $CP_TERRAFORM): the namespace and the pull secret are handled below"
  fi

  printf 'Apply the cluster side, push %s and install %s %s in namespace %s (context %s)? [y/N] ' \
    "$CP_PARTS" "$CP_PRODUCT" "$tag" "$CP_NAMESPACE" "$CP_CONTEXT"
  read -r answer
  [ "$answer" = y ] || [ "$answer" = Y ] || die "Nothing was changed."

  if [ "$tf" = 1 ]; then
    log "terraform apply (exactly the plan above)"
    terraform -chdir="$ROOT/$CP_TERRAFORM" apply -input=false "$PRIVATE/cluster.tfplan" || die "terraform apply failed."
  fi

  docker buildx version >/dev/null 2>&1 || die "docker buildx is missing."
  local part image folder
  while IFS=$'\t' read -r part image folder; do
    log "Build and push $image ($CP_PLATFORM)"
    docker buildx build --platform "$CP_PLATFORM" --push -t "$image" "$ROOT/$folder" || die "The $part image did not build or push."
  done < <(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); import cluster_plan as c
for p, i, f in c.images(c.load_config(sys.argv[2]), sys.argv[3]): print(f"{p}\t{i}\t{f}")' "$ENGINE/testsuite/lib" "$CONFIG" "$tag")

  if [ "$tf" = 0 ]; then
    log "Namespace $CP_NAMESPACE and the pull secret $CP_PULL_SECRET (without Terraform)"
    kubectl --context "$CP_CONTEXT" get namespace "$CP_NAMESPACE" >/dev/null 2>&1 \
      || kubectl --context "$CP_CONTEXT" create namespace "$CP_NAMESPACE"
    if [ -n "$CP_PULL_SECRET" ] && ! kubectl --context "$CP_CONTEXT" -n "$CP_NAMESPACE" get secret "$CP_PULL_SECRET" >/dev/null 2>&1; then
      [ -n "$CP_PULL_SOURCE" ] || die "No pull secret $CP_PULL_SECRET in $CP_NAMESPACE: install terraform, set cluster.pullSecret.sourceNamespace, or create it (kubectl -n $CP_NAMESPACE create secret docker-registry $CP_PULL_SECRET ...)."
      kubectl --context "$CP_CONTEXT" -n "$CP_PULL_SOURCE" get secret "$CP_PULL_SECRET" -o json \
        | python3 -c "import json,sys; s=json.load(sys.stdin); m=s['metadata']; s['metadata']={'name':m['name'],'namespace':sys.argv[1]}; print(json.dumps(s))" "$CP_NAMESPACE" \
        | kubectl --context "$CP_CONTEXT" apply -f - >/dev/null || die "Could not copy the pull secret from $CP_PULL_SOURCE."
      ok "Pull secret copied from $CP_PULL_SOURCE"
    fi
  fi

  log "helm upgrade --install $CP_RELEASE (secrets through a private values file)"
  python3 "$CLUSTER_PLAN" values --config "$CONFIG" --version "$tag" --out "$PRIVATE/values.json" || die "The values could not be written."
  helm upgrade --install "$CP_RELEASE" "$ROOT/$CP_CHART" --namespace "$CP_NAMESPACE" --kube-context "$CP_CONTEXT" \
    -f "$PRIVATE/values.json" --wait --timeout 10m \
    || die "helm upgrade failed: kubectl --context $CP_CONTEXT -n $CP_NAMESPACE get pods"
  rm -rf "$PRIVATE"

  for part in $CP_PARTS; do
    kubectl --context "$CP_CONTEXT" -n "$CP_NAMESPACE" rollout status "deployment/$CP_RELEASE-$part" --timeout=5m \
      || die "$part did not roll out."
  done
  if curl -fsS --max-time 10 -o /dev/null "$CP_HEALTH"; then
    ok "$CP_HEALTH answers healthy"
  else
    echo "$CP_HEALTH does not answer yet: DNS or the certificate may still be on its way." >&2
  fi
  ok "$CP_PRODUCT $tag is installed in $CP_NAMESPACE (context $CP_CONTEXT)"
}

case "${1:-}" in
  --plan) python3 "$PLAN" plan; exit 0 ;;
  --cluster-plan)
    python3 "$CLUSTER_PLAN" plan --config "$CONFIG" --version "$(version)" --commit "$(head_commit)"
    exit $? ;;
  --cluster) deploy_cluster; exit 0 ;;
  "") ;;
  *) die "Usage: crissp/deploy.sh [--plan | --cluster-plan | --cluster]" ;;
esac

# --- local: the product's Docker Compose stack
vars=$(python3 "$PLAN" plan --format shell) || die "The plan could not be made (crissp/deploy.sh --plan)"
PLAN_STOPS=""; PLAN_COMPOSE=""; PLAN_FILE=""; PLAN_SERVICES=""; PLAN_VERSION=""; PLAN_COMMIT=""; PLAN_PRODUCT=""; PLAN_HEALTH=""
eval "$vars"
if ! [ "$PLAN_COMPOSE" = 1 ]; then
  python3 "$PLAN" plan
  exit 0
fi

log "Release gate: is exactly this code fully tested?"
python3 "$ENGINE/testsuite/lib/release.py" check || die "Not deploying. Run crissp/check.sh (it tests only what changed; crissp/check.sh --plan shows what and how long) or, when it asks for it, crissp/check-all.sh."
log "Release notes (VERSION, CHANGELOG.md)"
python3 "$ENGINE/testsuite/lib/impact.py" release-notes || die "Not deploying: write the release notes of this version first."

python3 "$PLAN" plan
[ "$PLAN_STOPS" = 0 ] || die "Not deploying: see the stops above. Nothing was changed."

rebuilt=""
if [ -n "$PLAN_SERVICES" ]; then
  docker info >/dev/null 2>&1 || die "Docker is not running."
  for service in $PLAN_SERVICES; do
    log "Rebuild $service (docker compose up -d --build --no-deps $service)"
    docker compose -f "$ROOT/$PLAN_FILE" --project-directory "$ROOT" up -d --build --no-deps "$service" \
      || die "$service did not build or start (see above). What was rebuilt before it is running."
    rebuilt="$rebuilt $service"
  done
fi
[ -n "$rebuilt" ] || ok "Nothing to rebuild."

log "Health checks"
for url in $PLAN_HEALTH; do
  healthy "$url" || die "$url does not answer healthy: docker compose logs. Not recorded as deployed."
  ok "$url answers"
done
# shellcheck disable=SC2086  # one word per service
python3 "$PLAN" record $rebuilt
ok "$PLAN_PRODUCT $PLAN_VERSION (commit ${PLAN_COMMIT:0:8}) deployed in $SECONDS s"
