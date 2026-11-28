"""crissp/testsuite/lib/tools.py: the scanners crissp brings itself (trivy, gitleaks), one pinned version each, fetched
once from its release, checked against the SHA-256 written in tools.py, kept in the crissp cache. Never a download in
a test: the fetch is stood in."""

import hashlib
import importlib.util
import io
import os
import re
import runpy
import sys
import tarfile
from pathlib import Path

import pytest

LIB = Path(__file__).resolve().parents[1] / "lib"
spec = importlib.util.spec_from_file_location("tools_under_test", LIB / "tools.py")
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


def tarball(name: str, body: bytes) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for member, data in (("README.md", b"readme"), (name, body)):
            info = tarfile.TarInfo(member)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return out.getvalue()


@pytest.fixture
def pinned(monkeypatch):
    """A tool pinned to an archive this test makes, for the system the test says it runs on."""
    archive = tarball("scanner", b"#!/bin/sh\necho scanned\n")
    monkeypatch.setitem(
        tools.TOOLS,
        "scanner",
        {
            "version": "1.2.3",
            "binary": "scanner",
            "url": "https://example.test/v{version}/{asset}",
            "assets": {"linux-x86_64": ("scanner_1.2.3_linux_x64.tar.gz", hashlib.sha256(archive).hexdigest())},
        },
    )
    fetched = []

    def fetch(url):
        fetched.append(url)
        return archive

    return fetched, fetch


def env(tmp_path):
    return {"CRISSP_CACHE": str(tmp_path / "cache")}


def test_every_pin_names_a_version_and_a_checksum_for_every_system():
    for name, tool in tools.TOOLS.items():
        assert tool["version"] and tool["binary"] == name
        assert set(tool["assets"]) == set(tools.SYSTEMS), name
        for asset, sha in tool["assets"].values():
            assert tool["version"] in asset and asset.endswith(".tar.gz") and len(sha) == 64, (name, asset)


@pytest.mark.parametrize(
    "platform, machine, system",
    [
        ("linux", "x86_64", "linux-x86_64"),
        ("linux", "aarch64", "linux-arm64"),
        ("darwin", "arm64", "darwin-arm64"),
        ("darwin", "x86_64", "darwin-x86_64"),
        ("linux", "AMD64", "linux-x86_64"),
    ],
)
def test_the_system_is_named_the_way_the_pins_are(platform, machine, system):
    assert tools.system(platform, machine) == system


def test_a_system_without_a_pin_is_said_plainly():
    with pytest.raises(tools.ToolError, match=r"no pinned build for win32-x86_64.*WSL 2"):
        tools.system("win32", "AMD64")
    with pytest.raises(tools.ToolError, match="no pinned build for linux-riscv64"):
        tools.system("linux", "riscv64")


def test_the_cache_is_crissp_cache_then_xdg_then_home(tmp_path):
    assert tools.cache({"CRISSP_CACHE": "/c"}) == Path("/c/tools")
    assert tools.cache({"XDG_CACHE_HOME": "/x"}) == Path("/x/crissp/tools")
    assert tools.cache({"HOME": "/h"}) == Path("/h/.cache/crissp/tools")


def test_a_tool_is_fetched_once_checked_and_kept(pinned, tmp_path):
    fetched, fetch = pinned
    path = tools.ensure("scanner", env(tmp_path), fetch, "linux-x86_64")
    assert path == tmp_path / "cache/tools/scanner-1.2.3/scanner"
    assert path.read_bytes() == b"#!/bin/sh\necho scanned\n" and os.access(path, os.X_OK)
    assert fetched == ["https://example.test/v1.2.3/scanner_1.2.3_linux_x64.tar.gz"]
    assert tools.ensure("scanner", env(tmp_path), fetch, "linux-x86_64") == path
    assert len(fetched) == 1  # cached: not fetched again


def test_a_download_that_differs_from_the_pin_is_refused_and_nothing_is_kept(pinned, tmp_path):
    with pytest.raises(tools.ToolError, match=r"checksum.*refused"):
        tools.ensure("scanner", env(tmp_path), lambda url: tarball("scanner", b"something else"), "linux-x86_64")
    assert not (tmp_path / "cache/tools/scanner-1.2.3").exists()


def test_an_archive_without_the_binary_is_a_problem(monkeypatch, tmp_path):
    archive = tarball("other", b"x")
    monkeypatch.setitem(
        tools.TOOLS,
        "scanner",
        {
            "version": "1",
            "binary": "scanner",
            "url": "https://example.test/{asset}",
            "assets": {"linux-x86_64": ("s.tar.gz", hashlib.sha256(archive).hexdigest())},
        },
    )
    with pytest.raises(tools.ToolError, match=re.escape("no scanner in s.tar.gz")):
        tools.ensure("scanner", env(tmp_path), lambda url: archive, "linux-x86_64")


def test_a_download_that_fails_is_a_problem(pinned, tmp_path):
    def broken(url):
        raise OSError("network unreachable")

    with pytest.raises(tools.ToolError, match=r"could not fetch scanner 1.2.3.*network unreachable"):
        tools.ensure("scanner", env(tmp_path), broken, "linux-x86_64")


def test_an_unknown_tool_is_refused(tmp_path):
    with pytest.raises(tools.ToolError, match="unknown tool nmap"):
        tools.ensure("nmap", env(tmp_path))


def test_fetch_reads_the_url(monkeypatch):
    class Answer(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    asked = []
    monkeypatch.setattr(
        tools.urllib.request, "urlopen", lambda url, timeout: asked.append((url, timeout)) or Answer(b"bytes")
    )
    assert tools.fetch("https://example.test/a") == b"bytes"
    assert asked == [("https://example.test/a", tools.TIMEOUT)]


def test_this_machine_is_asked_when_no_system_is_given(pinned, monkeypatch, tmp_path):
    _, fetch = pinned
    monkeypatch.setattr(tools, "system", lambda: "linux-x86_64")
    assert tools.ensure("scanner", env(tmp_path), fetch).name == "scanner"


def test_path_prints_where_the_tool_is(pinned, monkeypatch, tmp_path, capsys):
    _, fetch = pinned
    monkeypatch.setattr(tools, "fetch", fetch)
    monkeypatch.setattr(tools, "system", lambda: "linux-x86_64")
    monkeypatch.setattr(tools.os, "environ", env(tmp_path))
    assert tools.main(["tools.py", "path", "scanner"]) == 0
    assert capsys.readouterr().out.strip() == str(tmp_path / "cache/tools/scanner-1.2.3/scanner")
    assert tools.main(["tools.py", "path", "nmap"]) == 1
    assert "unknown tool nmap" in capsys.readouterr().err
    assert tools.main(["tools.py"]) == 2


def test_the_script_runs_main(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["tools.py"])
    with pytest.raises(SystemExit) as done:
        runpy.run_path(str(LIB / "tools.py"), run_name="__main__")
    assert done.value.code == 2
