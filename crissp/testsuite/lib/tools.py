"""The scanners crissp brings itself: one pinned version of each, never the one a machine happens to have on its PATH.

A tool is fetched once from its release (the archive for this system), checked against the SHA-256 written below, and
kept in the crissp cache: CRISSP_CACHE/tools, else XDG_CACHE_HOME/crissp/tools, else ~/.cache/crissp/tools. A download
that differs from the pin is refused and nothing is kept, so a release that was replaced afterwards never runs. Moving
a pin is a change to this file: the new version and the checksums from the release's own checksums file.
The guards are bash, so on Windows they run in WSL 2, which is Linux: there is no Windows pin.

    python3 crissp/testsuite/lib/tools.py path <tool>     fetch it when it is not cached yet, print where it is
"""

import hashlib
import io
import os
import platform as _platform
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

TIMEOUT = 300
SYSTEMS = ("linux-x86_64", "linux-arm64", "darwin-x86_64", "darwin-arm64")
TOOLS = {
    "trivy": {  # CVEs and misconfigurations (lib/audit.py run)
        "version": "0.76.2", "binary": "trivy",
        "url": "https://github.com/aquasecurity/trivy/releases/download/v{version}/{asset}",
        "assets": {
            "linux-x86_64": ("trivy_0.76.2_Linux-64bit.tar.gz",
                             "bc0fc726e017b8927a62b2d3531d7a84ee01769daf5c99ed866dced54089fdbf"),
            "linux-arm64": ("trivy_0.76.2_Linux-ARM64.tar.gz",
                            "ab9d51f86e6a5fb936f605faff6b593ac51bc378fff4d3e8b9d58358b9c367c3"),
            "darwin-x86_64": ("trivy_0.76.2_macOS-64bit.tar.gz",
                              "e08bb9ea449ecf66c6bfb03cbb8697c503ff33d35fc585c9747e3eaeb7ed4c7b"),
            "darwin-arm64": ("trivy_0.76.2_macOS-ARM64.tar.gz",
                             "ae7ea358326960406b703c77b2ac490190797d80b306b5b50c2a27221da0a5b8")}},
    "gitleaks": {  # secrets in the git history (lib/audit.py secrets)
        "version": "8.30.1", "binary": "gitleaks",
        "url": "https://github.com/gitleaks/gitleaks/releases/download/v{version}/{asset}",
        "assets": {
            "linux-x86_64": ("gitleaks_8.30.1_linux_x64.tar.gz",
                             "551f6fc83ea457d62a0d98237cbad105af8d557003051f41f3e7ca7b3f2470eb"),
            "linux-arm64": ("gitleaks_8.30.1_linux_arm64.tar.gz",
                            "e4a487ee7ccd7d3a7f7ec08657610aa3606637dab924210b3aee62570fb4b080"),
            "darwin-x86_64": ("gitleaks_8.30.1_darwin_x64.tar.gz",
                              "dfe101a4db2255fc85120ac7f3d25e4342c3c20cf749f2c20a18081af1952709"),
            "darwin-arm64": ("gitleaks_8.30.1_darwin_arm64.tar.gz",
                             "b40ab0ae55c505963e365f271a8d3846efbc170aa17f2607f13df610a9aeb6a5")}},
}
MACHINES = {"x86_64": "x86_64", "amd64": "x86_64", "aarch64": "arm64", "arm64": "arm64"}


class ToolError(Exception):
    """A pinned tool that cannot be had: said as a problem, never a pass."""


def system(platform: str = sys.platform, machine: str = _platform.machine()) -> str:
    name = f"{platform}-{MACHINES.get(machine.lower(), machine.lower())}"
    if name not in SYSTEMS:
        hint = " (on Windows the guards run in WSL 2: run them there)" if platform == "win32" else ""
        raise ToolError(f"no pinned build for {name}{hint}")
    return name


def cache(env: dict) -> Path:
    if env.get("CRISSP_CACHE"):
        return Path(env["CRISSP_CACHE"]) / "tools"
    base = Path(env["XDG_CACHE_HOME"]) if env.get("XDG_CACHE_HOME") else Path(env.get("HOME", "~")) / ".cache"
    return base / "crissp" / "tools"


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as answer:  # noqa: S310 - a pinned https release URL, never from outside
        return answer.read()


def ensure(name: str, env: dict, fetcher=None, where: str | None = None) -> Path:
    """The pinned tool's binary: from the cache, or fetched, checked and kept there first."""
    if name not in TOOLS:
        raise ToolError(f"unknown tool {name} (crissp pins {', '.join(sorted(TOOLS))})")
    tool = TOOLS[name]
    folder = cache(env) / f"{name}-{tool['version']}"
    binary = folder / tool["binary"]
    if binary.is_file():
        return binary
    asset, sha = tool["assets"][where or system()]
    url = tool["url"].format(version=tool["version"], asset=asset)
    try:
        data = (fetcher or fetch)(url)
    except OSError as e:
        raise ToolError(f"could not fetch {name} {tool['version']} from {url}: {e}") from e
    if hashlib.sha256(data).hexdigest() != sha:
        raise ToolError(f"{asset}: the checksum differs from the pin in lib/tools.py: refused, nothing kept")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = next((m for m in tar.getmembers() if m.isfile() and m.name == tool["binary"]), None)
        if member is None:
            raise ToolError(f"no {tool['binary']} in {asset}")
        body = tar.extractfile(member).read()  # only this file's bytes: nothing in the archive picks a path
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=folder, delete=False) as tmp:
        tmp.write(body)
    os.chmod(tmp.name, 0o755)  # noqa: S103 - a program: everyone may run it, only its owner may change it
    os.replace(tmp.name, binary)  # whole or not at all: a stopped download never leaves half a tool
    return binary


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[1] != "path":
        print(__doc__, file=sys.stderr)
        return 2
    try:
        print(ensure(argv[2], dict(os.environ)))
    except ToolError as e:
        print(f"tools: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
