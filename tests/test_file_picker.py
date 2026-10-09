"""
test_file_picker.py - Tests for the GUI file picker.
===================================================

Most tests use `PickerState` (pure logic, no window). The last few drive the
real pygame `FilePicker` with fake mouse/keyboard events, using SDL's
"dummy" video driver so no window actually appears on screen.
"""

import pytest

import pygame

from jackvm import VirtualMachine
from jackvm.file_picker import CANCEL, PLAY, QUIT, FilePicker, PickerState, list_entries
from jackvm.player import choose_program


@pytest.fixture
def tree(tmp_path):
    """
    A small folder tree to browse:

        tmp/
          .hidden/          (ignored)
          empty/            (no .vm files)
          pong/  Main.vm, Ball.vm
          notes.txt         (ignored: not a .vm file)
          solo.vm
    """
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "empty").mkdir()
    pong = tmp_path / "pong"
    pong.mkdir()
    (pong / "Main.vm").write_text("function Main.main 0\npush constant 0\nreturn\n")
    (pong / "Ball.vm").write_text("function Ball.new 0\npush constant 0\nreturn\n")
    (tmp_path / "notes.txt").write_text("not a program")
    (tmp_path / "solo.vm").write_text("function Main.main 0\npush constant 0\nreturn\n")
    return tmp_path


# --- logic -------------------------------------------------------------------
def test_entries_are_parent_then_folders_then_vm_files(tree):
    entries = list_entries(tree)
    assert [(e.kind, e.path.name) for e in entries] == [
        ("parent", tree.parent.name),
        ("folder", "empty"),
        ("folder", "pong"),
        ("vm", "solo.vm"),
    ]
    assert [e.vm_count for e in entries if e.kind == "folder"] == [0, 2]
    assert entries[2].label == "pong/"


def test_clicking_a_vm_file_plays_just_that_file(tree):
    state = PickerState(tree)
    assert state.activate(3) == [tree / "solo.vm"]


def test_clicking_a_folder_opens_it_and_play_folder_plays_all_files(tree):
    state = PickerState(tree)
    assert state.activate(2) is None  # opened pong/
    assert state.directory == (tree / "pong").resolve()
    assert state.current_folder_vm_count() == 2
    files = state.play_current_folder()
    assert [f.name for f in files] == ["Ball.vm", "Main.vm"]


def test_play_button_on_a_folder_row(tree):
    state = PickerState(tree)
    files = state.play_folder_entry(2)  # the "[play 2 files]" next to pong/
    assert [f.name for f in files] == ["Ball.vm", "Main.vm"]


def test_playing_a_folder_without_vm_files_explains_why(tree):
    state = PickerState(tree)
    assert state.play_folder_entry(1) is None  # the "empty/" row
    assert "no .vm files" in state.message

    state.open_folder(tree / "empty")  # now look INSIDE the empty folder
    assert state.current_folder_vm_count() == 0
    assert state.play_current_folder() is None
    assert "no .vm files" in state.message


def test_going_up_reselects_the_folder_we_came_from(tree):
    state = PickerState(tree / "pong")
    state.go_up()
    assert state.directory == tree.resolve()
    assert state.entries[state.selected].path.name == "pong"


def test_selection_stays_in_range(tree):
    state = PickerState(tree)
    state.move(-100)
    assert state.selected == 0
    state.move(+100)
    assert state.selected == len(state.entries) - 1


# --- the real pygame picker, with fake events ----------------------------------
@pytest.fixture
def surface():
    pygame.init()
    window = pygame.display.set_mode((900, 620))
    yield window
    pygame.quit()


def key(k, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="")


def click(pos):
    return pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=pos)


def test_keyboard_navigation(tree, surface):
    picker = FilePicker(surface, tree)
    picker.draw()
    assert picker._handle_event(key(pygame.K_DOWN)) is None  # -> pong/
    outcome, files = picker._handle_event(key(pygame.K_RETURN, pygame.KMOD_CTRL))  # play folder
    assert outcome == PLAY and [f.name for f in files] == ["Ball.vm", "Main.vm"]
    assert picker._handle_event(key(pygame.K_ESCAPE)) == (CANCEL, None)
    assert picker._handle_event(pygame.event.Event(pygame.QUIT)) == (QUIT, None)
    assert picker._handle_event(key(pygame.K_q, pygame.KMOD_CTRL)) == (QUIT, None)
    picker._esc_needs_release = True  # opened while Esc was held down
    assert picker._handle_event(key(pygame.K_ESCAPE)) is None
    picker._handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0))
    assert picker._handle_event(key(pygame.K_ESCAPE)) == (CANCEL, None)


