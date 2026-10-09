"""
memory_map.py - Where everything lives inside the Hack computer's memory.
==========================================================================

The Jack VM runs on top of the "Hack" computer from the nand2tetris course.
Hack has ONE big block of memory (RAM). Every value in it is a 16-bit
signed integer (a number between -32768 and 32767).

There are no separate "variables", "screen buffer" or "keyboard port" -
everything is just a numbered slot (an *address*) in this one big list.
By agreement (a "convention"), certain address ranges have special jobs:

    Address(es)     Name          What it is used for
    -----------     ----------    --------------------------------------------
    0               SP            "Stack Pointer": address of the next FREE
                                  slot on the stack.
    1               LCL           Base address of the current function's
                                  LOCAL variables.
    2               ARG           Base address of the current function's
                                  ARGUMENTS.
    3               THIS          Base address of the current object ("this").
    4               THAT          Base address of the current array ("that").
    5  .. 12        TEMP 0..7     Eight scratch slots ("temp" segment).
    13 .. 15        R13..R15      General purpose (unused by this VM).
    16 .. 255       STATIC        "static" variables (class-level variables).
    256 .. 2047     STACK         The stack - where all the calculating happens.
    2048 .. 16383   HEAP          Memory handed out by Memory.alloc (objects,
                                  arrays, strings).
    16384 .. 24575  SCREEN        The display. Each bit is ONE pixel.
    24576           KEYBOARD      The code of the key currently held down
                                  (0 if no key is pressed).

Because the screen and keyboard are "just memory", a program draws a pixel by
writing to an address in the SCREEN range, and checks the keyboard by reading
address 24576. This trick is called **memory-mapped I/O**.

This module contains only constants plus one tiny helper (`to_int16`), so it
is a good first file to read.
"""

# ---------------------------------------------------------------------------
# The "virtual registers" - the first five memory slots.
# They hold *addresses* (pointers) that tell the VM where things are.
# ---------------------------------------------------------------------------
SP = 0  # Stack Pointer: next free slot on the stack
LCL = 1  # where the current function's local variables start
ARG = 2  # where the current function's arguments start
THIS = 3  # where the current object's fields start
THAT = 4  # where the current array's elements start

# ---------------------------------------------------------------------------
# Start addresses of each memory region.
# ---------------------------------------------------------------------------
TEMP_START = 5  # temp 0 is at address 5, temp 7 at address 12
STATIC_START = 16  # the first static variable lives at address 16
STACK_START = 256  # the stack grows upward from address 256
HEAP_START = 2048  # Memory.alloc hands out space from here
SCREEN_START = 16384  # first word of the screen
KEYBOARD = 24576  # the single keyboard "register"

# The total number of memory slots this VM provides.
# (The original Rust version uses KEYBOARD + 2, so we do the same.)
MEMORY_SIZE = KEYBOARD + 2

# ---------------------------------------------------------------------------
# The screen is 512 pixels wide and 256 pixels tall, black and white.
# Every memory word holds 16 pixels, so one row needs 512 / 16 = 32 words.
# ---------------------------------------------------------------------------
SCREEN_WIDTH = 512
SCREEN_HEIGHT = 256
WORDS_PER_ROW = SCREEN_WIDTH // 16  # = 32
SCREEN_SIZE_IN_WORDS = WORDS_PER_ROW * SCREEN_HEIGHT  # = 8192

# ---------------------------------------------------------------------------
# How the VM represents true and false.
# false is 0. true is -1, because -1 in 16-bit binary is 1111111111111111
# (all bits switched on). That makes "not true == false" work bit-by-bit.
# ---------------------------------------------------------------------------
TRUE = -1
FALSE = 0

# Friendly names for the low addresses - used by the debugger panel.
REGISTER_NAMES = {SP: "SP", LCL: "LCL", ARG: "ARG", THIS: "THIS", THAT: "THAT"}
for _i in range(8):
    REGISTER_NAMES[TEMP_START + _i] = f"TEMP{_i}"
for _i in (13, 14, 15):
    REGISTER_NAMES[_i] = f"R{_i}"


def to_int16(value: int) -> int:
    """
    Squeeze any Python integer into the 16-bit signed range (-32768..32767).

    WHY IS THIS NEEDED?
    Python integers can grow as big as you like: 32767 + 1 is simply 32768.
    Real 16-bit hardware cannot store 32768, so the number "wraps around"
    to -32768 instead (just like a car's odometer rolling over from 99999
    to 00000). Jack programs rely on this behaviour, so we copy it.

    HOW DOES IT WORK?
      1. Add 32768 so the valid range becomes 0..65535.
      2. "& 0xFFFF" keeps only the lowest 16 bits (0..65535), throwing the
         overflow away - this is the actual "wrap around".
      3. Subtract 32768 again to get back to -32768..32767.

    Examples:
        to_int16(5)       -> 5
        to_int16(32767+1) -> -32768   (overflow wraps around)
        to_int16(-32769)  -> 32767    (underflow wraps the other way)
    """
    return ((value + 32768) & 0xFFFF) - 32768
