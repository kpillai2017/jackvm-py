"""
jack_sources.py - Run Jack source code (.jack) by compiling it first.
====================================================================

The VM runs .vm files. But if the Jack compiler
(https://github.com/kpillai2017/jack-compiler) is installed too, you can
hand jackvm the Jack SOURCE instead and it compiles it for you:

    python -m jackvm projects/Square/            # a folder of .jack files
    python -m jackvm projects/Square/Main.jack   # ...or any file in it

and the file picker offers "[compile+play]" for folders of .jack files.
One folder is one Jack program (as in nand2tetris), so a single .jack file
means "its whole folder". When a folder holds both .jack and .vm files,
the .jack sources win - they're what you've been editing.

The compiler is a separate app in its own repository: it's found by
integrations.py and run as a command (`jackc <folder> -o <temp folder>`),
never imported. Its .vm output goes into a temporary folder that's removed
when jackvm exits, so your source folder is left exactly as it was.

If compiling fails, the compiler's error messages are shown, and
Ctrl+J opens the folder in the compiler's own window (jackc-gui), which
marks each mistake in the code.
"""

from __future__ import annotations

import atexit
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

from .integrations import JACKC, JACKC_GUI, Companion, find, not_found_message
from .program_files import describe, resolve_paths, vm_files_in

COMPILE_TIMEOUT_SECONDS = 300
# jackc reports errors compiler-style:  /path/Main.jack:3:7: error: 'x' is not declared
ERROR_LINE = re.compile(r"(?P<file>[^/\\\s]+\.jack):(?P<line>\d+):(?P<column>\d+): error: (?P<message>.*)")

# temporary output folder -> the .jack folder it was compiled from
_compiled_from: Dict[Path, Path] = {}


def jack_files_in(folder: Path) -> List[Path]:
    """All .jack files directly inside `folder` (or [] if it can't be read)."""
    try:
        return sorted((p for p in Path(folder).glob("*.jack") if p.is_file()), key=lambda p: p.name.lower())
    except OSError:
        return []


def jack_folder(path: Path) -> Optional[Path]:
    """The folder to compile if `path` is Jack source: a .jack file, or a folder holding some."""
    if path.is_file() and path.suffix.lower() == ".jack":
        return path.parent
    if path.is_dir() and jack_files_in(path):
        return path
    return None


class JackCompileError(Exception):
    """The Jack compiler found mistakes (or couldn't be run)."""

    def __init__(self, folder: Path, errors: List[str], output: str = "") -> None:
        self.folder = folder
        self.errors = errors  # short one-line messages, e.g. "Main.jack:3:7: error: ..."
        self.output = output  # everything the compiler printed
        more = f" (+{len(errors) - 1} more)" if len(errors) > 1 else ""
        super().__init__(f"{errors[0]}{more}" if errors else f"Can't compile {folder}")


def compile_folder(folder: Path, compiler: Companion) -> List[Path]:
    """Compile every .jack file in `folder` into a temporary folder; return the .vm files."""
    folder = Path(folder).resolve()
    output_folder = Path(tempfile.mkdtemp(prefix="jackvm-compiled-"))
    try:
        done = compiler.run([str(folder), "-o", str(output_folder)], timeout=COMPILE_TIMEOUT_SECONDS)
    except (OSError, subprocess.SubprocessError) as problem:
        shutil.rmtree(output_folder, ignore_errors=True)
        raise JackCompileError(folder, [f"Couldn't run the Jack compiler: {problem}"]) from None

    printed = (done.stdout or "") + (done.stderr or "")
    files = vm_files_in(output_folder)
    if done.returncode != 0 or not files:
        shutil.rmtree(output_folder, ignore_errors=True)
        errors = [
            f"{m['file']}:{m['line']}:{m['column']}: error: {m['message']}"
            for m in (ERROR_LINE.search(line) for line in printed.splitlines()) if m
        ]  # fmt: skip
        if not errors:
            last = [line.strip() for line in printed.splitlines() if line.strip()]
            errors = [last[-1] if last else f"The Jack compiler failed (exit {done.returncode})"]
        raise JackCompileError(folder, errors, printed)
    _compiled_from[output_folder.resolve()] = folder
    return files


def source_folder_for(files: Sequence[Path]) -> Optional[Path]:
    """Where the Jack sources of these .vm files are, if we know (or can see) them."""
    if not files:
        return None
    folder = Path(files[0]).parent.resolve()
    if folder in _compiled_from:
        return _compiled_from[folder]
    return folder if jack_files_in(folder) else None


def describe_program(files: Sequence[Path]) -> str:
    """Like program_files.describe(), but compiled programs are named after their source folder."""
    if files and Path(files[0]).parent.resolve() in _compiled_from:
        source = _compiled_from[Path(files[0]).parent.resolve()]
        return f"{source.name}/ (compiled from .jack, {len(files)} file{'s' if len(files) != 1 else ''})"
    return describe(files)


@atexit.register
def _remove_compiled_folders() -> None:
    for folder in _compiled_from:
        shutil.rmtree(folder, ignore_errors=True)
    _compiled_from.clear()


class JackTools:
    """
    The Jack compiler, if installed: `compiler` (jackc) compiles, `gui`
    (jackc-gui) opens sources in the compiler's window. Either may be None.
    """

    def __init__(
        self,
        compiler_finder: Callable[[], Optional[Companion]] = lambda: find(JACKC),
        gui_finder: Callable[[], Optional[Companion]] = lambda: find(JACKC_GUI),
    ) -> None:
        self.compiler = compiler_finder()
        self.gui = gui_finder()

    @property
    def can_compile(self) -> bool:
        return self.compiler is not None

    def prepare(self, names: Sequence[str]) -> List[Path]:
        """
        Like program_files.resolve_paths(), but Jack source is compiled first.
        Raises FileNotFoundError, or JackCompileError if the code has mistakes.
        """
        files: List[Path] = []
        for name in names:
            path = Path(name).expanduser()
            folder = jack_folder(path) if path.exists() else None
            if folder is None or (self.compiler is None and path.is_dir() and vm_files_in(path)):
                files.extend(resolve_paths([name]))  # .vm files (or no compiler: the old .vm files)
            elif self.compiler is None:
                raise FileNotFoundError(f"{name} is Jack source code (.jack), so it needs the Jack compiler.\n"
                                        f"{not_found_message(JACKC)}")  # fmt: skip
            else:
                print(f"Compiling {folder.name}/ with the Jack compiler...")
                files.extend(compile_folder(folder, self.compiler))
        return files

    def open_in_compiler(self, folder: Optional[Path]) -> str:
        """Ctrl+J: open `folder` in jackc-gui. Returns a message for the user."""
        if folder is None:
            return "No .jack sources next to this program"
        if self.gui is None:
            return not_found_message(JACKC_GUI)
        try:
            self.gui.launch([str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as problem:
            return f"Couldn't start the Jack compiler: {problem}"
        return f"Opened {folder.name}/ in the Jack compiler"
