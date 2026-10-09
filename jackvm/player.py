"""
player.py - The game window: runs the VM and shows it with pygame.
=================================================================

This is the Python version of the original "JackVmPlayer" web component.
It connects four pieces together:

        keyboard events ---> Keyboard ---> VM memory[24576]
                                               |
                                    VirtualMachine.run()
                                               |
        window <--- ScreenRenderer <--- VM memory[16384..24575]
           ^
           +------- DebuggerPanel <--- registers / stack / pc

Window layout
-------------
    +-------------------------------------------------------------+
    |  margin                                                      |
    |   #==========================#   +-- STATUS ------------+   |
    |   #                          #   +-- CALL STACK --------+   |
    |   #   game screen (framed)   #   +-- REGISTERS ---------+   |
    |   #                          #   +-- STACK -------------+   |
    |   #==========================#   |                      |   |
    |   +-- SHORTCUTS -------------+   +----------------------+   |
    +-------------------------------------------------------------+

The right-hand column is the debugger (Ctrl+D hides it). The shortcuts box
always stays under the game, so you can always see how to pause or quit.

The main loop
-------------
Games are animated by repeating these steps about 60 times per second
(each repetition is one "frame"):

    1. Handle events: key presses, the window's close button, shortcuts.
    2. Run the VM for a slice of time (or a fixed number of instructions).
    3. Draw the screen memory (and the debugger panel) into the window.
    4. Wait a little so we don't redraw faster than 60 frames per second.

Quitting with Esc - without stealing Esc from the game
------------------------------------------------------
Some games use Esc themselves (Pong uses it to end the game), so a plain
"Esc quits" would break them. Instead:

  * While the program runs, Esc is ALWAYS passed to the game. If you keep
    holding it for ESC_HOLD_SECONDS (1 s), the player quits. A bar appears
    after ESC_SHOW_BAR_AFTER (0.25 s), so normal taps never flash it.
  * Once the program has finished (HALTED) or crashed (ERROR), the game
    can't read keys any more - so a single Esc press quits immediately.

How many VM instructions per frame?
-----------------------------------
By default we run the VM for as long as we can within each frame while
still keeping the window responsive ("time budget" mode, ~12 milliseconds).
Use --ticks-per-frame to run an exact number instead; the original web
player used 40,000.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pygame

from .debugger import DebuggerPanel, build_sections, largest_sections
from .file_picker import PLAY, QUIT, FilePicker
from .keyboard import Keyboard
from .memory_map import SCREEN_HEIGHT, SCREEN_WIDTH
from .parser import ParseError
from .program_files import GAMES_FOLDER, describe, read_program
from .screen import DEFAULT_OFF_COLOUR, DEFAULT_ON_COLOUR, Colour, ScreenRenderer
from .vm import VirtualMachine, VMError

FRAMES_PER_SECOND = 60
TIME_BUDGET_SECONDS = 0.012  # VM time per frame in "time budget" mode
CHUNK = 2_000  # instructions to run between clock checks

ESC_HOLD_SECONDS = 1.0  # hold Esc this long to quit
ESC_SHOW_BAR_AFTER = 0.25  # ...and show the "keep holding" bar after this long

# Layout (pixels) and colours of the window decoration.
MARGIN = 16  # empty space around the screen and the panel
FRAME_WIDTH = 3  # thickness of the border around the game screen
FRAME_GAP = 3  # space between the game screen and its border
FRAME_EXTENT = FRAME_GAP + FRAME_WIDTH  # how far the frame sticks out
FRAME_COLOUR = (150, 160, 190)
BACKGROUND = DebuggerPanel.BACKGROUND


class Player:
    def __init__(
        self,
        vm: VirtualMachine,
        files: Sequence[Path] = (),
        scale: int = 2,
        show_debugger: bool = True,
        ticks_per_frame: Optional[int] = None,
        start_paused: bool = False,
        on_colour: Colour = DEFAULT_ON_COLOUR,
        off_colour: Colour = DEFAULT_OFF_COLOUR,
        watch: Sequence[int] = (),
    ) -> None:
        self.vm = vm
        self.files = list(files)  # the .vm files that were loaded (for the title)
        self.scale = max(1, scale)
        self.show_debugger = show_debugger
        self.ticks_per_frame = ticks_per_frame
        self.paused = start_paused
        self.watch = list(watch)
        self.error = ""  # message of the last runtime error, if any

        self.renderer = ScreenRenderer(on_colour, off_colour)
        self.keyboard = Keyboard(vm)

        # The clock we read. It's an attribute so tests can replace it with a
        # fake clock and "hold" Esc for exactly 1 second without waiting.
        self.now = time.perf_counter
        self._esc_pressed_at: Optional[float] = None  # None = Esc not held

        # For the speed read-out in the debugger.
        self._speed = 0.0
        self._speed_ticks = 0
        self._speed_time = time.perf_counter()

    # ------------------------------------------------------------------
    # Window setup and layout
    # ------------------------------------------------------------------
    def _open_window(self) -> None:
        pygame.init()
        pygame.display.set_caption(self._title())
        self.screen_size = (SCREEN_WIDTH * self.scale, SCREEN_HEIGHT * self.scale)
        # Where the game screen goes: MARGIN in from the top-left corner.
        self.screen_rect = pygame.Rect((MARGIN, MARGIN), self.screen_size)
        self.panel = DebuggerPanel()
        self._resize_window()

    def _resize_window(self) -> None:
        """
        Work out where everything goes, then size the window to fit:

          left column:  the framed game screen, and the SHORTCUTS box below it
          right column: the debugger boxes (if shown)
          MARGIN pixels of empty space around everything
        """
        # The shortcuts box lines up with the outside edges of the screen's frame.
        frame = self.screen_rect.inflate(2 * FRAME_EXTENT, 2 * FRAME_EXTENT)
        self.shortcuts = self.panel.shortcuts_section(frame.width)
        self.shortcuts_rect = pygame.Rect(
            frame.left, frame.bottom + DebuggerPanel.GAP + 4,
            frame.width, self.panel.box_height(self.shortcuts.row_count),
        )  # fmt: skip

        width = self.screen_rect.right + MARGIN
        height = self.shortcuts_rect.bottom + MARGIN
        if self.show_debugger:
            width += DebuggerPanel.WIDTH + MARGIN
            # Size for the tallest the panel can get (an ERROR box showing),
            # so a crash never pushes boxes off the bottom of the window.
            panel_height = self.panel.required_height(largest_sections(self.vm, self.watch))
            height = max(height, MARGIN + panel_height + MARGIN)
        self.window = pygame.display.set_mode((width, height))

    def _title(self) -> str:
        return f"JackVM (Python) - {describe(self.files)}" if self.files else "JackVM (Python)"

    # ------------------------------------------------------------------
    # The main loop
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Open the window and play until the user quits."""
        self._open_window()
        clock = pygame.time.Clock()
        try:
            while self._handle_events() and not self._esc_held_long_enough():
                self._run_vm_for_one_frame()
                self._draw()
                clock.tick(FRAMES_PER_SECOND)
        finally:
            pygame.quit()

    # 1. Events -------------------------------------------------------------
    def _handle_events(self) -> bool:
        """Process all waiting events. Returns False when we should quit."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.KEYDOWN:
                # Ctrl (or Cmd on a Mac) + key = player shortcut, not game input.
                if event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META):
                    if not self._handle_shortcut(event.key):
                        return False
                    continue
                if event.key == pygame.K_ESCAPE:
                    if self.program_finished():
                        return False  # nothing left to protect: quit now
                    self._esc_pressed_at = self.now()  # start the hold timer
                self.keyboard.press(event.key, event.unicode)  # the game gets it too

            elif event.type == pygame.KEYUP:
                if event.key == pygame.K_ESCAPE:
                    self._esc_pressed_at = None  # let go early: cancel quitting
                self.keyboard.release(event.key)

            elif event.type == pygame.WINDOWFOCUSLOST:
                # Otherwise a key held while switching windows would "stick".
                self.keyboard.release_all()
                self._esc_pressed_at = None
        return True

    def program_finished(self) -> bool:
        """True once the program has halted or crashed (it can't read keys)."""
        return bool(self.error) or self.vm.is_halted()

    def esc_hold_progress(self) -> float:
        """How far through the 'hold Esc to quit' countdown we are: 0.0 .. 1.0."""
        if self._esc_pressed_at is None:
            return 0.0
        held_for = self.now() - self._esc_pressed_at
        return min(1.0, held_for / ESC_HOLD_SECONDS)

    def _esc_held_long_enough(self) -> bool:
        return self.esc_hold_progress() >= 1.0

    def _handle_shortcut(self, key: int) -> bool:
        """React to Ctrl+<key>. Returns False if the user asked to quit."""
        if key == pygame.K_q:
            return False
        if key == pygame.K_p:
            self.paused = not self.paused
        elif key == pygame.K_n:
            self.paused = True  # stepping only makes sense while paused
            self._safely(lambda: self.vm.tick())
        elif key == pygame.K_r:
            self.vm.restart()
            self.keyboard.release_all()
            self._esc_pressed_at = None
            self.error = ""
        elif key == pygame.K_d:
            self.show_debugger = not self.show_debugger
            self._resize_window()
        elif key == pygame.K_o:
            return self._open_another_program()
        return True

    def _open_another_program(self) -> bool:
        """
        Ctrl+O: show the file picker inside our window. If the user picks
        something, load it and start it; if they cancel, carry on as before.
        Returns False if the user closed the window (= quit).
        """
        self.keyboard.release_all()
        self._esc_pressed_at = None  # Esc in the picker means "cancel", not "quit"
        start = self.files[0].parent if self.files else GAMES_FOLDER

        # A tiny window (e.g. --scale 1 --no-debugger) is too cramped for a
        # file list, so make it at least 800 x 560 while the picker is open.
        width, height = self.window.get_size()
        if width < 800 or height < 560:
            self.window = pygame.display.set_mode((max(width, 800), max(height, 560)))

        outcome, files = choose_program(self.window, self.vm, start)
        if outcome == PLAY:
            self.files = files
            self.error = ""
            self.paused = False
            pygame.display.set_caption(self._title())
        self._resize_window()  # back to the normal player size
        return outcome != QUIT

    # 2. Run the VM ---------------------------------------------------------
    def _run_vm_for_one_frame(self) -> None:
        if self.paused or self.program_finished():
            return
        if self.ticks_per_frame:
            self._safely(lambda: self.vm.run(self.ticks_per_frame))
            return
        # Time-budget mode: keep running small chunks until the budget is used.
        deadline = time.perf_counter() + TIME_BUDGET_SECONDS
        while time.perf_counter() < deadline and not self.program_finished():
            self._safely(lambda: self.vm.run(CHUNK))

    def _safely(self, action) -> None:
        """Run `action`, turning a VM crash into a message instead of a crash."""
        try:
            action()
        except VMError as problem:
            self.error = str(problem)
            print(f"\nRuntime error: {problem}")

    # 3. Draw ---------------------------------------------------------------
    def _draw(self) -> None:
        self.window.fill(BACKGROUND)
        self._draw_game_screen()
        self.panel.draw_box(self.window, self.shortcuts_rect.x, self.shortcuts_rect.y, self.shortcuts, self.shortcuts_rect.width)
        if self.show_debugger:
            sections = build_sections(self.vm, self._status(), self._measure_speed(), self.watch, self.error)
            panel_x = self.screen_rect.right + MARGIN
            self.panel.draw(self.window, panel_x, MARGIN, sections)
        self._draw_quit_hints()
        pygame.display.flip()  # show everything we just drew

    def _draw_game_screen(self) -> None:
        # Screen memory -> RGB bytes -> pygame image -> scaled up -> window.
        rgb = self.renderer.to_rgb_bytes(self.vm.memory)
        image = pygame.image.frombuffer(rgb, (SCREEN_WIDTH, SCREEN_HEIGHT), "RGB")
        if self.scale != 1:
            image = pygame.transform.scale(image, self.screen_size)  # keeps pixels crisp
        self.window.blit(image, self.screen_rect)

        # A frame around the screen, so its edges are clear even when the
        # game's background is the same colour as the window's.
        frame = self.screen_rect.inflate(2 * FRAME_EXTENT, 2 * FRAME_EXTENT)
        pygame.draw.rect(self.window, FRAME_COLOUR, frame, width=FRAME_WIDTH, border_radius=4)

    def _draw_quit_hints(self) -> None:
        """The 'keep holding Esc' bar, or a 'press Esc to quit' note at the end."""
        progress = self.esc_hold_progress()
        if self._esc_pressed_at is not None and progress * ESC_HOLD_SECONDS >= ESC_SHOW_BAR_AFTER:
            self._draw_banner("Keep holding Esc to quit...", progress)
        elif self.program_finished():
            self._draw_banner("Program finished - press Esc to quit", None)

    def _draw_banner(self, text: str, progress: Optional[float]) -> None:
        """A dark, see-through box over the bottom of the game screen."""
        font = self.panel.font
        height = 44 if progress is not None else 28
        box = pygame.Rect(0, 0, min(380, self.screen_rect.width - 20), height)
        box.midbottom = (self.screen_rect.centerx, self.screen_rect.bottom - 10)

        overlay = pygame.Surface(box.size, pygame.SRCALPHA)  # SRCALPHA = allows see-through
        overlay.fill((20, 20, 26, 220))  # the 4th number is opacity (0..255)
        self.window.blit(overlay, box)
        pygame.draw.rect(self.window, FRAME_COLOUR, box, width=1, border_radius=4)

        label = font.render(text, True, (235, 235, 235))
        self.window.blit(label, label.get_rect(midtop=(box.centerx, box.top + 6)))
        if progress is not None:
            bar = pygame.Rect(box.left + 12, box.bottom - 14, box.width - 24, 6)
            pygame.draw.rect(self.window, (70, 70, 85), bar, border_radius=3)
            filled = bar.copy()
            filled.width = int(bar.width * progress)
            pygame.draw.rect(self.window, (255, 110, 110), filled, border_radius=3)

    def _status(self) -> str:
        if self.error:
            return "ERROR"
        if self.vm.is_halted():
            return "HALTED"
        return "PAUSED" if self.paused else "RUNNING"

    def _measure_speed(self) -> float:
        """Instructions per second, refreshed twice a second."""
        now = time.perf_counter()
        elapsed = now - self._speed_time
        if elapsed >= 0.5:
            self._speed = max(0, self.vm.ticks - self._speed_ticks) / elapsed
            self._speed_ticks = self.vm.ticks
            self._speed_time = now
        return self._speed


# ---------------------------------------------------------------------------
# Choosing a program with the GUI file picker
# ---------------------------------------------------------------------------
def choose_program(surface, vm: VirtualMachine, start_directory: Path) -> Tuple[str, Optional[List[Path]]]:
    """
    Show the file picker on `surface` until the user picks a program that
    loads without errors (or gives up).

    If the chosen files contain a mistake, the picker opens again with the
    problem shown at the top, so the user can choose something else.
    The VM is only changed when loading succeeds.

    Returns (outcome, files) - outcome is "play", "cancel" or "quit".
    """
    message = ""
    while True:
        outcome, files = FilePicker(surface, start_directory, message).run()
        if outcome != PLAY or not files:
            return outcome, None
        try:
            vm.load_source(read_program(files))
            return PLAY, files
        except ParseError as problem:
            first = problem.problems[0]
            more = f" (+{len(problem.problems) - 1} more)" if len(problem.problems) > 1 else ""
            message = f"Can't load {describe(files)}: {first.message} on line {first.line_number}{more}"
        except (OSError, UnicodeDecodeError) as problem:
            message = f"Can't read {describe(files)}: {problem}"
        print(message)
        start_directory = files[0].parent  # reopen where the user was


def open_picker_window(vm: VirtualMachine, start_directory: Path = GAMES_FOLDER) -> Optional[List[Path]]:
    """
    Used when jackvm is started without a program: open a window just for
    the picker. Returns the loaded files, or None if the user gave up.
    (The Player then reuses and resizes this same window.)
    """
    pygame.init()
    pygame.display.set_caption("JackVM (Python) - choose a program")
    surface = pygame.display.set_mode((900, 620))
    outcome, files = choose_program(surface, vm, start_directory)
    if outcome != PLAY:
        pygame.quit()
        return None
    return files
