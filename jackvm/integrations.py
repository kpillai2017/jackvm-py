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
  2. The config file, shared by both apps (see `config_path()`):
         ~/.config/jack-tools/config.ini   (%APPDATA%\\jack-tools\\config.ini on Windows)
         [apps]
         jackvm = ~/code/jackvm-py         # a checkout: its venv's jackvm is used
         jackc = /opt/jack/venv/bin/jackc  # ...or the command itself
     A folder is searched for the command: in the folder itself, its bin/,
     or a virtual environment inside it (.venv, venv, env, .direnv/*).
     A checkout that only had `pip install -r requirements.txt` (so there's
     no command) is run from its source with that environment's Python.
     jackc-gui is also found in the folder given for jackc. "off" works here too.
     The GUIs can write this file for you: when the other app isn't found,
     Ctrl+J asks where it is (see locate_app.py).
  3. The same Python environment: each package advertises itself under the
     "jack_tools" entry-point group in its pyproject.toml, so after
         pip install -e ../jackvm-py      (or ../jack-compiler)
     the other app is found with no configuration at all.
  4. The PATH: a `jackvm` / `jackc` / `jackc-gui` command installed
     anywhere else (another virtual environment, pipx, ...).

If none of them works, `find()` returns None and the GUI shows
`not_found_message(app)`: how to install or configure the missing app.

This file is shared: the same copy lives in both repositories
(jack_compiler/integrations.py and jackvm/integrations.py). If you change
one, copy it over the other: tests/test_shared_files.py in each repository
fails when the two differ (CI fetches the other repository to compare).
It only uses the standard library, and works on Python 3.8+.
"""

from __future__ import annotations

import configparser
import importlib.util
import os
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Mapping, Optional, Sequence

ENTRY_POINT_GROUP = "jack_tools"
OFF_VALUES = {"0", "off", "no", "none", "false", "disable", "disabled"}
CONFIG_ENV_VAR = "JACK_TOOLS_CONFIG"  # points at a different config file
CONFIG_SECTION = "apps"
VENV_FOLDERS = (".venv", "venv", "env", ".direnv/*")  # where a checkout's virtual environment may be


@dataclass(frozen=True)
class App:
    """One app that may (or may not) be installed."""

    key: str  # its entry-point name in the "jack_tools" group
    title: str  # what the GUIs call it
    env_var: str  # environment variable that overrides the lookup
    executable: str  # command name to look for on the PATH (and its key in the config file)
    install_hint: str  # how to get it, shown when it isn't found
    config_fallback: str = ""  # another config key whose FOLDER also holds this app
    entry: str = ""  # its "module:function", to run it from a checkout that wasn't pip-installed
    repo: str = ""  # its repository's (usual) folder name


JACKVM = App(
    "vm", "JackVM", "JACKVM", "jackvm",
    "git clone https://github.com/kpillai2017/jackvm-py.git && pip install -e ./jackvm-py",
    entry="jackvm.main:main", repo="jackvm-py",
)  # fmt: skip
JACKC = App(
    "compiler", "Jack compiler", "JACKC", "jackc",
    "git clone https://github.com/kpillai2017/jack-compiler.git && pip install -e './jack-compiler[gui]'",
    entry="jack_compiler.compiler:main", repo="jack-compiler",
)  # fmt: skip
JACKC_GUI = App(
    "compiler-gui", "Jack compiler GUI", "JACKC_GUI", "jackc-gui", JACKC.install_hint, "jackc",
    entry="jack_compiler.gui.main:main", repo="jack-compiler",
)  # fmt: skip


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


def entry_point_command(
    value: str, program_name: str, python: Optional[str] = None, source_folder: Optional[Path] = None
) -> List[str]:
    """
    A command line that runs an entry point such as "jackvm.main:main" with
    `python` (default: this same interpreter) - like the script pip would
    have made. With `source_folder`, the code is imported from that checkout.
    """
    module, _, function = value.partition(":")
    path = f"sys.path.insert(0, {str(source_folder)!r}); " if source_folder is not None else ""
    code = (
        f"import sys; {path}sys.argv[0] = {program_name!r}; "
        f"from {module} import {function or 'main'} as main; sys.exit(main())"
    )
    return [python or sys.executable, "-c", code]


def config_path(environ: Optional[Mapping[str, str]] = None) -> Optional[Path]:
    """
    Where the shared config file is: $JACK_TOOLS_CONFIG if it's set, else
    %APPDATA%\\jack-tools\\config.ini on Windows, else
    $XDG_CONFIG_HOME/jack-tools/config.ini (normally ~/.config/...).
    Only `environ` is consulted, so tests with a fake one never see the
    real file. None if there's no home folder to put it in.
    """
    environ = os.environ if environ is None else environ
    explicit = environ.get(CONFIG_ENV_VAR, "").strip()
    if explicit:
        return Path(explicit).expanduser()
    if os.name == "nt" and environ.get("APPDATA"):
        return Path(environ["APPDATA"]) / "jack-tools" / "config.ini"
    base = environ.get("XDG_CONFIG_HOME") or (environ.get("HOME") and str(Path(environ["HOME"]) / ".config"))
    return Path(base) / "jack-tools" / "config.ini" if base else None


def read_config(path: Optional[Path]) -> Dict[str, str]:
    """The [apps] section of the config file, e.g. {"jackvm": "~/jackvm-py"}; {} if there is none."""
    if path is None or not path.is_file():
        return {}
    parser = configparser.ConfigParser(interpolation=None)
    try:
        parser.read(path, encoding="utf-8")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return {}  # a broken config file must never stop the GUI (not_found_message explains)
    if not parser.has_section(CONFIG_SECTION):
        return {}
    return {key: value.strip() for key, value in parser.items(CONFIG_SECTION) if value.strip()}


def _as_folder(value: str) -> Optional[Path]:
    """The folder a config value names, or None if it isn't one (then it's a command)."""
    value = value.strip().strip("\"'")
    if not value:
        return None  # (Path("") would be the current folder)
    folder = Path(value).expanduser()
    return folder if folder.is_dir() else None


def command_in_folder(folder: Path, executable: str) -> Optional[str]:
    """
    Find `executable` in a folder from the config file: the folder itself
    (a bin/ folder), its bin/ (a virtual environment), or a virtual
    environment inside it (a checkout of the other repository).
    """
    names = [executable + ".exe", executable] if os.name == "nt" else [executable]
    bins = ["Scripts", "bin"] if os.name == "nt" else ["bin"]
    places = [folder, *(folder / b for b in bins)]
    for pattern in VENV_FOLDERS:
        for venv in sorted(folder.glob(pattern)):
            places += [venv / b for b in bins]
    for place in places:
        for name in names:
            candidate = place / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
    return None


def python_in_folder(folder: Path) -> Optional[str]:
    """The Python of a virtual environment inside a checkout (.venv, venv, env, .direnv/*), if any."""
    for name in ("python", "python3"):
        found = command_in_folder(folder, name)
        if found and Path(found).parent != folder:  # a python in a bin/ folder, not a stray file
            return found
    return None


def source_command(folder: Path, app: App) -> Optional[List[str]]:
    """
    Run `app` straight from a checkout whose requirements were installed
    (pip install -r requirements.txt) but which wasn't pip-installed itself,
    so it has no `jackvm` / `jackc` command: its venv's Python imports the
    code from the folder.
    """
    package = app.entry.partition(":")[0].split(".")[0]
    if not package or not (folder / package / "__init__.py").is_file():
        return None
    python = python_in_folder(folder)
    return entry_point_command(app.entry, app.executable, python, folder.resolve()) if python else None


def command_for_folder(folder: Path, app: App) -> Optional[List[str]]:
    """How to run `app` from a folder: its installed command, else its source code."""
    command = command_in_folder(folder, app.executable)
    return [command] if command else source_command(folder, app)


def check_folder(app: App, folder: Path) -> Optional[Companion]:
    """Is `app` usable from this folder (e.g. one the user chose in the GUI)? Its Companion, or None."""
    folder = Path(folder).expanduser()
    command = command_for_folder(folder, app) if folder.is_dir() else None
    return Companion(app, command, f"folder {folder}") if command else None


def can_configure(app: App, environ: Optional[Mapping[str, str]] = None) -> bool:
    """
    Would saving a folder in the config file change anything? Not when the
    environment variable is set (it wins over the file) or the app was
    switched off on purpose.
    """
    environ = os.environ if environ is None else environ
    if environ.get(app.env_var, "").strip():
        return False
    path = config_path(environ)
    return path is not None and read_config(path).get(app.executable, "").lower() not in OFF_VALUES


def save_setting(key: str, value: str, environ: Optional[Mapping[str, str]] = None) -> Path:
    """
    Set `key = value` in the [apps] section of the config file, creating the
    file (and its folder) if needed. Everything else in the file - other
    settings, comments - is kept. Returns the file's path. Raises OSError
    if it can't be written.
    """
    path = config_path(environ)
    if path is None:
        raise OSError("there's no home folder to keep the config file in")
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    except UnicodeDecodeError:
        lines = []
    new_line = f"{key} = {value}"
    section, header, done = "", None, False
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            section = stripped[1:-1].strip().lower()
            if section == CONFIG_SECTION:
                header = index
        elif section == CONFIG_SECTION and stripped.split("=", 1)[0].strip().lower() == key.lower() and "=" in stripped:
            lines[index] = new_line
            done = True
            break
    if not done:
        if header is None:
            lines += ([""] if lines and lines[-1].strip() else []) + [f"[{CONFIG_SECTION}]"]
            header = len(lines) - 1
        lines.insert(header + 1, new_line)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def start_folder_for(app: App) -> Path:
    """
    Where a "where is it?" folder chooser should start: the folder that holds
    this checkout, since the other repository is often cloned next to it.
    """
    root = Path(__file__).resolve().parent.parent  # this repository (if it's a checkout)
    if (root / "pyproject.toml").is_file() and root.parent.is_dir():
        return root.parent
    return Path.home()


OFF = object()  # _from_config's "switched off" answer


def _from_config(app: App, settings: Mapping[str, str], path: Optional[Path]) -> Optional[object]:
    """
    What the config file says about `app`: a Companion, OFF (switched off),
    or None (no usable setting - look elsewhere).
    """
    value = settings.get(app.executable, "")
    if value.lower() in OFF_VALUES:
        return OFF
    found_by = f"config file {path}"
    try:
        if value:
            folder = _as_folder(value)
            if folder is None:
                return Companion(app, split_command(value), found_by)
            command = command_for_folder(folder, app)
            return Companion(app, command, found_by) if command else None
        # e.g. jackc-gui: look where jackc is (its folder, or next to its command).
        other = settings.get(app.config_fallback, "") if app.config_fallback else ""
        folder = _as_folder(other) or (_as_folder(str(Path(split_command(other)[0]).parent)) if other else None)
    except ValueError:  # e.g. an unclosed quote: ignore the setting rather than crash
        return None
    command = command_for_folder(folder, app) if folder else None
    return Companion(app, command, found_by) if command else None


def find(
    app: App,
    environ: Optional[Mapping[str, str]] = None,
    entry_points: Optional[Iterable] = None,
    which: Callable[[str], Optional[str]] = shutil.which,
) -> Optional[Companion]:
    """
    Look for `app` (see the module docstring for the order). The keyword
    arguments exist so tests can fake the environment (which also decides
    where the config file is), the installed packages and the PATH.
    """
    environ = os.environ if environ is None else environ

    # 1. An explicit setting always wins.
    override = environ.get(app.env_var, "").strip()
    if override:
        if override.lower() in OFF_VALUES:
            return None
        return Companion(app, split_command(override), f"${app.env_var}")

    # 2. The config file.
    path = config_path(environ)
    configured = _from_config(app, read_config(path), path)
    if configured is OFF:
        return None
    if isinstance(configured, Companion):
        return configured

    # 3. Installed in this same Python environment.
    try:
        points = list(entry_points) if entry_points is not None else _jack_tools_entry_points()
    except Exception:  # broken package metadata must never stop the GUI
        points = []
    for point in points:
        if point.name == app.key and _importable(point.value.partition(":")[0]):
            return Companion(app, entry_point_command(point.value, app.executable), "same Python environment")

    # 4. Anywhere on the PATH.
    on_path = which(app.executable)
    if on_path:
        return Companion(app, [on_path], "PATH")
    return None


def not_found_message(app: App, environ: Optional[Mapping[str, str]] = None) -> str:
    """
    What to tell the user when find(app) gave None: why, if they did
    configure it (e.g. the folder has no jackvm installed), and how to fix it.
    The first line is short enough for a GUI banner; the rest is detail
    (the GUIs print the whole message in the terminal too).
    """
    environ = os.environ if environ is None else environ
    if environ.get(app.env_var, "").strip().lower() in OFF_VALUES:
        return f"{app.title} is switched off (${app.env_var}={environ[app.env_var]})"
    path = config_path(environ)
    where = _short_path(path, environ) if path else "jack-tools/config.ini"
    value = read_config(path).get(app.executable, "")
    if value.lower() in OFF_VALUES:
        return f"{app.title} is switched off in {where}"
    if value and _as_folder(value) is not None:
        return (f"No {app.executable} command in {value} (set in {where})\n"
                f"Looked in that folder, its bin/, and .venv, venv, env, .direnv/* inside it. Install it there\n"
                f"(python3 -m venv .venv && .venv/bin/pip install -e .), or give the command's full path.")  # fmt: skip
    if path is not None and path.is_file() and _unreadable(path):
        return f"{where} couldn't be read\nIt must be an INI file with an [{CONFIG_SECTION}] section."
    return (f"{app.title} not found: set {app.executable} = <its folder> under [{CONFIG_SECTION}] in {where}\n"
            f"Or install it here: {app.install_hint}")  # fmt: skip


def _short_path(path: Path, environ: Mapping[str, str]) -> str:
    """~/.config/... rather than /Users/someone/.config/..."""
    home = environ.get("HOME", "").rstrip("/\\")
    text = str(path)
    return "~" + text[len(home):] if home and text.startswith(home + os.sep) else text


def _unreadable(path: Path) -> bool:
    try:
        configparser.ConfigParser(interpolation=None).read(path, encoding="utf-8")
        return False
    except (configparser.Error, OSError, UnicodeDecodeError):
        return True
