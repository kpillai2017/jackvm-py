"""
keyboard.py - Translate real key presses into Hack keyboard codes.
=================================================================

How the Hack keyboard works
---------------------------
There is just ONE memory address for the keyboard: 24576 (KEYBOARD).

    * While a key is held down, that address contains the key's code.
    * When no key is held down, it contains 0.

A Jack program "reads the keyboard" simply by peeking at that address
(that's literally what `Keyboard.keyPressed()` in the OS does).

Key codes
---------
Normal characters use their ASCII code ('A' = 65, '0' = 48, space = 32).
Keys that don't print anything get special codes from 128 upward:

    Enter 128   Backspace 129   Left 130   Up 131     Right 132  Down 133
    Home 134    End 135         PgUp 136   PgDn 137   Insert 138 Delete 139
    Esc 140     F1..F12 = 141..152

LETTERS ARE ALWAYS UPPER-CASE. Both the official nand2tetris emulator and
the original jackvm-rs report the *key* rather than the typed character, so
pressing "q" gives 81 ('Q'). Existing games depend on that (Square Game
quits on 81), so we do the same.

This file has two parts:
  * `hack_key_code()` - a pure function: pygame key -> Hack code.
  * `Keyboard`        - remembers which keys are held and writes the right
                        code into the VM's memory.
"""

from __future__ import annotations

from typing import Dict, List, Optional

import pygame

from .memory_map import KEYBOARD

# pygame key constant -> Hack key code, for keys that aren't plain characters.
SPECIAL_KEYS: Dict[int, int] = {
    pygame.K_RETURN: 128,
    pygame.K_KP_ENTER: 128,
    pygame.K_BACKSPACE: 129,
    pygame.K_LEFT: 130,
    pygame.K_UP: 131,
    pygame.K_RIGHT: 132,
    pygame.K_DOWN: 133,
    pygame.K_HOME: 134,
    pygame.K_END: 135,
    pygame.K_PAGEUP: 136,
    pygame.K_PAGEDOWN: 137,
    pygame.K_INSERT: 138,
    pygame.K_DELETE: 139,
    pygame.K_ESCAPE: 140,
}
# F1..F12 are numbered one after another, both in pygame and in Hack.
_F_KEYS = [
    pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4, pygame.K_F5, pygame.K_F6,
    pygame.K_F7, pygame.K_F8, pygame.K_F9, pygame.K_F10, pygame.K_F11, pygame.K_F12,
]  # fmt: skip
for _number, _key in enumerate(_F_KEYS):
    SPECIAL_KEYS[_key] = 141 + _number


def hack_key_code(key: int, unicode_text: str = "") -> Optional[int]:
    """
    Work out the Hack code for a key press.

    `key` is pygame's key constant (event.key) and `unicode_text` is the
    character it typed (event.unicode), which may be "" for keys like Shift.
    Returns None for keys the Hack computer doesn't know about.
    """
    if key in SPECIAL_KEYS:
        return SPECIAL_KEYS[key]

    if len(unicode_text) == 1 and 32 <= ord(unicode_text) <= 126:
        # A printable character. Letters become upper-case (see above).
        return ord(unicode_text.upper())

    # Some keyboards/OSes give no text (e.g. when Ctrl/Alt is held). For letter
    # and digit keys we can still work it out from the key itself.
    if pygame.K_a <= key <= pygame.K_z:
        return ord("A") + (key - pygame.K_a)
    if pygame.K_0 <= key <= pygame.K_9 or key == pygame.K_SPACE:
        return key  # pygame uses the ASCII codes for these keys
    return None


class Keyboard:
    """
    Keeps the VM's keyboard register up to date.

    We remember every key that is currently held down. The register always
    shows the most recently pressed one. If you hold LEFT, tap SPACE, and
    let go of SPACE, the register goes back to LEFT instead of 0 - which
    feels much better in games.
    """

    def __init__(self, vm) -> None:
        self.vm = vm
        self.held: List[int] = []  # pygame keys held, oldest first
        self.codes: Dict[int, int] = {}  # pygame key -> Hack code

    def press(self, key: int, unicode_text: str = "") -> None:
        code = hack_key_code(key, unicode_text)
        if code is None:
            return
        if key in self.held:
            self.held.remove(key)
        self.held.append(key)
        self.codes[key] = code
        self._update_register()

    def release(self, key: int) -> None:
        if key in self.held:
            self.held.remove(key)
            del self.codes[key]
        self._update_register()

    def release_all(self) -> None:
        """Forget all keys (e.g. when the window loses focus)."""
        self.held.clear()
        self.codes.clear()
        self._update_register()

    def current_code(self) -> int:
        return self.codes[self.held[-1]] if self.held else 0

    def _update_register(self) -> None:
        self.vm.poke(KEYBOARD, self.current_code())
