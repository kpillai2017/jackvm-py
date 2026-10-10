"""
file_picker.py - Choose a program to run with the mouse (or keyboard).
=====================================================================

Instead of typing a path on the command line, you can pick a program in a
simple file browser drawn inside the pygame window:

    python -m jackvm            # no program given -> the picker opens
    python -m jackvm --gui      # same thing, explicitly
    Ctrl+O while a game runs    # open the picker to switch programs

If the Jack compiler (https://github.com/kpillai2017/jack-compiler) is
installed, the picker also lists .jack files and offers "[compile+play]"
for folders of Jack source - see jack_sources.py. If the code has a
mistake, the first error shows at the top and Ctrl+J opens the folder in
the compiler's window. If jack-decompiler is installed, Ctrl+U opens the
selected .vm file or folder (or else the folder you're in) in the
decompiler's window - see decompiler_link.py.

You can play either:

  * a single **.vm file**  - click it, or
  * a **folder of .vm files** - e.g. `games/pong/` holds Main.vm, Ball.vm,
    Bat.vm and PongGame.vm (one file per Jack class, which is exactly what
    the nand2tetris compiler produces). Click "[play]" next to the folder,
    or open the folder and press the "Play this folder" button.

What it looks like:

    Choose a .vm file, or a folder of .vm files
    /Users/you/jackvm-py/games
    -----------------------------------------------------------
     <-  .. (parent folder)
     [+] average/                               [play 9 files]
     [+] pong/                                  [play 4 files]
     [+] space-invaders/                       [play 12 files]
    -----------------------------------------------------------
     [ Play this folder ]   [ Quit ]   ("Back" when opened from a program)

Why not a "native" Open dialog?
-------------------------------
Python's built-in dialogs come from `tkinter`. On macOS, tkinter and pygame
both want to control the app's window system, and mixing them is a common
cause of crashes (and the Python that ships with macOS uses an old, buggy
Tk). Drawing our own browser with pygame avoids all that - and it's a nice
small example of building a user interface from scratch.

Structure
---------
* `list_entries()` and `PickerState` contain all the *logic* (which files
  exist, what is selected, what happens when you click). No pygame needed,
  so they're easy to test.
* `FilePicker` only *draws* the state and turns mouse/keyboard events into
  calls on `PickerState`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from . import program_files
from .jack_sources import jack_files_in

# What the picker can end with:
PLAY = "play"  # the user chose something to run
CANCEL = "cancel"  # the user pressed Esc / Back / Quit (the caller decides which it means)
QUIT = "quit"  # the user closed the window
FIND_COMPILER = "find-compiler"  # Ctrl+J without a Jack compiler: ask where it is
FIND_DECOMPILER = "find-decompiler"  # Ctrl+U without the decompiler: ask where it is (then open the files)


# ---------------------------------------------------------------------------
# Part 1: logic (no pygame)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Entry:
    """One row in the file list."""

    kind: str  # "parent" (the .. row), "folder", "vm" or "jack"
    path: Path
    vm_count: int = 0  # for folders: how many .vm files are directly inside
    jack_count: int = 0  # ...and how many .jack files (only counted if we can compile)

    @property
    def label(self) -> str:
        if self.kind == "parent":
            return "..  (parent folder)"
        if self.kind == "folder":
            return self.path.name + "/"
        return self.path.name


def vm_files_in(folder: Path) -> List[Path]:
    """All .vm files directly inside `folder` (or [] if it can't be read)."""
    try:
        return program_files.vm_files_in(folder)
    except OSError:  # e.g. no permission to read the folder
        return []


def list_entries(directory: Path, show_jack: bool = False) -> List[Entry]:
    """
    Everything the picker shows for `directory`, in display order:
    the parent folder first, then sub-folders, then .vm files (and .jack
    files, if `show_jack` - i.e. the Jack compiler is installed).
    Hidden items (names starting with ".") and other file types are skipped.
    """
    entries: List[Entry] = []
    if directory.parent != directory:  # the top of the disk has no parent
        entries.append(Entry("parent", directory.parent))

    folders, vm_files, jack_files = [], [], []
    try:
        children = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        children = []
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            if child.is_dir():
                jack_count = len(jack_files_in(child)) if show_jack else 0
                folders.append(Entry("folder", child, len(vm_files_in(child)), jack_count))
            elif child.suffix.lower() == ".vm":
                vm_files.append(Entry("vm", child))
            elif show_jack and child.suffix.lower() == ".jack":
                jack_files.append(Entry("jack", child))
        except OSError:
            continue  # unreadable item: just leave it out
    return entries + folders + vm_files + jack_files


class PickerState:
    """
    Remembers which folder we're in and which row is selected, and decides
    what each action does. Every method that can finish the picker returns
    the list of .vm files to play, or None to keep browsing.
    """

    def __init__(self, directory: Path, can_compile: bool = False) -> None:
        self.message = ""  # feedback shown to the user (e.g. an error)
        self.can_compile = can_compile  # is the Jack compiler installed?
        self.open_folder(directory)

    # --- navigation -------------------------------------------------------
    def open_folder(self, directory: Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.entries = list_entries(self.directory, self.can_compile)
        # Start on the first real item rather than on "..", if there is one.
        self.selected = 1 if len(self.entries) > 1 and self.entries[0].kind == "parent" else 0
        self.message = ""

    def go_up(self) -> None:
        if self.directory.parent != self.directory:
            child = self.directory
            self.open_folder(self.directory.parent)
            # Re-select the folder we just came out of - feels natural.
            for index, entry in enumerate(self.entries):
                if entry.path == child:
                    self.selected = index

    def move(self, delta: int) -> None:
        """Move the selection up (negative) or down (positive)."""
        if self.entries:
            self.selected = max(0, min(len(self.entries) - 1, self.selected + delta))

    # --- choosing ---------------------------------------------------------
    def activate(self, index: Optional[int] = None) -> Optional[List[Path]]:
        """What Enter / a click does: play a .vm file, or open a folder."""
        if index is not None:
            self.selected = index
        if not self.entries:
            return None
        entry = self.entries[self.selected]
        if entry.kind in ("vm", "jack"):  # a .jack file means "compile its folder"
            return [entry.path]
        if entry.kind == "parent":
            self.go_up()
        else:
            self.open_folder(entry.path)
        return None

    def play_folder_entry(self, index: Optional[int] = None) -> Optional[List[Path]]:
        """Play all .vm files of the selected (or given) folder row."""
        if index is not None:
            self.selected = index
        if not self.entries:
            return None
        entry = self.entries[self.selected]
        if entry.kind in ("vm", "jack"):
            return [entry.path]
        if entry.kind == "folder":
            return self._play_folder(entry.path)
        return self.play_current_folder()

    def play_current_folder(self) -> Optional[List[Path]]:
        """Play all .vm files in the folder we're looking at."""
        return self._play_folder(self.directory)

    def _play_folder(self, folder: Path) -> Optional[List[Path]]:
        if self.can_compile and jack_files_in(folder):
            return [folder]  # Jack source: compiled before it's played
        files = vm_files_in(folder)
        if not files:
            kinds = ".vm or .jack" if self.can_compile else ".vm"
            self.message = f"There are no {kinds} files directly inside {folder.name or folder}/"
            return None
        return files

    def decompile_targets(self) -> Optional[List[Path]]:
        """
        Ctrl+U: the .vm files to open in the decompiler - the selected .vm
        file, the .vm files of the selected folder, or else (on the ".." row
        or a .jack file) those of the folder we're looking at.
        """
        entry = self.entries[self.selected] if self.entries else None
        if entry is not None and entry.kind == "vm":
            return [entry.path]
        folder = entry.path if entry is not None and entry.kind == "folder" else self.directory
        files = vm_files_in(folder)
        if not files:
            self.message = f"There are no .vm files to decompile directly inside {folder.name or folder}/"
            return None
        return files

    def current_folder_vm_count(self) -> int:
        return sum(1 for e in self.entries if e.kind == "vm")

    def current_folder_jack_count(self) -> int:
        return sum(1 for e in self.entries if e.kind == "jack")


# ---------------------------------------------------------------------------
# Part 2: drawing and input (pygame)
# ---------------------------------------------------------------------------
class FilePicker:
    """Shows a PickerState in a pygame window and handles mouse/keyboard."""

    BACKGROUND = (30, 30, 36)
    TEXT = (230, 230, 230)
    DIM = (130, 130, 140)
    TITLE = (120, 190, 255)
    SELECTED_ROW = (60, 70, 100)
    HOVER_ROW = (45, 48, 60)
    ERROR = (255, 110, 110)
    BUTTON = (70, 110, 170)
    BUTTON_DISABLED = (60, 60, 68)

    MARGIN = 16

    def __init__(
        self,
        surface,
        start_directory: Path,
        message: str = "",
        can_compile: bool = False,
        compiler_folder: Optional[Path] = None,
        open_in_compiler=None,
        back_to: str = "",
        offer_find_compiler: bool = False,
        open_in_decompiler=None,
        offer_find_decompiler: bool = False,
    ) -> None:
        import pygame  # imported here so the logic above works without pygame

        self.pygame = pygame
        self.surface = surface
        # Esc / the second button: back to the program that was open (e.g.
        # "Pong"), or, in the first picker, there's nothing to go back to - so it quits.
        self.back_to = back_to
        self._esc_needs_release = False  # see run()
        self.state = PickerState(start_directory, can_compile)
        self.state.message = message
        # After a failed compile: the folder Ctrl+J opens in the compiler, and
        # the function that does it (JackTools.open_in_compiler).
        self.compiler_folder = compiler_folder
        self.open_in_compiler = open_in_compiler
        # No Jack compiler found? Ctrl+J ends the picker with FIND_COMPILER,
        # and choose_program asks where it is (see locate_app.py).
        self.offer_find_compiler = offer_find_compiler
        # Ctrl+U: the function that opens .vm files in jack-decompiler
        # (Decompiler.open), or - if it isn't found - end the picker with
        # FIND_DECOMPILER so choose_program can ask where it is.
        self.open_in_decompiler = open_in_decompiler
        self.offer_find_decompiler = offer_find_decompiler
        self.font = pygame.font.SysFont("menlo,consolas,dejavusansmono,couriernew,monospace", 15)
        self.small = pygame.font.SysFont("menlo,consolas,dejavusansmono,couriernew,monospace", 13)
        self.row_height = self.font.get_linesize() + 8
        self.scroll = 0  # index of the first visible row
        # Filled in by draw(), used to work out what the mouse clicked on.
        self._row_rects: List[Tuple[object, int, Optional[object]]] = []
        self._play_button = None
        self._cancel_button = None

    # --- the picker's own little main loop --------------------------------
    def run(self) -> Tuple[str, Optional[List[Path]]]:
        """
        Show the picker until the user decides.
        Returns (PLAY, files), (CANCEL, None) or (QUIT, None).
        """
        pygame = self.pygame
        clock = pygame.time.Clock()
        pygame.key.set_repeat(300, 40)  # hold an arrow key to keep moving
        # Opened by HOLDING Esc? Then its key-repeat isn't a request to go back.
        self._esc_needs_release = bool(pygame.key.get_pressed()[pygame.K_ESCAPE])
        try:
            while True:
                for event in pygame.event.get():
                    result = self._handle_event(event)
                    if result is not None:
                        return result
                self.draw()
                pygame.display.flip()
                clock.tick(30)  # a file list doesn't need 60 frames/s
        finally:
            pygame.key.set_repeat()  # turn key repeat off again for games

    def _handle_event(self, event) -> Optional[Tuple[str, Optional[List[Path]]]]:
        pygame = self.pygame
        state = self.state
        files: Optional[List[Path]] = None

        if event.type == pygame.QUIT:
            return QUIT, None

        if event.type == pygame.KEYDOWN:
            ctrl = event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            if event.key == pygame.K_ESCAPE:
                return None if self._esc_needs_release else (CANCEL, None)
            if ctrl and event.key == pygame.K_q:
                return QUIT, None
            if ctrl and event.key == pygame.K_j and self.compiler_folder and self.open_in_compiler:
                state.message = self.open_in_compiler(self.compiler_folder)
                print(state.message)
            elif ctrl and event.key == pygame.K_j and self.offer_find_compiler:
                return FIND_COMPILER, None
            elif ctrl and event.key == pygame.K_u and self.open_in_decompiler:
                targets = state.decompile_targets()
                if targets:
                    state.message = self.open_in_decompiler(targets)
                print(state.message)
            elif ctrl and event.key == pygame.K_u and self.offer_find_decompiler:
                return FIND_DECOMPILER, state.decompile_targets()
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                files = state.play_folder_entry() if ctrl else state.activate()
            elif event.key in (pygame.K_BACKSPACE, pygame.K_LEFT):
                state.go_up()
            elif event.key == pygame.K_RIGHT:
                if state.entries and state.entries[state.selected].kind == "folder":
                    state.activate()
            elif event.key == pygame.K_UP:
                state.move(-1)
            elif event.key == pygame.K_DOWN:
                state.move(+1)
            elif event.key == pygame.K_PAGEUP:
                state.move(-self._visible_rows())
            elif event.key == pygame.K_PAGEDOWN:
                state.move(+self._visible_rows())
            elif event.key == pygame.K_HOME:
                state.move(-len(state.entries))
            elif event.key == pygame.K_END:
                state.move(+len(state.entries))

        elif event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE:
            self._esc_needs_release = False

        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 3)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:  # left click
            if self._cancel_button and self._cancel_button.collidepoint(event.pos):
                return CANCEL, None
            files = self._handle_click(event.pos)

        if files:
            return PLAY, files
        return None

    def _handle_click(self, position) -> Optional[List[Path]]:
        """Work out what is under the mouse and do the matching action."""
        if self._play_button and self._play_button.collidepoint(position):
            return self.state.play_current_folder()
        for row_rect, index, play_rect in self._row_rects:
            if play_rect is not None and play_rect.collidepoint(position):
                return self.state.play_folder_entry(index)
            if row_rect.collidepoint(position):
                return self.state.activate(index)
        return None

    # --- drawing ------------------------------------------------------------
    def _list_area(self):
        """The rectangle (x, y, width, height) where rows are drawn."""
        width, height = self.surface.get_size()
        top = self.MARGIN + 3 * self.font.get_linesize() + 14
        bottom = height - self.MARGIN - 44 - self.small.get_linesize() - 10
        return self.pygame.Rect(self.MARGIN, top, width - 2 * self.MARGIN, max(self.row_height, bottom - top))

    def _visible_rows(self) -> int:
        return max(1, self._list_area().height // self.row_height)

    def _keep_selection_visible(self) -> None:
        rows = self._visible_rows()
        selected = self.state.selected
        if selected < self.scroll:
            self.scroll = selected
        elif selected >= self.scroll + rows:
            self.scroll = selected - rows + 1
        self.scroll = max(0, min(self.scroll, max(0, len(self.state.entries) - rows)))

    def _text(self, text, colour, position, font=None) -> None:
        font = font or self.font
        self.surface.blit(font.render(text, True, colour), position)

    def _fit_left(self, text: str, max_width: int, font) -> str:
        """Shorten long paths from the LEFT: '.../games/pong' keeps the useful end."""
        if font.size(text)[0] <= max_width:
            return text
        while text and font.size("..." + text)[0] > max_width:
            text = text[1:]
        return "..." + text

    def _button(self, rect, label: str, enabled: bool) -> None:
        pygame = self.pygame
        pygame.draw.rect(self.surface, self.BUTTON if enabled else self.BUTTON_DISABLED, rect, border_radius=6)
        image = self.font.render(label, True, self.TEXT if enabled else self.DIM)
        self.surface.blit(image, image.get_rect(center=rect.center))

    def draw(self) -> None:
        pygame = self.pygame
        surface, state = self.surface, self.state
        width, height = surface.get_size()
        surface.fill(self.BACKGROUND)
        line = self.font.get_linesize()
        x = self.MARGIN

        # Header: title, current folder, message.
        title = "Choose a .vm or .jack file, or a folder of them" if state.can_compile else "Choose a .vm file, or a folder of .vm files"
        self._text(title, self.TITLE, (x, self.MARGIN))
        self._text(self._fit_left(str(state.directory), width - 2 * x, self.font), self.TEXT, (x, self.MARGIN + line))
        if state.message:  # (one line fits: the rest is printed in the terminal)
            self._text(state.message.split("\n")[0], self.ERROR, (x, self.MARGIN + 2 * line), self.small)

        # The list of entries (only the rows that fit).
        area = self._list_area()
        pygame.draw.line(surface, self.DIM, (area.left, area.top - 4), (area.right, area.top - 4))
        self._keep_selection_visible()
        mouse = pygame.mouse.get_pos()
        self._row_rects = []
        visible = state.entries[self.scroll : self.scroll + self._visible_rows()]
        for offset, entry in enumerate(visible):
            index = self.scroll + offset
            row = pygame.Rect(area.left, area.top + offset * self.row_height, area.width, self.row_height)
            if index == state.selected:
                pygame.draw.rect(surface, self.SELECTED_ROW, row, border_radius=4)
            elif row.collidepoint(mouse):
                pygame.draw.rect(surface, self.HOVER_ROW, row, border_radius=4)

            icon = {"parent": "<- ", "folder": "[+]", "vm": " * ", "jack": " # "}[entry.kind]
            colour = self.TEXT if entry.kind != "folder" or entry.vm_count or entry.jack_count else self.DIM
            self._text(f"{icon} {entry.label}", colour, (row.left + 8, row.top + 4))

            play_rect = None
            label = ""
            if entry.kind == "folder" and entry.jack_count:  # (only counted if we can compile)
                label = f"[compile+play {entry.jack_count} .jack]"
            elif entry.kind == "folder" and entry.vm_count:
                label = f"[play {entry.vm_count} file{'s' if entry.vm_count != 1 else ''}]"
            if label:
                image = self.font.render(label, True, self.TITLE)
                play_rect = image.get_rect(right=row.right - 8, top=row.top + 4)
                surface.blit(image, play_rect)
            self._row_rects.append((row, index, play_rect))

        if not state.entries:
            self._text("(this folder is empty)", self.DIM, (area.left + 8, area.top + 4))
        if len(state.entries) > self._visible_rows():
            shown = f"{self.scroll + 1}-{self.scroll + len(visible)} of {len(state.entries)}"
            self._text(shown, self.DIM, (area.right - self.small.size(shown)[0], area.bottom + 2), self.small)

        # Footer: help text and buttons.
        help_y = height - self.MARGIN - 44 - self.small.get_linesize() - 4
        pygame.draw.line(surface, self.DIM, (area.left, help_y - 4), (area.right, help_y - 4))
        self._text(self._footer(width - 2 * x), self.DIM, (x, help_y), self.small)
        jack_count = state.current_folder_jack_count()
        count = jack_count or state.current_folder_vm_count()
        if jack_count:
            play_label = f"Compile and play ({jack_count} .jack)"
        else:
            play_label = f"Play this folder ({count} file{'s' if count != 1 else ''})" if count else "Play this folder"
        self._play_button = pygame.Rect(x, height - self.MARGIN - 40, max(260, self.font.size(play_label)[0] + 30), 40)
        self._cancel_button = pygame.Rect(self._play_button.right + 12, self._play_button.top, 120, 40)
        self._button(self._play_button, play_label, enabled=count > 0)
        self._button(self._cancel_button, "Back" if self.back_to else "Quit", enabled=True)

    def _footer(self, width: int) -> str:
        """The key help, without its least important hints if it's too wide for `width`."""
        back_to = self.back_to if len(self.back_to) <= 20 else self.back_to[:19] + "…"
        parts = [
            "Enter: open", "Ctrl+Enter: play folder", "Backspace: up",
            f"Esc: back to {back_to}" if self.back_to else "Esc: quit", "Ctrl+Q: quit",
        ]  # fmt: skip
        if self.compiler_folder and self.open_in_compiler:
            parts.append("Ctrl+J: open in compiler")
        elif self.offer_find_compiler:
            parts.append("Ctrl+J: find the Jack compiler")
        if self.open_in_decompiler:
            parts.append("Ctrl+U: decompile")
        elif self.offer_find_decompiler:
            parts.append("Ctrl+U: find the decompiler")
        for drop in ("Backspace: up", "Ctrl+U: find the decompiler", "Enter: open", "Ctrl+Enter: play folder"):
            if self.small.size("   ".join(parts))[0] <= width:
                break
            if drop in parts:
                parts.remove(drop)
        return "   ".join(parts)
