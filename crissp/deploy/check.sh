#!/usr/bin/env bash
# crissp/deploy/check.sh: the testsuite's deploy step. It proves the deployment template without touching a cluster:
#   1. helm lint and helm template of crissp/deploy/helm/app, with its example values and every ci/*-values.yaml
#   2. terraform fmt -check and terraform validate of crissp/deploy/terraform, when terraform is installed (in a
#      throwaway copy, so nothing lands in the repository); without it a visible "skipped" line, never a silent pass
#   3. pytest on crissp/deploy/tests (the chart rendered, the Terraform files read, no secret, no private name)
# It never installs anything, never runs helm install/upgrade, terraform apply, kubectl or docker push.
# Exit 0 only when every step that ran passed.
set -uo pipefail
export PYTHONDONTWRITEBYTECODE=1  # nothing generated lands in the repository
HERE="$(cd "$(dirname "$0")" && pwd)"
ENGINE="$(cd "$HERE/.." && pwd)"
ROOT="${CRISSP_ROOT:-$(cd "$HERE/../.." && pwd)}"  # the project whose chart and Terraform are proven
export CRISSP_ROOT="$ROOT"
PROJECT="$ROOT/crissp/deploy"
[ -d "$PROJECT" ] || PROJECT="$HERE"
CHART="$PROJECT/helm/app"
failed=0
step() { echo "== $*"; }
bad() { echo "FAILED: $*"; failed=1; }

step "helm lint and helm template ($CHART)"
if command -v helm >/dev/null 2>&1; then
  helm lint "$CHART" >/dev/null || bad "helm lint"
  helm template example "$CHART" --namespace example >/dev/null || bad "helm template with the example values"
  for values in "$CHART"/ci/*-values.yaml; do
    [ -f "$values" ] || continue
    helm lint "$CHART" -f "$values" >/dev/null || bad "helm lint -f ${values#"$ROOT"/}"
    helm template example "$CHART" --namespace example -f "$values" >/dev/null || bad "helm template -f ${values#"$ROOT"/}"
  done
  [ "$failed" = 0 ] && echo "ok: helm lint and helm template"
else
  bad "helm is not installed: the chart cannot be proven"
fi

step "terraform fmt -check and terraform validate ($PROJECT/terraform)"
if command -v terraform >/dev/null 2>&1; then
  work="$(mktemp -d "${TMPDIR:-/tmp}/crissp-terraform.XXXXXX")"
  cp "$PROJECT"/terraform/*.tf "$work/"
  if terraform fmt -check -diff "$work" >/dev/null; then echo "ok: terraform fmt -check"; else bad "terraform fmt -check (run terraform fmt in crissp/deploy/terraform)"; fi
  if TF_DATA_DIR="$work/.terraform" terraform -chdir="$work" init -backend=false -input=false >/dev/null \
     && TF_DATA_DIR="$work/.terraform" terraform -chdir="$work" validate; then
    echo "ok: terraform validate"
  else
    bad "terraform validate"
  fi
  rm -rf "$work"
else
  echo "skipped: terraform not installed (terraform fmt -check and terraform validate did not run; the structure tests below still read the files)"
fi

step "pytest crissp/deploy/tests"
if command -v uv >/dev/null 2>&1; then
  (cd "$ROOT" && uv run --quiet --no-project --with-requirements "$ENGINE/testsuite/requirements.txt" \
     --with-requirements "$HERE/requirements.txt" python -m pytest -q -p no:cacheprovider "$HERE/tests") \
    || bad "pytest crissp/deploy/tests"
elif python3 -c "import pytest, yaml" 2>/dev/null; then
  (cd "$ROOT" && python3 -m pytest -q -p no:cacheprovider "$HERE/tests") || bad "pytest crissp/deploy/tests"
else
  bad "neither uv nor a python3 with pytest and pyyaml: the tests cannot run (crissp/deploy/requirements.txt)"
fi

if [ "$failed" = 0 ]; then echo "deploy: green"; else echo "deploy: red"; fi
exit "$failed"
