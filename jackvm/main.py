"""
main.py - The command line interface ("CLI").
============================================

This is the file that runs when you type:

    python -m jackvm                          # opens a window to CHOOSE a program
    python -m jackvm pong                     # a bundled game, by name
    python -m jackvm games/pong               # a folder of .vm files
    python -m jackvm games/hello-world/Main.vm   # a single .vm file
    python -m jackvm Main.vm Ball.vm Bat.vm   # several files at once
    python -m jackvm pong --headless --ticks 3000000   # no window

Run `python -m jackvm --help` to see every option.

It uses `argparse`, Python's built-in library for reading command line
options, then either:
  * opens the GUI file picker (no program given, or --gui),
  * opens the pygame Player, or
  * with --headless, runs the VM in the terminal and prints the screen as text.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .memory_map import REGISTER_NAMES
from .parser import ParseError
from .program_files import GAMES_FOLDER, describe, list_games, read_program, resolve_paths  # noqa: F401
from .screen import DEFAULT_OFF_COLOUR, DEFAULT_ON_COLOUR, Colour, to_ascii
from .vm import VirtualMachine, VMError


# ---------------------------------------------------------------------------
# Small parsing helpers for options
# ---------------------------------------------------------------------------
def parse_colour(text: str) -> Colour:
    """'#ff8800' or 'ff8800' -> (255, 136, 0)"""
    text = text.lstrip("#")
    if len(text) != 6:
        raise argparse.ArgumentTypeError(f"colour must look like #rrggbb, not {text!r}")
    try:
        return tuple(int(text[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        raise argparse.ArgumentTypeError(f"colour must look like #rrggbb, not {text!r}") from None


def parse_watch(text: str) -> List[int]:
    """'8000' -> [8000];  '8000:8003' -> [8000, 8001, 8002, 8003]"""
    try:
        if ":" in text:
            start, end = (int(part) for part in text.split(":"))
            return list(range(start, end + 1))
        return [int(text)]
    except ValueError:
        raise argparse.ArgumentTypeError(f"--watch expects ADDRESS or START:END, not {text!r}") from None


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m jackvm",
        description="Run Jack VM (.vm) programs from the nand2tetris course.",
        epilog=f"Bundled games: {', '.join(list_games())}",
    )
    parser.add_argument(
        "program", nargs="*",
        help="a .vm file, a folder of .vm files, or a bundled game name. Leave it out to choose in a window.",
    )  # fmt: skip
    parser.add_argument(
        "--gui", action="store_true",
        help="choose the program in a window (starts in the given folder, or in games/)",
    )  # fmt: skip
    parser.add_argument("--scale", type=int, default=2, help="window zoom factor (default: 2)")
    parser.add_argument("--no-debugger", action="store_true", help="hide the memory debugger panel")
    parser.add_argument("--paused", action="store_true", help="start paused (press Ctrl+P to run, Ctrl+N to step)")
    parser.add_argument(
        "--ticks-per-frame", type=int, default=None, metavar="N",
        help="run exactly N instructions per frame (default: as many as fit in ~12 ms)",
    )  # fmt: skip
    parser.add_argument("--on-colour", type=parse_colour, default=DEFAULT_ON_COLOUR, metavar="#RRGGBB", help="pixel colour (default: black)")
    parser.add_argument("--off-colour", type=parse_colour, default=DEFAULT_OFF_COLOUR, metavar="#RRGGBB", help="background colour (default: white)")
    parser.add_argument(
        "--watch", type=parse_watch, action="append", default=[], metavar="ADDR[:END]",
        help="show these memory addresses in the debugger (can be repeated)",
    )  # fmt: skip
    parser.add_argument("--headless", action="store_true", help="no window: run in the terminal and print the screen as text")
    parser.add_argument("--ticks", type=int, default=5_000_000, help="with --headless: how many instructions to run (default: 5,000,000)")
    return parser


# ---------------------------------------------------------------------------
# Headless mode
# ---------------------------------------------------------------------------
def run_headless(vm: VirtualMachine, ticks: int, watch: Sequence[int]) -> int:
    """Run without a window, then print a summary. Returns an exit code."""
    exit_code = 0
    try:
        vm.run(ticks)
    except VMError as problem:
        print(f"Runtime error: {problem}")
        exit_code = 1
    print(to_ascii(vm.memory))
    status = "halted" if vm.is_halted() else "still running"
    print(f"\nRan {vm.ticks:,} instructions; program is {status}. Next: {vm.current_instruction()}")
    print("  ".join(f"{REGISTER_NAMES[a]}={vm.peek(a)}" for a in range(5)))
    for address in watch:
        print(f"  memory[{address}] = {vm.peek(address)}")
    return exit_code


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    watch = [address for group in args.watch for address in group]
    use_gui_picker = args.gui or not args.program

    if use_gui_picker and args.headless:
        parser.error("--headless needs a program (a .vm file, a folder or a game name)")

    vm = VirtualMachine()
    files: List[Path] = []

    if use_gui_picker:
        # Imported here so --headless works even where pygame isn't installed.
        from .player import open_picker_window

        start = Path(args.program[0]).expanduser() if args.program else GAMES_FOLDER
        files = open_picker_window(vm, start if start.is_dir() else GAMES_FOLDER)
        if not files:
            return 0  # the user cancelled or closed the window
    else:
        try:
            files = resolve_paths(args.program)
            vm.load_source(read_program(files))
        except (FileNotFoundError, ParseError) as problem:
            print(problem, file=sys.stderr)
            return 1

    print(f"Loaded {describe(files)}: {len(vm.commands):,} instructions.")

    if args.headless:
        return run_headless(vm, args.ticks, watch)

    from .player import Player

    Player(
        vm,
        files=files,
        scale=args.scale,
        show_debugger=not args.no_debugger,
        ticks_per_frame=args.ticks_per_frame,
        start_paused=args.paused,
        on_colour=args.on_colour,
        off_colour=args.off_colour,
        watch=watch,
    ).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
