"""The framework's own files are generic: they name no product they came from, no person, no private cluster and no
other product's backlog. What a product is called comes from its configuration (suites.json, the uxsuite's team.json).
The words are kept as SHA-256 hashes of the lower-case word, and the patterns spelled in parts, so this guard does not
name them either. Read: the testsuite, the uxsuite, the look, the crissp tool, the scripts, and the template's parts."""

import hashlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
WORDS = {
    "a7e88c6179b8acc23fa52642b9d88e1c605b4c4edd580a496e8945b3b1117e15", "6a34ca257c90f92a08cc7c64ffe0dce14454f8382843761a9c574b3a9a00cb81",
    "9b9a7d0d8156089b79f3cdd32bd46e449e8cd2a5e78c1dbdf866991dbc09a230", "9cc57c91e044a25c6ec91d81909c53781c9e144da095310b67a0ce7897f9f669",
    "0cbb043abe19b54d875da33d48de6c158a2d5c6cec48f6461e06322eff56455c", "bcc017d98327ac5346afd954b28504e4ebc0f7d807415f2b9b190e59a1603273",
    "ef24d5e64656cc41052c333013cbb262994d6ff7187364bd05dbf6cfc0472c62", "61bffea9215f65164ad18b45aff1436c0c165d0d5dd2087ef61b4232ba6d2c1a",
    "da0daaba4b156961c049ab4b85b6d0bcba2872200b7dedb4aa77f9208c601444", "ed078c3b90083544d15d50dc70d2bd70465ce5fa96b81fea2e163dc40e39af22",
    "964ca863a05cf6824621ce8948c156f2699020dbed94cddccf079d0254b7ad89",
}
# a product's name as a proper noun, its packages and paths, another backlog's ids, the old place of the UX suite
PATTERNS = re.compile("|".join([r"\bF" + r"low\b", "liquid" + "-nitro", "@f" + "low/", "apps/f" + "low", r"\bE3[02]-", r"\bT-5\d\b",
                                r"\bK-2" + r"1\b", "design/" + "uxsuite", "low-code " + "platform"]))
OWNED = ["crissp/testsuite", "crissp/uxsuite", "crissp/look", "crissp/tool", "crissp/check.sh", "crissp/check-all.sh",
         "crissp/test.sh", "crissp/ux.sh", "crissp/template/crissp/uxsuite", "crissp/template/crissp/testsuite"]
LOCAL = {"results", "__pycache__", ".venv", "node_modules"}


def private(text: str) -> list[str]:
    words = {w for w in re.findall(r"[a-z0-9]+", text.lower()) if hashlib.sha256(w.encode()).hexdigest() in WORDS}
    return sorted(words) + [m.group(0) for m in PATTERNS.finditer(text)]


def owned(repo: Path = REPO) -> list[Path]:
    out = []
    for name in OWNED:
        path = repo / name
        files = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else []
        out += [p for p in files if not LOCAL & set(p.relative_to(repo).parts) and p.suffix not in (".woff2", ".png")]
    return out


def test_the_guard_finds_a_name_a_pattern_and_leaves_plain_words_alone():
    name = "wand" + "vol"
    assert private(f"Deploy {name.upper()} to the cluster") == [name]
    assert private("the " + "F" + "low suite") == ["F" + "low"] and private("see E3" + "2-OC-01") == ["E3" + "2-"]
    assert private("a workflow, the flow of work, overflow: hidden, K-2, E3-01") == []


@pytest.mark.parametrize("name", OWNED)
def test_every_part_of_the_framework_is_there(name):
    if name == "crissp/template/crissp/testsuite" and not (REPO / name).exists():
        pytest.skip("no testsuite skeleton in the template")
    assert (REPO / name).exists()


def test_the_framework_s_own_files_name_no_private_product_or_person():
    hits = [f"{p.relative_to(REPO)}: {', '.join(found)}" for p in owned()
            if (found := private(p.read_text(errors="replace")) + private(str(p.relative_to(REPO))))]
    assert hits == []
