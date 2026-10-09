"""
debugger.py - A live "X-ray" view of the virtual machine.
========================================================

Seeing the registers and the stack change while a game runs is one of the
best ways to understand how the VM works. The original web player showed a
table of registers and stack cells under the game; this is the same idea,
drawn as a panel on the right-hand side of the pygame window.

The panel is a column of boxes ("sections"):

    ┌ STATUS ─────────────────────┐   running / paused / halted / error,
    │ RUNNING                     │   PC + the NEXT instruction, speed
    │ pc 9338   sub               │
    └─────────────────────────────┘
    ┌ CALL STACK ─────────────────┐   which function called which
    ┌ REGISTERS ──────────────────┐   SP, LCL, ARG, THIS, THAT, TEMP0-7, keyboard
    ┌ STACK ──────────────────────┐   the top of the stack, arrow at SP
    ┌ WATCHED ADDRESSES ──────────┐   (only with --watch)

This module also builds the SHORTCUTS box that player.py shows under the
game screen (see `shortcuts_section`).

Tip: pause the game (Ctrl+P) and press Ctrl+N repeatedly to run ONE
instruction at a time while watching the stack.

The module is split in two:
  * `build_sections()` only produces text, so it can be tested without a window.
  * `DebuggerPanel` draws those sections as boxes with pygame.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

from .memory_map import KEYBOARD, REGISTER_NAMES, STACK_START, TEMP_START

# Each row of a section is (text, colour-name). Colours are chosen in draw().
Line = Tuple[str, str]

STACK_ROWS = 10  # how many stack cells to show
CALL_STACK_ROWS = 5  # how many nested function calls to show
ERROR_WRAP = 36  # characters per line when wrapping an error message
ERROR_MAX_ROWS = 4  # longer messages are cut short (the terminal has them in full)


@dataclass
class Section:
    """One box of the panel: a title and some rows of text."""

    title: str
    rows: List[Line] = field(default_factory=list)
    # Always reserve at least this many rows, so the boxes below don't jump
    # up and down when (say) the call stack gets shorter.
    min_rows: int = 0

    def add(self, text: str = "", colour: str = "normal") -> None:
        self.rows.append((text, colour))

    @property
    def row_count(self) -> int:
        return max(len(self.rows), self.min_rows)


# Shown in the SHORTCUTS box under the game screen. The items are laid out
# left to right and wrap onto a new row when the box is full ("flow layout").
HELP_ITEMS = [
    "Ctrl+P pause/resume",
    "Ctrl+N step",
    "Ctrl+R restart",
    "Ctrl+D debugger",
    "Ctrl+O open program",
    "Ctrl+Q quit",
    "Hold Esc 1 s: back to picker",
]
HELP_SEPARATOR = "   "


def _peek_text(vm, address: int, width: int) -> str:
    """
    Read one memory cell for display, right-aligned in `width` characters.

    The debugger is most useful exactly when something has gone wrong, for
    example after a stack overflow, when SP points past the end of memory.
    So it must never crash while looking at a broken VM: addresses outside
    memory are shown as "----" instead of raising IndexError.
    """
    if 0 <= address < len(vm.memory):
        return f"{vm.peek(address):>{width}}"
    return f"{'----':>{width}}"


def build_sections(vm, status: str, ticks_per_second: float, watch: Sequence[int] = (), error: str = "") -> List[Section]:
    """Describe the VM's current state as a list of Sections (top to bottom)."""
    sections: List[Section] = []

    # --- status + next instruction ----------------------------------------
    box = Section("STATUS")
    box.add(status, "error" if error else ("highlight" if status == "RUNNING" else "normal"))
    box.add(f"pc {vm.pc:<6} {vm.current_instruction()}")
    box.add(f"speed  {ticks_per_second / 1e6:5.2f} M instructions/s", "dim")
    box.add(f"ticks  {vm.ticks:,}", "dim")
    if status in ("HALTED", "ERROR"):
        box.add("Program finished: Esc to go back", "dim")
    sections.append(box)

    if error:
        box = Section("ERROR")
        for line in wrap_error(error):
            box.add(line, "error")
        sections.append(box)

    # --- call stack -----------------------------------------------------
    box = Section("CALL STACK (innermost first)", min_rows=CALL_STACK_ROWS + 1)
    names = [name for name, _ in reversed(vm.call_stack)]
    for name in names[:CALL_STACK_ROWS]:
        box.add(name)
    if len(names) > CALL_STACK_ROWS:
        box.add(f"... {len(names) - CALL_STACK_ROWS} more", "dim")
    if not names:
        box.add("(none)", "dim")
    sections.append(box)

    # --- registers ------------------------------------------------------
    box = Section("REGISTERS")
    for address in range(0, 5):
        box.add(f"{address:>2} {REGISTER_NAMES[address]:<6}{_peek_text(vm, address, 7)}")
    temps = [_peek_text(vm, TEMP_START + i, 6) for i in range(8)]
    box.add("TEMP0-3 " + " ".join(temps[:4]))
    box.add("TEMP4-7 " + " ".join(temps[4:]))
    box.add(f"KEYBOARD ({KEYBOARD}) {_peek_text(vm, KEYBOARD, 6)}")
    sections.append(box)

    # --- stack ------------------------------------------------------------
    # Show the cells just below SP: that's where the action is.
    sp = vm.peek(0)
    # Keep the window inside memory even if SP has run off the end
    # (after a stack overflow); the rows past the end show as "----".
    first = max(STACK_START, min(sp, len(vm.memory)) - STACK_ROWS + 1)
    box = Section("STACK (top is nearest SP)")
    for address in range(first, first + STACK_ROWS):
        marker = "  <- SP" if address == sp else ""
        colour = "highlight" if address == sp else ("normal" if address < sp else "dim")
        box.add(f"{address:>5}{_peek_text(vm, address, 8)}{marker}", colour)
    sections.append(box)

    # --- watched addresses -------------------------------------------------
    if watch:
        box = Section("WATCHED ADDRESSES")
        for address in watch:
            box.add(f"{address:>5}{_peek_text(vm, address, 8)}")
        sections.append(box)

    return sections


