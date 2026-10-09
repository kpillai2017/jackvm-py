"""
commands.py - The instructions the Jack VM understands.
========================================================

A `.vm` file is plain text, one instruction per line, for example:

    push constant 7      // put the number 7 on top of the stack
    push constant 8
    add                  // pop 7 and 8, push 15

The parser (see parser.py) reads that text and turns each line into one of the
small Python objects defined below. Working with objects is much easier (and
faster) than re-reading text every time the VM runs an instruction.

There are only NINE kinds of command in the whole VM language:

    Command        Example                    What it does
    -----------    -------------------------  --------------------------------
    Push           push local 2               copy a value ONTO the stack
    Pop            pop that 0                 move the top value OFF the stack
    Arithmetic     add / sub / neg / eq /     maths & logic on the top of
                   gt / lt / and / or / not   the stack
    Label          label LOOP                 marks a place you can jump to
    Goto           goto LOOP                  always jump
    IfGoto         if-goto LOOP               pop a value; jump if it's true
    Function       function Main.main 2       start of a function with 2 locals
    Call           call Math.multiply 2       call a function with 2 arguments
    Return         return                     go back to the caller

We use Python "dataclasses": a shortcut for writing simple classes whose job
is just to hold a few named values. `frozen=True` means the object can't be
changed after it is made - instructions never change while a program runs.
"""

from __future__ import annotations

from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Memory segments - the different "areas" push/pop can talk to.
# We use plain strings (the same words that appear in the .vm file) because
# they are easy to read and print.
# ---------------------------------------------------------------------------
SEGMENTS = (
    "constant",  # not really memory: "push constant 5" just pushes 5
    "local",  # the current function's local variables
    "argument",  # the current function's arguments
    "this",  # fields of the current object
    "that",  # elements of the current array
    "pointer",  # pointer 0 = the THIS register, pointer 1 = the THAT register
    "temp",  # eight scratch slots at addresses 5..12
    "static",  # class-level variables
)

# Arithmetic / logic operators.
# "Binary" ones take TWO values from the stack, "unary" ones take ONE.
BINARY_OPERATORS = ("add", "sub", "eq", "gt", "lt", "and", "or")
UNARY_OPERATORS = ("neg", "not")
OPERATORS = BINARY_OPERATORS + UNARY_OPERATORS


@dataclass(frozen=True)
class Push:
    """`push <segment> <index>` - copy a value onto the top of the stack."""

    segment: str
    index: int

    def __str__(self) -> str:  # how the debugger prints it
        return f"push {self.segment} {self.index}"


@dataclass(frozen=True)
class Pop:
    """`pop <segment> <index>` - remove the top value and store it somewhere."""

    segment: str
    index: int

    def __str__(self) -> str:
        return f"pop {self.segment} {self.index}"


@dataclass(frozen=True)
class Arithmetic:
    """`add`, `sub`, `neg`, `eq`, `gt`, `lt`, `and`, `or` or `not`."""

    operator: str

    def __str__(self) -> str:
        return self.operator


@dataclass(frozen=True)
class Label:
    """
    `label <name>` - a bookmark in the program.

    Labels never *run*: the parser just remembers which instruction number
    they point at (see parser.py) and leaves them out of the final program.
    The name is stored in its "full" form, e.g. "Main.main$LOOP", so labels
    with the same short name in different functions don't clash.
    """

    name: str

    def __str__(self) -> str:
        return f"label {self.name}"


@dataclass(frozen=True)
class Goto:
    """`goto <label>` - jump to a label, always."""

    label: str

    def __str__(self) -> str:
        return f"goto {self.label}"


@dataclass(frozen=True)
class IfGoto:
    """`if-goto <label>` - pop the top value; jump only if it is NOT false (0)."""

    label: str

    def __str__(self) -> str:
        return f"if-goto {self.label}"


@dataclass(frozen=True)
class Function:
    """`function <Class.name> <n_locals>` - the first instruction of a function."""

    name: str
    n_locals: int

    @property
    def class_name(self) -> str:
        """'Main.main' -> 'Main'. Static variables belong to a class."""
        return self.name.split(".")[0]

    def __str__(self) -> str:
        return f"function {self.name} {self.n_locals}"


@dataclass(frozen=True)
class Call:
    """`call <Class.name> <n_args>` - call a function that has n_args arguments."""

    name: str
    n_args: int

    def __str__(self) -> str:
        return f"call {self.name} {self.n_args}"


@dataclass(frozen=True)
class Return:
    """`return` - hand the top-of-stack value back to whoever called us."""

    def __str__(self) -> str:
        return "return"