@pytest.mark.parametrize("back_to, esc, button", [("", "Esc: quit", "Quit"), ("pong/", "Esc: back to pong/", "Back")])
@pytest.mark.parametrize("with_compiler", [False, True])
def test_the_picker_says_what_esc_does_and_fits(tree, surface, monkeypatch, back_to, esc, button, with_compiler):
    surface = pygame.display.set_mode((800, 560))  # the smallest picker window
    picker = FilePicker(surface, tree, compiler_folder=tree if with_compiler else None,
                        open_in_compiler=(lambda f: "") if with_compiler else None, back_to=back_to)  # fmt: skip
    drawn = []
    monkeypatch.setattr(picker, "_text", lambda text, *a, **k: drawn.append(text))
    monkeypatch.setattr(picker, "_button", lambda rect, label, **k: drawn.append(label))
    picker.draw()
    footer = next(t for t in drawn if "Ctrl+Q: quit" in t)
    assert esc in footer and button in drawn and ("Ctrl+J" in footer) == with_compiler
    assert picker.small.size(footer)[0] <= 800 - 2 * picker.MARGIN  # fits the smallest window


def test_mouse_clicks_on_rows_and_buttons(tree, surface):
    picker = FilePicker(surface, tree)
    picker.draw()  # works out where everything is on screen
    rows = {picker.state.entries[i].path.name: (rect, play) for rect, i, play in picker._row_rects}

    # Click the "[play 2 files]" tag on the pong/ row.
    outcome, files = picker._handle_event(click(rows["pong"][1].center))
    assert outcome == PLAY and len(files) == 2

    # Click the solo.vm row.
    outcome, files = picker._handle_event(click(rows["solo.vm"][0].center))
    assert outcome == PLAY and files == [tree / "solo.vm"]

    # Click the pong/ row itself: opens the folder, then "Play this folder".
    assert picker._handle_event(click(rows["pong"][0].center)) is None
    picker.draw()
    outcome, files = picker._handle_event(click(picker._play_button.center))
    assert outcome == PLAY and len(files) == 2

    assert picker._handle_event(click(picker._cancel_button.center)) == (CANCEL, None)


def test_choose_program_reopens_with_a_message_when_the_file_is_broken(tree, surface, monkeypatch):
    (tree / "broken.vm").write_text("function Main.main 0\nfly away\n")
    answers = [(PLAY, [tree / "broken.vm"]), (PLAY, [tree / "solo.vm"])]
    messages = []

    def fake_run(self):
        messages.append(self.state.message)
        return answers.pop(0)

    monkeypatch.setattr(FilePicker, "run", fake_run)
    vm = VirtualMachine()
    outcome, files = choose_program(surface, vm, tree)

    assert outcome == PLAY and files == [tree / "solo.vm"]
    assert messages[0] == ""
    assert "Unrecognised instruction 'fly' on line 2" in messages[1]
    assert "Main.main" in vm.addresses  # the good program was loaded


def test_ctrl_o_in_the_player_switches_program_or_keeps_the_old_one(surface, monkeypatch):
    from jackvm.player import Player
    from jackvm.program_files import read_program, resolve_paths

    pong = resolve_paths(["pong"])
    vm = VirtualMachine()
    vm.load_source(read_program(pong))
    player = Player(vm, files=pong)
    player._open_window()
    size_before = player.window.get_size()

    # 1. The user cancels: Pong stays loaded.
    monkeypatch.setattr(FilePicker, "run", lambda self: (CANCEL, None))
    assert player._open_another_program() is True
    assert "PongGame.run" in vm.addresses

    # 2. The user picks the square game: it is loaded and the title changes.
    square = resolve_paths(["square-game"])
    monkeypatch.setattr(FilePicker, "run", lambda self: (PLAY, square))
    assert player._open_another_program() is True
    assert player.files == square
    assert "SquareGame.run" in vm.addresses and "PongGame.run" not in vm.addresses
    assert "square-game/ (3 files)" in pygame.display.get_caption()[0]
    assert player.window.get_size() == size_before  # back to the normal size

    # 3. The user closes the window while choosing: the player should quit.
    monkeypatch.setattr(FilePicker, "run", lambda self: (QUIT, None))
    assert player._open_another_program() is False
