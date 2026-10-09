"""
jack_os.py - The Jack "Operating System" (a library of helper classes).
======================================================================

Jack programs rely on a small standard library, which nand2tetris calls the
"Jack OS". It provides eight classes:

    Math       multiply, divide, sqrt, min, max, abs
    Memory     peek, poke, alloc (reserve heap memory), deAlloc
    Screen     clearScreen, drawPixel, drawLine, drawRectangle, drawCircle
    Output     printChar, printString, printInt, println (text on screen)
    Keyboard   keyPressed, readChar, readLine, readInt
    String     new, length, charAt, appendChar, intValue, ...
    Array      new, dispose
    Sys        init (program start-up), halt, error, wait

Where does the OS come from?
----------------------------
The OS is itself written in Jack and compiled to VM code. Exactly like the
original Rust project, we ship that compiled VM code as a text file
(`jackvm/os/JackOS.vm`) and simply **glue it onto the end** of your program
before running. So the OS is executed by the very same VM as your game -
there is no "magic" hidden in Python.

How does the program start?
---------------------------
Every complete program starts by running `Sys.init`. The OS version of
`Sys.init` sets up the other OS classes and then calls YOUR `Main.main`.

When do we add the OS?
----------------------
* If the program has `Main.main` but NO `Sys.init`, it needs the OS -> we
  add it. (This is the normal case: pong.vm, hello-world.vm, ...)
* If the program already contains `Sys.init`, it has brought its own OS (or
  is a hand-written test program) -> we leave it alone.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from .parser import Program, parse_program

# The OS source lives next to this file, in the "os" folder.
OS_SOURCE_PATH = Path(__file__).parent / "os" / "JackOS.vm"


def os_source() -> str:
    """Return the OS's VM source code as a string."""
    return OS_SOURCE_PATH.read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def os_program() -> Program:
    """
    Parse the OS once and remember the result.

    `@lru_cache` is a Python decorator that stores the return value, so the
    3,900-line OS is only parsed the first time we need it.
    """
    return parse_program(os_source())


def needs_os(program: Program) -> bool:
    """True if the program has a Main.main but doesn't bring its own Sys.init."""
    return "Main.main" in program.addresses and "Sys.init" not in program.addresses


def link_with_os(program: Program) -> Program:
    """
    Return a NEW Program made of `program` followed by the Jack OS.

    "Linking" means joining separately-parsed pieces of code into one program
    and fixing up their addresses so they still point at the right place.

    Example: if your program has 1000 commands, the OS's first command (which
    was address 0 in the OS on its own) becomes address 1000 in the combined
    program. So every OS address is shifted by `len(program.commands)`.

    If you wrote your OWN version of an OS function (say `Math.multiply`),
    yours wins: we don't overwrite names that already exist.
    """
    os = os_program()
    offset = len(program.commands)

    combined = Program(
        commands=program.commands + os.commands,
        addresses=dict(program.addresses),  # copy, don't modify the original
    )
    for name, address in os.addresses.items():
        if name not in combined.addresses:
            combined.addresses[name] = address + offset
    return combined
