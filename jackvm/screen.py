"""
screen.py - Turn the SCREEN part of memory into a picture.
=========================================================

How the Hack screen is stored
-----------------------------
The screen is 512 x 256 black-and-white pixels. It lives in memory starting
at address 16384 (SCREEN_START). Each 16-bit memory word holds 16 pixels,
one per bit:

    * Row r, word column c is at address  16384 + r * 32 + c
      (each row is 512 / 16 = 32 words long)
    * Inside a word, BIT 0 (the lowest, rightmost bit) is the LEFTMOST pixel
      of that group of 16, bit 1 is the next pixel to the right, and so on.

Example - the word at address 16384 (top-left corner) holds 5:

    5 in binary  =  0000 0000 0000 0101
                                  ^ ^
                             bit 2   bit 0
    So pixels x=0 and x=2 of row 0 are ON (black), the rest are OFF.

How we draw it quickly
----------------------
Checking 131,072 pixels one by one in Python, 60 times a second, would be too
slow. Instead we use a classic trick - a **lookup table**:

    There are only 256 possible values of a byte (8 bits = 8 pixels). We
    work out the colour bytes for each of them ONCE, at start-up. Then each
    16-pixel word is just two table look-ups (low byte, high byte) joined.

That turns ~131,000 small steps into ~16,000 per frame - fast enough.

This module does NOT need pygame (it only produces raw bytes or text), which
makes it easy to test. player.py hands the bytes to pygame for display.
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .memory_map import SCREEN_HEIGHT, SCREEN_SIZE_IN_WORDS, SCREEN_START, SCREEN_WIDTH, WORDS_PER_ROW

Colour = Tuple[int, int, int]  # (red, green, blue), each 0..255

# Defaults copied from the original nand2tetris look: black pixels on white.
DEFAULT_ON_COLOUR: Colour = (0, 0, 0)
DEFAULT_OFF_COLOUR: Colour = (255, 255, 255)


def pixel_is_on(memory: Sequence[int], x: int, y: int) -> bool:
    """
    Is the pixel at column x, row y switched on?

    This is the slow-but-obvious version - perfect for understanding the
    layout and for tests. The fast renderer below gives the same answers.
    """
    word = memory[SCREEN_START + y * WORDS_PER_ROW + x // 16]
    bit = x % 16
    return (word >> bit) & 1 == 1


def build_byte_table(on: Colour, off: Colour) -> List[bytes]:
    """
    For every possible byte value 0..255, pre-compute the RGB bytes of its
    8 pixels. table[5] for example is: ON, OFF, ON, OFF, OFF, OFF, OFF, OFF
    (bits 0 and 2 set), each pixel written as 3 bytes (red, green, blue).
    """
    on_bytes, off_bytes = bytes(on), bytes(off)
    table = []
    for value in range(256):
        pixels = [on_bytes if (value >> bit) & 1 else off_bytes for bit in range(8)]
        table.append(b"".join(pixels))
    return table


class ScreenRenderer:
    """Converts screen memory into an RGB byte string pygame can display."""

    def __init__(self, on: Colour = DEFAULT_ON_COLOUR, off: Colour = DEFAULT_OFF_COLOUR):
        self.table = build_byte_table(on, off)

    def to_rgb_bytes(self, memory: Sequence[int]) -> bytes:
        """
        Return the whole screen as bytes: 512 * 256 pixels * 3 colour bytes,
        row after row, left to right ("RGB" format).
        """
        table = self.table
        words = memory[SCREEN_START : SCREEN_START + SCREEN_SIZE_IN_WORDS]
        parts = []
        for word in words:
            word &= 0xFFFF  # treat negative numbers as their 16 raw bits
            parts.append(table[word & 0xFF])  # low byte  = pixels 0..7
            parts.append(table[word >> 8])  # high byte = pixels 8..15
        return b"".join(parts)


def to_ascii(memory: Sequence[int], x_step: int = 4, y_step: int = 8) -> str:
    """
    Draw the screen as text, e.g. for the terminal in --headless mode.

    The screen is shrunk: each character stands for a block of
    x_step * y_step pixels and is '#' if ANY pixel in that block is on.
    With the defaults that gives a 128 x 32 character picture.
    """
    lines = []
    for top in range(0, SCREEN_HEIGHT, y_step):
        row_chars = []
        for left in range(0, SCREEN_WIDTH, x_step):
            block_on = any(
                pixel_is_on(memory, x, y)
                for y in range(top, top + y_step)
                for x in range(left, left + x_step)
            )
            row_chars.append("#" if block_on else ".")
        lines.append("".join(row_chars))
    return "\n".join(lines)
