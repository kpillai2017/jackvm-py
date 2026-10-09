"""
integrations.py - Find the companion app (jack-compiler <-> jackvm-py).
=====================================================================

jack-compiler and jackvm-py live in two separate git repositories, and
neither one *needs* the other. But when both are installed, each one can
offer a shortcut to the other:

    jackc-gui  --Ctrl+J-->  jackvm        run the compiled program
    jackvm     ---------->  jackc         compile a folder of .jack files
    jackvm     --Ctrl+J-->  jackc-gui     open the sources in the compiler

The two apps only ever talk through each other's COMMAND LINE (they never
import each other's code), so either one can change its insides freely and
still work with an older or newer copy of the other.

How the other app is found
--------------------------
`find(app)` tries these, in order, and uses the first that works:

  1. An environment variable, e.g.  JACKVM="python3 -m jackvm"
     (set it to "off" to switch the integration off).
  2. The same Python environment: each package advertises itself under the
     "jack_tools" entry-point group in its pyproject.toml, so after
         pip install -e ../jackvm-py      (or ../jack-compiler)
     the other app is found with no configuration at all.
  3. The PATH: a `jackvm` / `jackc` / `jackc-gui` command installed
     anywhere else (another virtual environment, pipx, ...).

If none of them works, `find()` returns None and the GUI shows how to
install the missing app instead of the shortcut.

This file is shared: the same copy lives in both repositories
(jack_compiler/integrations.py and jackvm/integrations.py). If you change
one, copy it over the other: tests/test_shared_files.py in each repository
fails when the two differ (CI fetches the other repository to compare).
It only uses the standard library, and works on Python 3.8+.
"""

from __future__ import annotations

import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Callable, Iterable, List, Mapping, Optional, Sequence

ENTRY_POINT_GROUP = "jack_tools"
OFF_VALUES = {"0", "off", "no", "none", "false", "disable", "disabled"}


@dataclass(frozen=True)
class App:
    """One app that may (or may not) be installed."""

    key: str  # its entry-point name in the "jack_tools" group
    title: str  # what the GUIs call it
    env_var: str  # environment variable that overrides the lookup
    executable: str  # command name to look for on the PATH
    install_hint: str  # how to get it, shown when it isn't found


JACKVM = App(
    "vm", "JackVM", "JACKVM", "jackvm",
    "git clone https://github.com/kpillai2017/jackvm-py.git && pip install -e ./jackvm-py",
)  # fmt: skip
JACKC = App(
    "compiler", "Jack compiler", "JACKC", "jackc",
    "git clone https://github.com/kpillai2017/jack-compiler.git && pip install -e './jack-compiler[gui]'",
)  # fmt: skip
JACKC_GUI = App("compiler-gui", "Jack compiler GUI", "JACKC_GUI", "jackc-gui", JACKC.install_hint)


@dataclass(frozen=True)
class Companion:
    """An app that was found: how to run it, and how it was found."""

    app: App
    command: List[str]  # the command line, before any arguments
    found_by: str  # e.g. "PATH", "$JACKVM", "same Python environment"

    def run(self, args: Sequence[str], timeout: Optional[float] = None) -> subprocess.CompletedProcess:
        """Run it, wait for it to finish, and capture what it prints."""
        return subprocess.run(
            [*self.command, *args], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=timeout,
        )  # fmt: skip

    def launch(self, args: Sequence[str], **popen_options) -> subprocess.Popen:
        """Start it in the background (e.g. a second window) and return at once."""
        return subprocess.Popen([*self.command, *args], **popen_options)

    def describe(self) -> str:
        return f"{self.app.title} (found via {self.found_by})"


def split_command(text: str) -> List[str]:
    """
    Split a command such as  python3 -m jackvm  into its words. Quotes
    group words with spaces; Windows paths keep their backslashes.
    """
    if os.name == "nt":
        return [word.strip('"') for word in shlex.split(text, posix=False)]
    return shlex.split(text)


def _jack_tools_entry_points() -> list:
    from importlib import metadata

    found = metadata.entry_points()
    if hasattr(found, "select"):  # Python 3.10+
        return list(found.select(group=ENTRY_POINT_GROUP))
    return list(found.get(ENTRY_POINT_GROUP, []))  # Python 3.8 / 3.9: a dict


def _importable(module: str) -> bool:
    """False for a stale install whose code has been moved or deleted."""
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def entry_point_command(value: str, program_name: str) -> List[str]:
    """
    A command line that runs an entry point such as "jackvm.main:main" with
    this same Python interpreter - like the script pip would have made.
    """
    module, _, function = value.partition(":")
    code = (
        f"import sys; sys.argv[0] = {program_name!r}; "
        f"from {module} import {function or 'main'} as main; sys.exit(main())"
    )
    return [sys.executable, "-c", code]


def find(
    app: App,
    environ: Optional[Mapping[str, str]] = None,
    entry_points: Optional[Iterable] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> Optional[Companion]:
    """
    Look for `app` (see the module docstring for the order). The keyword
    arguments exist so tests can fake the environment, the installed
    packages and the PATH.
    """
    environ = os.environ if environ is None else environ

    # 1. An explicit setting always wins.
    override = environ.get(app.env_var, "").strip()
    if override:
        if override.lower() in OFF_VALUES:
            return None
        return Companion(app, split_command(override), f"${app.env_var}")

    # 2. Installed in this same Python environment.
    try:
        points = list(entry_points) if entry_points is not None else _jack_tools_entry_points()
    except Exception:  # broken package metadata must never stop the GUI
        points = []
    for point in points:
        if point.name == app.key and _importable(point.value.partition(":")[0]):
            return Companion(app, entry_point_command(point.value, app.executable), "same Python environment")

    # 3. Anywhere on the PATH.
    path = which(app.executable)
    if path:
        return Companion(app, [path], "PATH")
    return None
