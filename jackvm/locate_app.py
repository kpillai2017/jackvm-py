"""
locate_app.py - "Where is JackVM?": choose the other app's folder in the window.
================================================================================

When the companion app isn't found (see integrations.py), Ctrl+J doesn't
just say so: it opens this small folder chooser inside the same pygame
window, so the user can point at the checkout instead of editing a file:

    Where is JackVM? Open your jackvm-py folder, then press "Use this folder"
    /Users/you/code
    -----------------------------------------------------------
     <-  ..  (parent folder)
     [+] jack-compiler/
     [+] jackvm-py/                                       [use]
    -----------------------------------------------------------
     [ Use this folder ]   [ Back ]

Folders where the app can be run (its command, or its source with a virtual
environment - see integrations.check_folder) get a "[use]" button. The
choice is saved in the shared config file (integrations.save_setting), so
both apps find it from then on, from any folder.

This file is shared, like integrations.py: the same copy lives in both
repositories (jack_compiler/locate_app.py and jackvm/locate_app.py), and
tests/test_shared_files.py checks they match. It needs pygame only when the
window is drawn; `LocateState` (the logic) works without it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, List, Mapping, Optional, Tuple

from .integrations import App, Companion, check_folder, save_setting

# What the chooser can end with:
FOUND = "found"  # the user chose a folder where the app works (and it was saved)
CANCEL = "cancel"  # Esc / Back
QUIT = "quit"  # Ctrl+Q, or the window was closed

FONTS = "menlo,dejavusansmono,consolas,couriernew,monospace"


# ---------------------------------------------------------------------------
# Part 1: logic (no pygame)
# ---------------------------------------------------------------------------
class LocateState:
    """
    Which folder we're in, its sub-folders (and which of them hold the app),
    and the selected row. `check` is integrations.check_folder, swappable
    for tests.
    """

    def __init__(
        self, app: App, start: Path, check: Callable[[App, Path], Optional[Companion]] = check_folder
    ) -> None:
        self.app = app
        self.check = check
        self.message = ""
        self.chosen: Optional[Path] = None  # the folder use() accepted
        self.open_folder(start)
        for index, (path, _) in enumerate(self.entries):  # the usual name? select it
            if path.name == app.repo and path != self.directory.parent:
                self.selected = index

    def open_folder(self, directory: Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.entries: List[Tuple[Path, bool]] = []  # (folder, can the app run from it?)
        if self.directory.parent != self.directory:
            self.entries.append((self.directory.parent, False))  # the ".." row
        try:
            children = sorted(self.directory.iterdir(), key=lambda p: p.name.lower())
        except OSError:
            children = []
        for child in children:
            try:
                if not child.name.startswith(".") and child.is_dir():
                    self.entries.append((child, self.check(self.app, child) is not None))
            except OSError:
                continue
        self.selected = 1 if len(self.entries) > 1 and self.has_parent_row else 0
        self.message = ""

    @property
    def has_parent_row(self) -> bool:
        return bool(self.entries) and self.entries[0][0] == self.directory.parent != self.directory

    def is_parent_row(self, index: int) -> bool:
        return index == 0 and self.has_parent_row

    def go_up(self) -> None:
        if self.directory.parent != self.directory:
            child = self.directory
            self.open_folder(self.directory.parent)
            for index, (path, _) in enumerate(self.entries):
                if path == child and not self.is_parent_row(index):
                    self.selected = index

    def move(self, delta: int) -> None:
        if self.entries:
            self.selected = max(0, min(len(self.entries) - 1, self.selected + delta))

    def activate(self, index: Optional[int] = None) -> None:
        """Enter / a click on a row: open that folder (or go up)."""
        if index is not None:
            self.selected = index
        if not self.entries:
            return
        if self.is_parent_row(self.selected):
            self.go_up()
        else:
            self.open_folder(self.entries[self.selected][0])

    def use(self, folder: Optional[Path] = None) -> Optional[Companion]:
        """
        "Use this folder" (default: the one we're in) or a row's [use]:
        the Companion if the app runs from there, else None and a message.
        """
        folder = self.directory if folder is None else folder
        found = self.check(self.app, folder)
        self.chosen = folder.resolve() if found is not None else None
        if found is None:
            self.message = (f"No {self.app.executable} in {folder.name or folder}/ - "
                            f"open your {self.app.repo or self.app.title} folder (it needs a .venv with it installed)")  # fmt: skip
        return found

    def use_selected(self) -> Optional[Companion]:
        """Ctrl+Enter: use the selected row's folder."""
        if not self.entries or self.is_parent_row(self.selected):
            return self.use()
        return self.use(self.entries[self.selected][0])


def config_key_for(app: App) -> str:
    """The setting to save: jackc-gui is saved as its checkout, "jackc", which finds both."""
    return app.config_fallback or app.executable


# ---------------------------------------------------------------------------
# Part 2: drawing and input (pygame)
# ---------------------------------------------------------------------------
class FolderChooser:
    """Shows a LocateState in a pygame window; saves the folder the user chooses."""

    BACKGROUND = (30, 30, 36)
    TEXT = (230, 230, 230)
    DIM = (130, 130, 140)
    TITLE = (120, 190, 255)
    GOOD = (120, 220, 140)
    SELECTED_ROW = (60, 70, 100)
    HOVER_ROW = (45, 48, 60)
    ERROR = (255, 110, 110)
    BUTTON = (70, 110, 170)
    MARGIN = 16

    def __init__(
        self, surface, app: App, start: Optional[Path] = None, environ: Optional[Mapping[str, str]] = None,
        check: Callable[[App, Path], Optional[Companion]] = check_folder,
    ) -> None:  # fmt: skip
        import pygame  # imported here so LocateState works without pygame

        from .integrations import start_folder_for

        self.pygame = pygame
        self.surface = surface
        self.app = app
        self.environ = environ
        self.state = LocateState(app, start if start is not None else start_folder_for(app), check)
        self.font = pygame.font.SysFont(FONTS, 15)
        self.small = pygame.font.SysFont(FONTS, 13)
        self.row_height = self.font.get_linesize() + 8
        self.scroll = 0
        self.saved_to: Optional[Path] = None  # the config file, once saved
        self.save_problem = ""  # why it couldn't be saved (the folder is still used this time)
        self._row_rects: List[Tuple[object, int, Optional[object]]] = []
        self._use_button = None
        self._back_button = None
        self._esc_needs_release = False

    def run(self) -> Tuple[str, Optional[Companion]]:
        """Show the chooser until the user decides. Returns (FOUND, companion), (CANCEL, None) or (QUIT, None)."""
        pygame = self.pygame
        clock = pygame.time.Clock()
        pygame.key.set_repeat(300, 40)
        self._esc_needs_release = bool(pygame.key.get_pressed()[pygame.K_ESCAPE])
        try:
            while True:
                for event in pygame.event.get():
                    result = self._handle_event(event)
                    if result is not None:
                        return result
                self.draw()
                pygame.display.flip()
                clock.tick(30)
        finally:
            pygame.key.set_repeat()

    def _found(self, companion: Optional[Companion]) -> Optional[Tuple[str, Optional[Companion]]]:
        if companion is None:
            return None
        try:
            self.saved_to = save_setting(config_key_for(self.app), str(self.state.chosen), self.environ)
        except OSError as problem:
            self.save_problem = str(problem)
        return FOUND, companion

    def _handle_event(self, event) -> Optional[Tuple[str, Optional[Companion]]]:
        pygame = self.pygame
        state = self.state
        if event.type == pygame.QUIT:
            return QUIT, None
        if event.type == pygame.KEYDOWN:
            ctrl = event.mod & (pygame.KMOD_CTRL | pygame.KMOD_META)
            if event.key == pygame.K_ESCAPE:
                return None if self._esc_needs_release else (CANCEL, None)
            if ctrl and event.key == pygame.K_q:
                return QUIT, None
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if ctrl:
                    return self._found(state.use_selected())
                state.activate()
            elif event.key in (pygame.K_BACKSPACE, pygame.K_LEFT):
                state.go_up()
            elif event.key == pygame.K_RIGHT:
                if state.entries and not state.is_parent_row(state.selected):
                    state.activate()
            elif event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP, pygame.K_PAGEDOWN, pygame.K_HOME, pygame.K_END):
                page = self._visible_rows()
                state.move({pygame.K_UP: -1, pygame.K_DOWN: 1, pygame.K_PAGEUP: -page, pygame.K_PAGEDOWN: page,
                            pygame.K_HOME: -len(state.entries), pygame.K_END: len(state.entries)}[event.key])  # fmt: skip
        elif event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE:
            self._esc_needs_release = False
        elif event.type == pygame.MOUSEWHEEL:
            self.scroll = max(0, self.scroll - event.y * 3)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._back_button and self._back_button.collidepoint(event.pos):
                return CANCEL, None
            if self._use_button and self._use_button.collidepoint(event.pos):
                return self._found(state.use())
            for row, index, use_rect in self._row_rects:
                if use_rect is not None and use_rect.collidepoint(event.pos):
                    return self._found(state.use(state.entries[index][0]))
                if row.collidepoint(event.pos):
                    state.activate(index)
                    break
        return None

    # --- drawing ------------------------------------------------------------
    def _list_area(self):
        width, height = self.surface.get_size()
        top = self.MARGIN + 3 * self.font.get_linesize() + 14
        bottom = height - self.MARGIN - 44 - self.small.get_linesize() - 10
        return self.pygame.Rect(self.MARGIN, top, width - 2 * self.MARGIN, max(self.row_height, bottom - top))

    def _visible_rows(self) -> int:
        return max(1, self._list_area().height // self.row_height)

    def _text(self, text: str, colour, position, font=None) -> None:
        font = font or self.font
        width = self.surface.get_width() - position[0] - self.MARGIN
        while text and font.size(text)[0] > width:  # too long: cut it, keeping the start
            text = text[:-2] + "…"
        self.surface.blit(font.render(text, True, colour), position)

    def _button(self, rect, label: str) -> None:
        self.pygame.draw.rect(self.surface, self.BUTTON, rect, border_radius=6)
        image = self.font.render(label, True, self.TEXT)
        self.surface.blit(image, image.get_rect(center=rect.center))

    def footer(self, width: int) -> str:
        """The key hints, dropping the least important ones until they fit."""
        hints = ["Enter: open", "Ctrl+Enter: use selected", "Backspace: up", "Esc: back", "Ctrl+Q: quit"]
        while len(hints) > 2 and self.small.size("   ".join(hints))[0] > width:
            hints.pop(2 if len(hints) > 4 else 1)
        return "   ".join(hints)

    def draw(self) -> None:
        pygame = self.pygame
        surface, state = self.surface, self.state
        width, height = surface.get_size()
        surface.fill(self.BACKGROUND)
        line = self.font.get_linesize()
        x = self.MARGIN
        where = state.app.repo or state.app.title
        self._text(f'Where is {state.app.title}? Open your {where} folder, then press "Use this folder"', self.TITLE, (x, self.MARGIN))
        directory = str(state.directory)
        while len(directory) > 4 and self.font.size(directory)[0] > width - 2 * x:
            directory = "..." + directory[4:]
        self._text(directory, self.TEXT, (x, self.MARGIN + line))
        if state.message:
            self._text(state.message, self.ERROR, (x, self.MARGIN + 2 * line), self.small)
        else:
            self._text(f"[use] marks folders that have {state.app.executable}. It's saved in the config file for next time.",
                       self.DIM, (x, self.MARGIN + 2 * line), self.small)  # fmt: skip

        area = self._list_area()
        pygame.draw.line(surface, self.DIM, (area.left, area.top - 4), (area.right, area.top - 4))
        rows = self._visible_rows()
        if state.selected < self.scroll:
            self.scroll = state.selected
        elif state.selected >= self.scroll + rows:
            self.scroll = state.selected - rows + 1
        self.scroll = max(0, min(self.scroll, max(0, len(state.entries) - rows)))
        mouse = pygame.mouse.get_pos()
        self._row_rects = []
        for offset, (path, usable) in enumerate(state.entries[self.scroll : self.scroll + rows]):
            index = self.scroll + offset
            row = pygame.Rect(area.left, area.top + offset * self.row_height, area.width, self.row_height)
            if index == state.selected:
                pygame.draw.rect(surface, self.SELECTED_ROW, row, border_radius=4)
            elif row.collidepoint(mouse):
                pygame.draw.rect(surface, self.HOVER_ROW, row, border_radius=4)
            label = "<-  ..  (parent folder)" if state.is_parent_row(index) else f"[+] {path.name}/"
            self._text(label, self.GOOD if usable else self.TEXT, (row.left + 8, row.top + 4))
            use_rect = None
            if usable:
                image = self.font.render("[use]", True, self.GOOD)
                use_rect = image.get_rect(right=row.right - 8, top=row.top + 4)
                surface.blit(image, use_rect)
            self._row_rects.append((row, index, use_rect))
        if len(state.entries) <= (1 if state.has_parent_row else 0):
            self._text("(no folders here)", self.DIM, (area.left + 8, area.top + 4 + self.row_height))

        help_y = height - self.MARGIN - 44 - self.small.get_linesize() - 4
        pygame.draw.line(surface, self.DIM, (area.left, help_y - 4), (area.right, help_y - 4))
        self._text(self.footer(width - 2 * x), self.DIM, (x, help_y), self.small)
        self._use_button = pygame.Rect(x, height - self.MARGIN - 40, 220, 40)
        self._back_button = pygame.Rect(self._use_button.right + 12, self._use_button.top, 120, 40)
        self._button(self._use_button, "Use this folder")
        self._button(self._back_button, "Back")


def locate(
    surface, app: App, environ: Optional[Mapping[str, str]] = None, start: Optional[Path] = None
) -> Tuple[str, Optional[Companion], str]:
    """
    Ask the user where `app` is (see the module docstring). Returns
    (outcome, companion, message): the message says where it was saved.
    """
    chooser = FolderChooser(surface, app, start, environ)
    outcome, companion = chooser.run()
    if outcome != FOUND or companion is None:
        return outcome, None, ""
    if chooser.saved_to is not None:
        return outcome, companion, f"Found {app.title} - saved in {chooser.saved_to}"
    return outcome, companion, f"Found {app.title}, but couldn't save it: {chooser.save_problem}"
