"""
test_shared_files.py - the shared files must match jack-compiler's copy.
========================================================================

jackvm-py and jack-compiler live in separate git repositories, but share two
files word for word: integrations.py, the code that lets each app find the
other, and locate_app.py, the window that asks where it is. This test
fails if the copies drift apart, so a fix made in one repository isn't
forgotten in the other.

Where is the other repository's copy?
  * $JACK_TOOLS_COMPANION - a checkout of jack-compiler (CI clones one there:
    the branch with the same name as this one if it exists, else main), or
  * a sibling folder, ../jack-compiler, next to this checkout.

The test is SKIPPED when neither exists (e.g. you only cloned this repo),
or when the other side doesn't have the file yet. When CI sets
$JACK_TOOLS_COMPANION, a missing checkout is an error rather than a skip.

To fix a failure: decide which copy is right, copy it over the other one,
and commit it in BOTH repositories.
"""

import difflib
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
COMPANION = "jack-compiler"
SHARED_FILES = [
    # (path in this repository, path in the companion repository)
    ("jackvm/integrations.py", "jack_compiler/integrations.py"),
    ("jackvm/locate_app.py", "jack_compiler/locate_app.py"),
]


def companion_root() -> Path:
    configured = os.environ.get("JACK_TOOLS_COMPANION")
    if configured:
        root = Path(configured).expanduser()
        if not root.is_dir():
            pytest.fail(f"JACK_TOOLS_COMPANION={configured} is not a folder")
        return root
    root = ROOT.parent / COMPANION
    if not root.is_dir():
        pytest.skip(f"no {COMPANION} checkout next to this one (set JACK_TOOLS_COMPANION to compare)")
    return root


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")  # Windows checkouts may use CRLF


@pytest.mark.parametrize("ours, theirs", SHARED_FILES)
def test_shared_file_matches_the_companion_repository(ours, theirs):
    other = companion_root() / theirs
    if not other.is_file():
        pytest.skip(f"{COMPANION} has no {theirs} yet")
    mine, their_copy = read(ROOT / ours), read(other)
    if mine != their_copy:
        diff = difflib.unified_diff(
            their_copy.splitlines(keepends=True), mine.splitlines(keepends=True),
            fromfile=f"{COMPANION}/{theirs}", tofile=ours,
        )  # fmt: skip
        shown = "".join(list(diff)[:60])
        pytest.fail(f"{ours} differs from {COMPANION}'s copy - copy the right one over the other:\n{shown}")
