"""
program_files.py - Finding and reading .vm files.
================================================

A Jack program can arrive in three shapes:

  * ONE .vm file             e.g. games/hello-world/Main.vm
  * a FOLDER of .vm files     e.g. games/pong/  (Main.vm, Ball.vm, Bat.vm, ...)
  * a bundled game NAME       e.g. "pong"  ->  games/pong/

The nand2tetris compiler writes one .vm file per Jack class, so a folder is
the most common shape. This module turns any of them into a list of files,
and those files into one big program text for the parser.

Both the command line (main.py) and the GUI file picker (via player.py) use
these helpers, which is why they live in their own module.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Sequence

# The games that come with this project live in ../games next to the package.
GAMES_FOLDER = Path(__file__).resolve().parent.parent / "games"


def vm_files_in(folder: Path) -> List[Path]:
    """All .vm files directly inside `folder`, sorted by name (case-insensitive)."""
    return sorted((p for p in folder.glob("*.vm") if p.is_file()), key=lambda p: p.name.lower())


def list_games() -> List[str]:
    """Names of the bundled games: folders (or single files) in games/."""
    names = [p.name for p in GAMES_FOLDER.iterdir() if p.is_dir() and vm_files_in(p)]
    names += [p.stem for p in GAMES_FOLDER.glob("*.vm")]
    return sorted(names)


def resolve_paths(names: Sequence[str]) -> List[Path]:
    """
    Turn what the user typed into a list of .vm files.

    * an existing file          -> that file
    * an existing folder        -> every .vm file inside it (sorted by name)
    * a bundled game name       -> games/<name>/*.vm   (or games/<name>.vm)
    """
    files: List[Path] = []
    for name in names:
        path = Path(name).expanduser()
        if not path.exists():
            # Not a real path - is it the name of a bundled game?
            if (GAMES_FOLDER / name).is_dir():
                path = GAMES_FOLDER / name
            elif (GAMES_FOLDER / f"{name}.vm").is_file():
                path = GAMES_FOLDER / f"{name}.vm"
            else:
                raise FileNotFoundError(
                    f"Can't find {name!r} (not a file, a folder, or a bundled game: {', '.join(list_games())})"
                )
        if path.is_dir():
            found = vm_files_in(path)
            if not found:
                raise FileNotFoundError(f"No .vm files found in folder {path}")
            files.extend(found)
        else:
            files.append(path)
    return files


def read_program(files: Sequence[Path]) -> str:
    """
    Join several .vm files into one program text.

    Running separate class files together is as simple as sticking their
    texts end to end: every file starts with a `function` line, so labels
    stay correctly scoped (see parser.py).
    """
    return "\n".join(f.read_text(encoding="utf-8") for f in files)


def describe(files: Sequence[Path]) -> str:
    """A short human-readable name, e.g. 'pong/ (4 files)' or 'Main.vm'."""
    if len(files) == 1:
        return files[0].name
    folders = {f.parent for f in files}
    if len(folders) == 1:
        return f"{files[0].parent.name}/ ({len(files)} files)"
    return ", ".join(f.name for f in files)
