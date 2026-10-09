"""
vm.py - The Virtual Machine: the part that actually RUNS a program.
==================================================================

Big picture
-----------
A computer (real or virtual) does the same three things over and over:

    1. FETCH    - look at the instruction at address `pc`
    2. ADVANCE  - move `pc` on to the next instruction
    3. EXECUTE  - do what the instruction says (which may change `pc`
                  again, e.g. for `goto`)

`pc` stands for "program counter": the address of the next instruction.
One trip around this loop is called a "tick" (or "step"). See `tick()`.

The stack
---------
Almost every instruction works with the **stack**: a pile of numbers stored
in memory from address 256 upward. `memory[SP]` (address 0) holds the address
of the next FREE slot.

    push constant 7        push constant 8         add
    ----------------       ----------------        ----------------
    256: 7   <- SP=257     256: 7                  256: 15  <- SP=257
                           257: 8   <- SP=258

* PUSH  writes at memory[SP] then adds 1 to SP.
* POP   subtracts 1 from SP, then reads memory[SP].

Function calls (the trickiest part!)
------------------------------------
When function A calls function B, the VM must remember how to get back to A
and must give B its own fresh area for arguments and locals. It does this by
pushing a 5-slot "frame" onto the stack:

        ... A's stuff ...
        argument 0      <- new ARG points here (B's arguments, pushed by A)
        argument 1
        return address  <- where A should continue afterwards
        saved LCL       \
        saved ARG        |  A's registers, so we can restore them
        saved THIS       |
        saved THAT      /
        local 0         <- new LCL points here (B's local variables)
        local 1
        ...             <- SP (B's working stack starts here)

On `return`, the VM copies B's result into the slot where argument 0 was,
restores A's registers from the frame, moves SP to just above the result and
jumps to the return address. To A it looks like the arguments were "replaced"
by the result - exactly like `x = Math.multiply(a, b)` in Jack.

Read `_execute_call` and `_execute_return` with this picture next to you.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from . import jack_os
from .commands import (
    Arithmetic,
    Call,
    Function,
    Goto,
    IfGoto,
    Pop,
    Push,
    Return,
)
from .memory_map import (
    ARG,
    FALSE,
    LCL,
    MEMORY_SIZE,
    SP,
    STACK_START,
    STATIC_START,
    TEMP_START,
    THAT,
    THIS,
    TRUE,
    to_int16,
)
from .parser import Program, parse_program


# ---------------------------------------------------------------------------
# Errors the VM can raise while running
# ---------------------------------------------------------------------------
class VMError(Exception):
    """Something went wrong while running the program (a "runtime error")."""


class SysError(VMError):
    """
    The Jack program called `Sys.error(code)`, i.e. it reported its own error.

    The OS uses numbered error codes. The common ones are listed below so we
    can show a helpful message instead of just a number.
    """

    KNOWN_CODES = {
        1: "Sys.wait: duration must be positive",
        2: "Array.new: array size must be positive",
        3: "Math.divide: division by zero",
        4: "Math.sqrt: cannot compute the square root of a negative number",
        5: "Memory.alloc: allocated memory size must be positive",
        6: "Memory.alloc: heap overflow (out of memory)",
        7: "Screen.drawPixel: illegal pixel coordinates",
        8: "Screen.drawLine: illegal line coordinates",
        9: "Screen.drawRectangle: illegal rectangle coordinates",
        12: "Screen.drawCircle: illegal center coordinates",
        13: "Screen.drawCircle: illegal radius",
        14: "String.new: maximum length must be non-negative",
        15: "String.charAt: string index out of bounds",
        16: "String.setCharAt: string index out of bounds",
        17: "String.appendChar: string is full",
        18: "String.eraseLastChar: string is empty",
        19: "String.setInt: insufficient string capacity",
        20: "Output.moveCursor: illegal cursor location",
    }

    def __init__(self, code: int, called_from: str):
        self.code = code
        self.called_from = called_from
        meaning = self.KNOWN_CODES.get(code, "unknown error code")
        super().__init__(f"Sys.error({code}) called from {called_from}: {meaning}")


# ---------------------------------------------------------------------------
# Static variables: which memory addresses belong to which class?
# ---------------------------------------------------------------------------
def assign_static_addresses(commands: list) -> Dict[str, int]:
    """
    Give every class its own block of addresses for `static` variables.

    `push static 2` inside class Ball and `push static 2` inside class Bat must
    be DIFFERENT variables. So we look through the program, find the highest
    static index each class uses, and hand out consecutive blocks starting at
    address 16:

        Ball uses static 0..2  -> Ball gets addresses 16, 17, 18
        Bat  uses static 0..1  -> Bat  gets addresses 19, 20

    Returns a dict mapping class name -> first address of its block.
    Code that appears before any `function` line counts as class "STATIC".
    """
    highest_index: Dict[str, int] = {}  # dicts remember insertion order
    current_class = "STATIC"
    for command in commands:
        if isinstance(command, Function):
            current_class = command.class_name
        elif isinstance(command, (Push, Pop)) and command.segment == "static":
            previous = highest_index.get(current_class, 0)
            highest_index[current_class] = max(previous, command.index)

    bases: Dict[str, int] = {}
    next_free = STATIC_START
    for class_name, highest in highest_index.items():
        bases[class_name] = next_free
        next_free += highest + 1  # indices 0..highest need highest+1 slots
    return bases


# ---------------------------------------------------------------------------
# The virtual machine itself
# ---------------------------------------------------------------------------
class VirtualMachine:
    """
    Runs Jack VM programs.

    Typical use:

        vm = VirtualMachine()
        vm.load_source(open("games/pong.vm").read())
        while not vm.is_halted():
            vm.tick()          # run ONE instruction
        # or: vm.run(10_000)   # run up to 10,000 instructions
    """

    def __init__(self) -> None:
        # The RAM: a plain Python list of numbers, all starting at 0.
        self.memory: List[int] = [0] * MEMORY_SIZE

        # The program being run and its address book (see parser.py).
        self.commands: list = []
        self.addresses: Dict[str, int] = {}

        # class name -> first address of its static variables
        self.static_addresses: Dict[str, int] = {}

        # Address of the next instruction to run.
        self.pc: int = 0

        # Which functions are currently running, innermost last.
        # Each entry is (function name, base address for its static variables).
        # The VM only needs it for `static`; the debugger shows it too.
        self.call_stack: List[Tuple[str, int]] = []

        # How many instructions have run since the last (re)start.
        self.ticks: int = 0

        # A lookup table: "for this kind of command, call this method".
        # This is how `tick()` decides what to do (called "dispatching").
        self._handlers = {
            Push: self._execute_push,
            Pop: self._execute_pop,
            Arithmetic: self._execute_arithmetic,
            Goto: self._execute_goto,
            IfGoto: self._execute_if_goto,
            Function: self._execute_function,
            Call: self._execute_call,
            Return: self._execute_return,
        }

    # ------------------------------------------------------------------
    # Loading programs
    # ------------------------------------------------------------------
    def load_source(self, source: str) -> None:
        """
        Parse VM source text, add the Jack OS if needed, and get ready to run.

        Raises parser.ParseError if the source has mistakes.
        """
        program = parse_program(source)
        if jack_os.needs_os(program):
            program = jack_os.link_with_os(program)
        self.load_program(program)

    def load_program(self, program: Program) -> None:
        """Load an already-parsed Program and get ready to run it."""
        self.load(program.commands, program.addresses)

    def load(self, commands: list, addresses: Optional[Dict[str, int]] = None) -> None:
        """
        Load a list of command objects directly (handy for tests).

        Memory is wiped and SP is set to 256. If the program has a `Sys.init`
        function we start there (that's the official entry point); otherwise
        we start at the very first command.
        """
        self.commands = list(commands)
        self.addresses = dict(addresses or {})
        self.static_addresses = assign_static_addresses(self.commands)
        self.restart()

    def restart(self) -> None:
        """Wipe memory and start the current program again from the top."""
        self.memory = [0] * MEMORY_SIZE
        self.memory[SP] = STACK_START
        self.call_stack = []
        self.ticks = 0
        self.pc = self.addresses.get("Sys.init", 0)

    # ------------------------------------------------------------------
    # Looking at the machine (used by the screen, keyboard and debugger)
    # ------------------------------------------------------------------
    def peek(self, address: int) -> int:
        """Read one memory slot."""
        return self.memory[address]

    def poke(self, address: int, value: int) -> None:
        """Write one memory slot (the value is wrapped to 16 bits)."""
        self.memory[address] = to_int16(value)

    def is_halted(self) -> bool:
        """The program has finished when `pc` runs past the last command."""
        return self.pc >= len(self.commands)

    def current_instruction(self) -> str:
        """The next instruction as text, e.g. 'push local 0' (or 'HALT')."""
        if self.is_halted():
            return "HALT"
        return str(self.commands[self.pc])

    def current_function(self) -> str:
        """Name of the function currently running (or '' if none yet)."""
        return self.call_stack[-1][0] if self.call_stack else ""

    # ------------------------------------------------------------------
    # Running
    # ------------------------------------------------------------------
    def tick(self) -> None:
        """Run exactly ONE instruction: fetch, advance, execute."""
        if self.pc >= len(self.commands):
            return  # halted: nothing left to do

        command = self.commands[self.pc]  # 1. FETCH
        self.pc += 1  # 2. ADVANCE (jumps will overwrite this)
        self.ticks += 1
        handler = self._handlers[type(command)]
        try:
            handler(command)  # 3. EXECUTE
        except IndexError:
            raise self._out_of_memory_error(command) from None

    def run(self, max_ticks: int) -> int:
        """
        Run up to `max_ticks` instructions (stopping early if the program
        halts). Returns how many instructions actually ran.

        This is the same as calling tick() in a loop, but written out "inline"
        because it runs millions of times per second; avoiding the extra
        method call and the halted-check per tick makes it noticeably faster.
        """
        commands = self.commands
        handlers = self._handlers
        n_commands = len(commands)
        done = 0
        command = None
        try:
            while done < max_ticks and self.pc < n_commands:
                command = commands[self.pc]
                self.pc += 1
                handlers[type(command)](command)
                done += 1
        except IndexError:
            # A safety net: a "try" costs nothing until something goes wrong.
            raise self._out_of_memory_error(command) from None
        finally:
            self.ticks += done
        return done

    def _out_of_memory_error(self, command) -> VMError:
        """Python raises IndexError for memory[too_big]; explain it in VM terms."""
        return VMError(
            f"'{command}' tried to use a memory address outside 0..{MEMORY_SIZE - 1} "
            f"in function {self.current_function() or '?'}."
        )

    # ------------------------------------------------------------------
    # Stack helpers
    # ------------------------------------------------------------------
    def _stack_push(self, value: int) -> None:
        memory = self.memory
        address = memory[SP]
        if address >= MEMORY_SIZE:
            # The stack grows upward. On real Hack hardware it would first
            # trample the heap and the screen (you may see junk pixels!), and
            # finally run off the end of memory - which we report here.
            raise VMError(
                f"Stack overflow: the stack ran past the end of memory in function "
                f"{self.current_function() or '?'}. Is there a function that calls itself forever?"
            )
        memory[address] = value
        memory[SP] = address + 1

    def _stack_pop(self) -> int:
        memory = self.memory
        memory[SP] -= 1
        address = memory[SP]
        if address < 0:
            # Python lists accept negative indexes (memory[-1] is the LAST
            # item!), so without this check a bug would silently read the
            # keyboard register instead of crashing. Better to fail loudly.
            raise VMError("Stack underflow: popped more values than were pushed")
        return memory[address]

    def _check_address(self, address: int, description: str) -> int:
        """Make sure an address is inside memory (see the note in _stack_pop)."""
        if not 0 <= address < MEMORY_SIZE:
            raise VMError(
                f"{description} tried to use address {address}, which is outside memory "
                f"(0..{MEMORY_SIZE - 1}). In function {self.current_function() or '?'}."
            )
        return address

    def _segment_address(self, segment: str, index: int) -> int:
        """
        Work out WHICH memory address `<segment> <index>` refers to.

            local 2     -> memory[LCL] + 2       (LCL holds a base address)
            argument 0  -> memory[ARG] + 0
            this 1      -> memory[THIS] + 1
            that 5      -> memory[THAT] + 5
            pointer 0   -> address 3 (the THIS register itself)
            pointer 1   -> address 4 (the THAT register itself)
            temp 3      -> 5 + 3 = address 8
            static 2    -> (this class's static base) + 2
        """
        memory = self.memory
        if segment == "local":
            address = memory[LCL] + index
        elif segment == "argument":
            address = memory[ARG] + index
        elif segment == "this":
            address = memory[THIS] + index
        elif segment == "that":
            address = memory[THAT] + index
        elif segment == "pointer":
            address = THIS if index == 0 else THAT
        elif segment == "temp":
            address = TEMP_START + index
        elif segment == "static":
            address = self._static_base() + index
        else:
            raise VMError(f"Segment {segment!r} has no memory address")
        return self._check_address(address, f"'{segment} {index}'")

    def _static_base(self) -> int:
        """First static address of the class whose function is running now."""
        if self.call_stack:
            return self.call_stack[-1][1]
        return STATIC_START  # no function running yet (simple test programs)

    # ------------------------------------------------------------------
    # One method per kind of command
    # ------------------------------------------------------------------
    def _execute_push(self, command: Push) -> None:
        if command.segment == "constant":
            value = command.index  # the number itself, not a memory slot
        else:
            value = self.memory[self._segment_address(command.segment, command.index)]
        self._stack_push(value)

    def _execute_pop(self, command: Pop) -> None:
        # Work out the destination BEFORE popping: popping changes SP, and
        # "pop pointer 0" changes THIS - we want the address as it was.
        address = self._segment_address(command.segment, command.index)
        self.memory[address] = self._stack_pop()

    def _execute_arithmetic(self, command: Arithmetic) -> None:
        op = command.operator

        # --- Unary operators: take ONE value ------------------------------
        if op == "neg":
            self._stack_push(to_int16(-self._stack_pop()))  # -(-32768) wraps!
            return
        if op == "not":
            # `~` flips every bit. For 16-bit values ~x == -x - 1, which
            # always stays in range, so no wrapping is needed.
            self._stack_push(~self._stack_pop())
            return

        # --- Binary operators: take TWO values ----------------------------
        # The SECOND value pushed is on top, so pop it first:
        #   push 9, push 4, sub  ->  9 - 4  (not 4 - 9)
        y = self._stack_pop()
        x = self._stack_pop()
        if op == "add":
            result = to_int16(x + y)
        elif op == "sub":
            result = to_int16(x - y)
        elif op == "eq":
            result = TRUE if x == y else FALSE
        elif op == "gt":
            result = TRUE if x > y else FALSE
        elif op == "lt":
            result = TRUE if x < y else FALSE
        elif op == "and":
            result = x & y  # bit-by-bit AND (Python handles negatives correctly)
        elif op == "or":
            result = x | y  # bit-by-bit OR
        else:
            raise VMError(f"Unknown operator {op!r}")
        self._stack_push(result)

    def _jump_to(self, label: str) -> None:
        try:
            self.pc = self.addresses[label]
        except KeyError:
            raise VMError(f"Cannot jump to unknown label or function {label!r}") from None

    def _execute_goto(self, command: Goto) -> None:
        self._jump_to(command.label)

    def _execute_if_goto(self, command: IfGoto) -> None:
        # Anything that isn't false (0) counts as true.
        if self._stack_pop() != FALSE:
            self._jump_to(command.label)

    def _execute_function(self, command: Function) -> None:
        # We have just entered a function. Remember it (for `static`), then
        # make room for its local variables, all starting at 0.
        static_base = self.static_addresses.get(command.class_name, STATIC_START)
        self.call_stack.append((command.name, static_base))
        for _ in range(command.n_locals):
            self._stack_push(0)

    def _execute_call(self, command: Call) -> None:
        # Two OS functions are handled specially, like the original VM does:
        if command.name == "Sys.halt":
            # The OS's own Sys.halt is an endless loop. We simply stop.
            self.pc = len(self.commands)
            return
        if command.name == "Sys.error":
            # Its single argument (the error code) is on top of the stack.
            code = self.memory[self.memory[SP] - 1]
            raise SysError(code, self.current_function() or "?")

        memory = self.memory
        # Push the 5-slot frame (see the diagram at the top of this file).
        # self.pc already points at the instruction AFTER this call - that's
        # exactly where the caller should continue, i.e. the return address.
        self._stack_push(self.pc)
        self._stack_push(memory[LCL])
        self._stack_push(memory[ARG])
        self._stack_push(memory[THIS])
        self._stack_push(memory[THAT])
        # The arguments were pushed by the caller just before the frame.
        memory[ARG] = memory[SP] - command.n_args - 5
        # The new function's locals will start right after the frame.
        memory[LCL] = memory[SP]
        self._jump_to(command.name)

    def _execute_return(self, command: Return) -> None:
        if self.call_stack:
            self.call_stack.pop()

        memory = self.memory
        frame = memory[LCL]  # the frame sits just below the locals
        if frame < 5:
            raise VMError("'return' executed, but there is no function call to return from")
        return_address = memory[frame - 5]

        # Put the result where the caller's first argument was...
        memory[self._check_address(memory[ARG], "return")] = self._stack_pop()
        # ...and make the stack end right after it.
        memory[SP] = memory[ARG] + 1

        # Restore the caller's registers (saved in the frame by `call`).
        memory[THAT] = memory[frame - 1]
        memory[THIS] = memory[frame - 2]
        memory[ARG] = memory[frame - 3]
        memory[LCL] = memory[frame - 4]

        self.pc = return_address
