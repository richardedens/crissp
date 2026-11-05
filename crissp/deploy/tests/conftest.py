"""Shared paths and the chart renderer for crissp/deploy/tests: the chart is proven by rendering it (helm template),
never by installing it; the Terraform files by reading them, never by applying them."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ENGINE = Path(__file__).resolve().parents[1]
_PROJECT = Path(os.environ.get("CRISSP_ROOT") or os.getcwd()) / "crissp" / "deploy"
DEPLOY = _PROJECT if (_PROJECT / "helm").is_dir() else ENGINE  # the project's own chart and Terraform, else the template
CHART = DEPLOY / "helm" / "app"
TERRAFORM = DEPLOY / "terraform"
HELM = shutil.which("helm")


def render(*sets: str, values: list[Path] | None = None, release: str = "shop", namespace: str = "shop") -> list[dict]:
    if HELM is None:
        pytest.fail("helm is not installed: the chart cannot be proven (crissp/deploy/check.sh needs it)")
    argv = [HELM, "template", release, str(CHART), "--namespace", namespace]
    for v in values or []:
        argv += ["-f", str(v)]
    for s in sets:
        argv += ["--set", s]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    if done.returncode:
        raise AssertionError(done.stderr)
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def one(docs: list[dict], kind: str, name: str) -> dict:
    found = [d for d in docs if d["kind"] == kind and d["metadata"]["name"] == name]
    assert len(found) == 1, f"{kind}/{name}: {len(found)}"
    return found[0]


def pods(docs: list[dict]):
    """(document, pod spec) for every workload."""
    for d in docs:
        spec = d.get("spec", {})
        pod = spec.get("template", {}).get("spec") or spec.get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec")
        if pod:
            yield d, pod
