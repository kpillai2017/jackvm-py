"""
decompiler_link.py - Open the running program in the Jack decompiler.
====================================================================

jack-decompiler (https://github.com/kpillai2017/jack-decompiler) turns
.vm files back into readable Jack source, in its own window. When it's
installed, Ctrl+U ("un-compile") in the player opens the program that's
running in it:

    jackvm  --Ctrl+U-->  jackdecomp <the program's .vm files>

Like jack-compiler, the decompiler is a separate app in its own repository:
it's found by integrations.find() and started as a command, never imported.
It's looked for the same four ways (see integrations.py):

  1. $JACKDECOMP, e.g.  JACKDECOMP="python3 -m jack_decompiler"  (or "off")
  2. the config file:   [apps]  jackdecomp = ~/code/jack-decompiler
  3. the same Python environment (its "jack_tools" entry point "decompiler")
  4. a `jackdecomp` command on the PATH

The first time it isn't found, Ctrl+U asks where it is (locate_app.py)
and saves the answer in the config file.

The App description lives here rather than in integrations.py, because
integrations.py must stay identical to jack-compiler's copy.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, Optional, Sequence, Tuple

from .integrations import App, Companion, can_configure, find, not_found_message
from .locate_app import locate

JACKDECOMP = App(
    "decompiler", "Jack decompiler", "JACKDECOMP", "jackdecomp",
    "git clone https://github.com/kpillai2017/jack-decompiler.git && pip install -e ./jack-decompiler",
    entry="jack_decompiler.main:main", repo="jack-decompiler",
)  # fmt: skip


class Decompiler:
    """The Jack decompiler, if installed (`app` is None when it isn't)."""

    def __init__(self, finder: Callable[[], Optional[Companion]] = lambda: find(JACKDECOMP)) -> None:
        self._finder = finder
        self.refresh()

    def refresh(self) -> None:
        """Look for it again (e.g. after its folder was saved in the config file)."""
        self.app = self._finder()

    def can_locate(self) -> bool:
        """Is it missing, and could the user point us at it (see locate)?"""
        return self.app is None and can_configure(JACKDECOMP)

    def locate(self, surface) -> Tuple[str, str]:
        """
        Ask the user where jack-decompiler is, in a folder chooser drawn on
        `surface`. Returns (outcome, message): outcome is locate_app's
        FOUND, CANCEL or QUIT.
        """
        outcome, companion, message = locate(surface, JACKDECOMP)
        if companion is not None:
            self.refresh()
            if self.app is None:  # (the config file couldn't be saved)
                self.app = companion
        return outcome, message

    def shortcut_label(self) -> str:
        """What the SHORTCUTS box says about Ctrl+U."""
        if self.app is not None:
            return "Ctrl+U decompile"
        return "Ctrl+U find decompiler..." if self.can_locate() else "Ctrl+U decompiler (not installed)"

    def open(self, files: Sequence[Path]) -> str:
        """Ctrl+U: open these .vm files in the decompiler's window. Returns a message for the user."""
        vm_files = [Path(f) for f in files if Path(f).suffix == ".vm" and Path(f).is_file()]
        if not vm_files:
            return "No .vm files to decompile"
        if self.app is None:
            return not_found_message(JACKDECOMP)
        try:
            self.app.launch([str(f) for f in vm_files], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as problem:
            return f"Couldn't start the Jack decompiler: {problem}"
        what = vm_files[0].parent.name + "/" if len(vm_files) > 1 else vm_files[0].name
        return f"Opened {what} in the Jack decompiler"
