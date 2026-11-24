"""The website (site/, built by site/build.sh for GitHub Pages) never names a version by hand: the build fills in the
one in VERSION, so the site says the version that is on PyPI once it is released."""

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]


def test_the_site_names_no_version_by_hand_and_the_build_fills_in_version(tmp_path):
    page = (REPO / "site" / "index.html").read_text(encoding="utf-8")
    assert "{{VERSION}}" in page and not re.search(r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])", page)  # 127.0.0.1 is no version
    site = tmp_path / "site"
    shutil.copytree(REPO / "site", site, ignore=shutil.ignore_patterns("_site"))
    (tmp_path / "VERSION").write_text("9.8.7\n")
    shutil.copytree(REPO / "crissp" / "look", tmp_path / "crissp" / "look")
    shutil.copytree(REPO / "docs" / "images", tmp_path / "docs" / "images")
    subprocess.run(["bash", str(site / "build.sh")], check=True, capture_output=True)
    built = (site / "_site" / "index.html").read_text(encoding="utf-8")
    assert "C.R.I.S.S.P. 9.8.7 for Shop" in built and "{{VERSION}}" not in built
