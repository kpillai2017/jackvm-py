"""
parser.py - Turn the TEXT of a .vm file into a list of command OBJECTS.
=====================================================================

The parser reads a program line by line and produces two things:

1. `commands` - a Python list of Push / Pop / Add / ... objects
   (see commands.py). The position of a command in this list is its
   **address**: the first command is at address 0, the next at 1, etc.

2. `addresses` - a dictionary that maps every *function name* and every
   *label name* to the address it points at, e.g.

        {"Main.main": 0, "Main.main$LOOP": 4, "Math.multiply": 57, ...}

   The VM uses this "address book" to know where to jump for `goto`,
   `if-goto` and `call`.

A worked example
----------------
Source text (line numbers on the left):

    1  function Main.main 0
    2  label LOOP            // a label is NOT a real instruction...
    3  push constant 1
    4  goto LOOP

Result:

    commands  = [Function("Main.main", 0),     # address 0
                 Push("constant", 1),          # address 1
                 Goto("Main.main$LOOP")]       # address 2
    addresses = {"Main.main": 0,
                 "Main.main$LOOP": 1}          # ...it just names address 1

Notice two things:
  * `label LOOP` did not become a command. It only adds an entry to the
    address book pointing at the NEXT real command.
  * The label's name got the function name glued in front of it
    ("Main.main$LOOP"). That's called *scoping*: two different functions can
    both have a label called LOOP without getting mixed up.

Errors
------
If any line is wrong, we keep going and collect ALL the problems, then raise
one `ParseError` listing them. That's friendlier than stopping at the first
mistake.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .commands import (
    OPERATORS,
    SEGMENTS,
    Arithmetic,
    Call,
    Function,
    Goto,
    IfGoto,
    Label,
    Pop,
    Push,
    Return,
)
from .memory_map import to_int16


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass
class Program:
    """The result of parsing: the runnable commands plus the address book."""

    commands: list = field(default_factory=list)
    addresses: Dict[str, int] = field(default_factory=dict)


@dataclass
class SyntaxProblem:
    """One problem found on one line of the source file."""

    line_number: int  # 1 = first line of the file
    message: str
    text: str = ""  # the offending line, to make messages helpful

    def __str__(self) -> str:
        where = f"line {self.line_number}"
        return f"{where}: {self.message}" + (f"   -->  {self.text}" if self.text else "")


class ParseError(Exception):
    """Raised when the source contains one or more mistakes."""

    def __init__(self, problems: List[SyntaxProblem]):
        self.problems = problems
        summary = "\n".join(f"  {p}" for p in problems)
        super().__init__(f"Could not parse the VM program ({len(problems)} problem(s)):\n{summary}")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def strip_comment(line: str) -> str:
    """Remove a `// comment` (if any) and surrounding spaces/tabs."""
    comment_start = line.find("//")
    if comment_start != -1:
        line = line[:comment_start]
    return line.strip()


def parse_non_negative_int(text: Optional[str], what: str) -> int:
    """
    Convert text such as "42" into the number 42.

    Raises ValueError (with a friendly message) if the text is missing,
    is not a whole number, or is negative.
    """
    if text is None:
        raise ValueError(f"Expected {what}, but found nothing")
    try:
        number = int(text)
    except ValueError:
        raise ValueError(f"Expected {what}, but found {text!r}") from None
    if number < 0:
        raise ValueError(f"Expected {what} (zero or more), but found {number}")
    return number


def scoped_label(current_function: str, label: str) -> str:
    """'LOOP' inside 'Main.main' becomes 'Main.main$LOOP' (see module docs)."""
    if current_function:
        return f"{current_function}${label}"
    return label  # labels written before any `function` line stay as-is


# ---------------------------------------------------------------------------
# Parsing a single line
# ---------------------------------------------------------------------------
def parse_line(words: List[str], current_function: str):
    """
    Turn the words of ONE line (e.g. ["push", "local", "2"]) into a command.

    `current_function` is the name of the function we're inside of; it is
    needed to give labels their full, scoped names.

    Raises ValueError with an explanation if the line is not valid.
    """
    keyword = words[0]
    args = words[1:]
    arg1 = args[0] if len(args) > 0 else None
    arg2 = args[1] if len(args) > 1 else None

    def expect_arg_count(count: int) -> None:
        if len(args) != count:
            raise ValueError(f"'{keyword}' expects {count} argument(s) but got {len(args)}")

    # push / pop ------------------------------------------------------------
    if keyword in ("push", "pop"):
        expect_arg_count(2)
        segment = arg1
        if segment not in SEGMENTS:
            raise ValueError(f"Unknown memory segment {segment!r} (expected one of: {', '.join(SEGMENTS)})")
        index = parse_non_negative_int(arg2, "a non-negative integer index")
        if keyword == "pop" and segment == "constant":
            raise ValueError("You cannot 'pop' into the constant segment")
        if segment == "pointer" and index not in (0, 1):
            raise ValueError("The pointer segment only has entries 0 (THIS) and 1 (THAT)")
        if segment == "temp" and index > 7:
            raise ValueError("The temp segment only has entries 0 to 7")
        if keyword == "push":
            # Constants are stored as 16-bit numbers, so e.g. 40000 wraps around.
            return Push(segment, to_int16(index) if segment == "constant" else index)
        return Pop(segment, index)

    # add, sub, neg, eq, gt, lt, and, or, not ---------------------------------
    if keyword in OPERATORS:
        expect_arg_count(0)
        return Arithmetic(keyword)

    # label / goto / if-goto --------------------------------------------------
    if keyword in ("label", "goto", "if-goto"):
        expect_arg_count(1)
        name = scoped_label(current_function, arg1)
        if keyword == "label":
            return Label(name)
        if keyword == "goto":
            return Goto(name)
        return IfGoto(name)

    # function / call ---------------------------------------------------------
    if keyword == "function":
        expect_arg_count(2)
        return Function(arg1, parse_non_negative_int(arg2, "the number of local variables"))

    if keyword == "call":
        expect_arg_count(2)
        return Call(arg1, parse_non_negative_int(arg2, "the number of arguments"))

    # return ----------------------------------------------------------------
    if keyword == "return":
        expect_arg_count(0)
        return Return()

    raise ValueError(f"Unrecognised instruction {keyword!r}")


# ---------------------------------------------------------------------------
# Parsing a whole program
# ---------------------------------------------------------------------------
def parse_program(source: str) -> Program:
    """
    Parse the full text of a VM program.

    Returns a `Program`. Raises `ParseError` if anything is wrong.
    """
    program = Program()
    problems: List[SyntaxProblem] = []
    current_function = ""  # which function's body are we in?

    # enumerate(..., start=1) gives us human-friendly line numbers (1, 2, 3...)
    for line_number, raw_line in enumerate(source.splitlines(), start=1):
        line = strip_comment(raw_line)
        if not line:
            continue  # skip blank lines and comment-only lines

        words = line.split()  # split on any run of spaces or tabs
        try:
            command = parse_line(words, current_function)
        except ValueError as error:
            problems.append(SyntaxProblem(line_number, str(error), raw_line.strip()))
            continue

        # The address of the next command is simply "how many we have so far".
        next_address = len(program.commands)

        if isinstance(command, (Function, Label)):
            name = command.name
            if name in program.addresses:
                problems.append(SyntaxProblem(line_number, f"{name!r} is defined more than once", raw_line.strip()))
                continue
            program.addresses[name] = next_address

        if isinstance(command, Function):
            current_function = command.name

        # Labels are bookmarks only - they do not become runnable commands.
        if not isinstance(command, Label):
            program.commands.append(command)

    if problems:
        raise ParseError(problems)
    return program