def wrap_error(error: str) -> List[str]:
    """
    Break an error message into lines that fit in the panel.

    textwrap breaks between words (never in the middle of one), like a word
    processor. At most ERROR_MAX_ROWS lines are kept, so the ERROR box has a
    known maximum size - see `largest_sections` for why that matters.
    """
    lines = textwrap.wrap(error, ERROR_WRAP) or [""]
    if len(lines) > ERROR_MAX_ROWS:
        lines = lines[:ERROR_MAX_ROWS]
        lines[-1] = lines[-1][: ERROR_WRAP - 3] + "..."  # show that we cut it short
    return lines


def largest_sections(vm, watch: Sequence[int] = ()) -> List[Section]:
    """
    The sections as TALL as they can ever get: status ERROR with a full-size
    ERROR box. The player sizes its window from this, so when a program does
    crash, the extra ERROR box still fits and nothing gets cut off the bottom.
    (Every other box has a fixed number of rows, so this is the worst case.)
    """
    longest_error = " ".join(["x" * (ERROR_WRAP - 1)] * (ERROR_MAX_ROWS + 1))
    return build_sections(vm, "ERROR", 0.0, watch, error=longest_error)


class DebuggerPanel:
    """Draws `build_sections()` onto a pygame surface as bordered boxes."""

    WIDTH = 330  # pixels
    COLOURS = {
        "normal": (230, 230, 230),
        "dim": (130, 130, 140),
        "title": (120, 190, 255),
        "highlight": (255, 210, 90),
        "error": (255, 110, 110),
    }
    BACKGROUND = (30, 30, 36)  # behind everything
    BOX = (40, 42, 52)  # inside a box
    BOX_HEADER = (50, 54, 70)  # the title strip of a box
    BORDER = (88, 96, 120)  # the box outline
    PADDING = 6  # space between a box's border and its text
    GAP = 8  # space between boxes
    RADIUS = 6  # rounded corners

    def __init__(self) -> None:
        import pygame  # imported here so build_sections() works without pygame

        self.pygame = pygame
        # Use the first monospace font we can find, so the columns line up.
        self.font = pygame.font.SysFont("menlo,consolas,dejavusansmono,couriernew,monospace", 13)
        self.line_height = self.font.get_linesize()
        self.header_height = self.line_height + 6

    # --- sizes ----------------------------------------------------------------
    def box_height(self, n_rows: int) -> int:
        return self.header_height + self.PADDING + n_rows * self.line_height + self.PADDING

    def required_height(self, sections: List[Section]) -> int:
        """Pixels needed to stack these sections one below the other."""
        total = sum(self.box_height(s.row_count) for s in sections)
        return total + self.GAP * max(0, len(sections) - 1)

    # --- the shortcuts box (drawn under the game screen) ---------------------------
    def shortcuts_section(self, width: int, extra: Sequence[str] = ()) -> Section:
        """
        Arrange HELP_ITEMS into rows that fit inside a box `width` pixels wide.

        This is a tiny "flow layout" - the same idea a word processor uses to
        wrap words onto the next line: keep adding items to the current row;
        when the next one wouldn't fit, start a new row.
        """
        usable = width - 2 * self.PADDING
        rows: List[str] = []
        current = ""
        quit_at = HELP_ITEMS.index("Ctrl+Q quit")  # `extra` items go just before quitting
        for item in [*HELP_ITEMS[:quit_at], *extra, *HELP_ITEMS[quit_at:]]:
            candidate = item if not current else current + HELP_SEPARATOR + item
            if current and self.font.size(candidate)[0] > usable:
                rows.append(current)  # row is full: start a new one
                current = item
            else:
                current = candidate
        if current:
            rows.append(current)
        return Section("SHORTCUTS", [(row, "dim") for row in rows])

    # --- drawing ----------------------------------------------------------------
    def draw_box(self, target, x: int, y: int, section: Section, width: int = WIDTH) -> int:
        """Draw one section as a box at (x, y). Returns the y below the box."""
        pygame = self.pygame
        height = self.box_height(section.row_count)
        outline = pygame.Rect(x, y, width, height)

        # Body, then the title strip, then the border on top of both.
        pygame.draw.rect(target, self.BOX, outline, border_radius=self.RADIUS)
        header = pygame.Rect(x, y, width, self.header_height)
        pygame.draw.rect(
            target, self.BOX_HEADER, header,
            border_top_left_radius=self.RADIUS, border_top_right_radius=self.RADIUS,
        )  # fmt: skip
        pygame.draw.line(target, self.BORDER, (x, header.bottom), (outline.right - 1, header.bottom))
        pygame.draw.rect(target, self.BORDER, outline, width=1, border_radius=self.RADIUS)

        target.blit(self.font.render(section.title, True, self.COLOURS["title"]), (x + self.PADDING, y + 3))
        text_y = header.bottom + self.PADDING
        for text, colour in section.rows:
            if text:
                target.blit(self.font.render(text, True, self.COLOURS[colour]), (x + self.PADDING, text_y))
            text_y += self.line_height
        return y + height

    def draw(self, target, x: int, y: int, sections: List[Section]) -> None:
        """Draw the info boxes stacked downward, starting at (x, y)."""
        for section in sections:
            y = self.draw_box(target, x, y, section) + self.GAP
