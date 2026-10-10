"""
test_decompiler_link.py - Ctrl+U: open the program in jack-decompiler.
=====================================================================

The real decompiler lives in another repository (jack-decompiler), so these
tests use a tiny FAKE `jackdecomp`: a Python script that writes the
arguments it was given into opened.txt, next to the first .vm file.
"""

import os
import re
import stat
import sys
import time
from pathlib import Path

import pygame
import pytest

from jackvm import VirtualMachine
from jackvm.decompiler_link import JACKDECOMP, Decompiler
from jackvm.integrations import Companion, find, not_found_message
from jackvm.player import Player

FAKE_DECOMPILER = """
import pathlib, sys
pathlib.Path(sys.argv[1]).with_name('opened.txt').write_text('\\n'.join(sys.argv[1:]))
"""
LOOP_FOREVER = "function Sys.init 0\nlabel L\ngoto L\n"


@pytest.fixture
def program(tmp_path):
    """A two-file program, Pong/Main.vm and Pong/Ball.vm."""
    folder = tmp_path / "Pong"
    folder.mkdir()
    for name in ("Main", "Ball"):
        (folder / f"{name}.vm").write_text(f"function {name}.f 0\npush constant 0\nreturn\n")
    return [folder / "Main.vm", folder / "Ball.vm"]


@pytest.fixture
def fake(tmp_path):
    path = tmp_path / "fake_jackdecomp.py"
    path.write_text(FAKE_DECOMPILER)
    return Companion(JACKDECOMP, [sys.executable, str(path)], "test")


def wait_for(path: Path, seconds: float = 20.0) -> str:
    """The fake runs in the background (like the real window): wait for its output."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.is_file() and path.read_text():
            return path.read_text()
        time.sleep(0.05)
    raise AssertionError(f"{path} was never written")


def make_player(files, decompiler):
    vm = VirtualMachine()
    vm.load_source(LOOP_FOREVER)
    player = Player(vm, files=files, decompiler=decompiler)
    player._open_window()
    return player


def ctrl(key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, mod=pygame.KMOD_CTRL, unicode=""))


# --- finding the decompiler ---------------------------------------------------------
def test_the_environment_variable_finds_it_or_switches_it_off():
    found = find(JACKDECOMP, environ={"JACKDECOMP": "python3 -m jack_decompiler"}, entry_points=[], which=lambda name: None)
    assert found.command == ["python3", "-m", "jack_decompiler"] and found.found_by == "$JACKDECOMP"
    assert find(JACKDECOMP, environ={"JACKDECOMP": "off"}, entry_points=[], which=lambda name: "/bin/jackdecomp") is None
    assert "switched off" in not_found_message(JACKDECOMP, {"JACKDECOMP": "off"})


def test_a_folder_in_the_config_file_finds_its_command(tmp_path):
    checkout = tmp_path / "jack-decompiler"
    command = checkout / ".venv" / ("Scripts" if os.name == "nt" else "bin") / ("jackdecomp.exe" if os.name == "nt" else "jackdecomp")
    command.parent.mkdir(parents=True)
    command.write_text("#!/bin/sh\n")
    command.chmod(command.stat().st_mode | stat.S_IEXEC)
    config = tmp_path / "config.ini"
    config.write_text(f"[apps]\njackdecomp = {checkout}\n")
    found = find(JACKDECOMP, environ={"JACK_TOOLS_CONFIG": str(config)}, entry_points=[], which=lambda name: None)
    assert found is not None and Path(found.command[0]) == command


def test_the_path_is_tried_last():
    found = find(JACKDECOMP, environ={"JACK_TOOLS_CONFIG": os.devnull}, entry_points=[], which=lambda name: f"/opt/{name}")
    assert found.command == ["/opt/jackdecomp"] and found.found_by == "PATH"


def test_it_matches_what_jack_decompiler_advertises():
    """jack-decompiler's pyproject.toml must offer the command and entry point we look for."""
    pyproject = Path(__file__).resolve().parents[2] / "jack-decompiler" / "pyproject.toml"
    if not pyproject.is_file():
        pytest.skip("jack-decompiler isn't checked out next to jackvm-py")
    text = pyproject.read_text(encoding="utf-8")
    assert re.search(rf'^{JACKDECOMP.executable}\s*=\s*"{JACKDECOMP.entry}"', text, re.M)
    assert re.search(rf'^{JACKDECOMP.key}\s*=\s*"{JACKDECOMP.entry}"', text, re.M)


# --- opening a program ----------------------------------------------------------------
def test_open_starts_the_decompiler_with_the_vm_files(fake, program):
    message = Decompiler(lambda: fake).open(program)
    assert message == "Opened Pong/ in the Jack decompiler"
    assert wait_for(program[0].with_name("opened.txt")).split("\n") == [str(f) for f in program]


def test_open_names_a_single_file(fake, program):
    assert Decompiler(lambda: fake).open(program[:1]) == "Opened Main.vm in the Jack decompiler"


def test_open_explains_what_is_wrong(fake, program, tmp_path):
    assert Decompiler(lambda: fake).open([]) == "No .vm files to decompile"
    assert Decompiler(lambda: fake).open([tmp_path / "Missing.vm"]) == "No .vm files to decompile"
    assert Decompiler(lambda: None).open(program).startswith("Jack decompiler is switched off")  # conftest.py
    broken = Companion(JACKDECOMP, [str(tmp_path / "no-such-command")], "test")
    assert Decompiler(lambda: broken).open(program).startswith("Couldn't start the Jack decompiler")


def test_the_shortcut_label_says_what_ctrl_u_will_do(fake, monkeypatch):
    assert Decompiler(lambda: fake).shortcut_label() == "Ctrl+U decompile"
    assert Decompiler(lambda: None).shortcut_label() == "Ctrl+U decompiler (not installed)"  # switched off
    monkeypatch.delenv("JACKDECOMP")
    assert Decompiler(lambda: None).shortcut_label() == "Ctrl+U find decompiler..."


# --- the player -------------------------------------------------------------------------
def test_player_ctrl_u_opens_the_program_and_shows_a_notice(fake, program):
    p = make_player(program, Decompiler(lambda: fake))
    assert any("Ctrl+U decompile" in row for row, _ in p.shortcuts.rows)
    ctrl(pygame.K_u)
    assert p._handle_events()
    assert p._notice[0] == "Opened Pong/ in the Jack decompiler"
    assert wait_for(program[0].with_name("opened.txt"))
    pygame.quit()


def test_player_without_the_decompiler_says_so(program):
    p = make_player(program, Decompiler(lambda: None))
    assert any("Ctrl+U decompiler (not installed)" in row for row, _ in p.shortcuts.rows)
    ctrl(pygame.K_u)
    assert p._handle_events()
    assert p._notice[0].startswith("Jack decompiler is switched off")
    pygame.quit()


def test_player_ctrl_u_finds_the_decompiler_then_opens_the_program(fake, program, monkeypatch):
    import jackvm.decompiler_link as decompiler_link
    from jackvm.locate_app import FOUND

    monkeypatch.delenv("JACKDECOMP")
    saved = {}

    def fake_locate(surface, app):
        assert app is JACKDECOMP
        saved["app"] = fake
        return FOUND, fake, "Found Jack decompiler - saved in config.ini"

    monkeypatch.setattr(decompiler_link, "locate", fake_locate)
    p = make_player(program, Decompiler(lambda: saved.get("app")))
    assert any("Ctrl+U find decompiler..." in row for row, _ in p.shortcuts.rows)
    ctrl(pygame.K_u)
    assert p._handle_events()
    assert p._notice[0] == "Opened Pong/ in the Jack decompiler"
    assert any("Ctrl+U decompile" in row for row, _ in p.shortcuts.rows)
    assert wait_for(program[0].with_name("opened.txt"))
    pygame.quit()


def test_player_ctrl_q_in_the_chooser_quits(program, monkeypatch):
    import jackvm.decompiler_link as decompiler_link
    from jackvm.locate_app import QUIT

    monkeypatch.delenv("JACKDECOMP")
    monkeypatch.setattr(decompiler_link, "locate", lambda surface, app: (QUIT, None, ""))
    p = make_player(program, Decompiler(lambda: None))
    ctrl(pygame.K_u)
    assert p._handle_events() is False
    pygame.quit()


# --- the file picker ----------------------------------------------------------------------
@pytest.fixture
def tree(program):
    """tmp/  Pong/ (Main.vm, Ball.vm)   Empty/   solo.vm"""
    root = program[0].parent.parent
    (root / "Empty").mkdir()
    (root / "solo.vm").write_text("function Solo.f 0\npush constant 0\nreturn\n")
    return root


def select(state, name):
    state.selected = next(i for i, e in enumerate(state.entries) if e.path.name == name)


def test_picker_ctrl_u_decompiles_the_selection(tree):
    from jackvm.file_picker import PickerState

    state = PickerState(tree)
    select(state, "Pong")
    assert [f.name for f in state.decompile_targets()] == ["Ball.vm", "Main.vm"]
    select(state, "solo.vm")
    assert state.decompile_targets() == [tree / "solo.vm"]
    select(state, "Empty")
    assert state.decompile_targets() is None and "no .vm files to decompile" in state.message
    state.open_folder(tree / "Pong")
    state.selected = 0  # the ".." row: the folder we're in
    assert state.entries[0].kind == "parent"
    assert [f.name for f in state.decompile_targets()] == ["Ball.vm", "Main.vm"]


def picker_with(tree, **options):
    from jackvm.file_picker import FilePicker

    pygame.init()
    return FilePicker(pygame.display.set_mode((800, 560)), tree, **options)


def test_picker_ctrl_u_opens_the_decompiler_and_says_so(tree, fake):
    picker = picker_with(tree, open_in_decompiler=Decompiler(lambda: fake).open)
    select(picker.state, "Pong")
    event = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_u, mod=pygame.KMOD_CTRL, unicode="")
    assert picker._handle_event(event) is None  # the picker stays open
    assert picker.state.message == "Opened Pong/ in the Jack decompiler"
    assert wait_for(tree / "Pong" / "opened.txt")
    select(picker.state, "Empty")
    assert picker._handle_event(event) is None and "no .vm files" in picker.state.message
    pygame.quit()


@pytest.mark.parametrize("options, hint", [
    ({}, None),
    ({"open_in_decompiler": lambda files: ""}, "Ctrl+U: decompile"),
    ({"offer_find_decompiler": True}, "Ctrl+U: find the decompiler"),
    ({"offer_find_decompiler": True, "back_to": "space-invaders/", "compiler_folder": Path("."), "open_in_compiler": lambda f: ""}, None),
])  # fmt: skip
def test_picker_footer_mentions_ctrl_u_and_still_fits(tree, options, hint):
    picker = picker_with(tree, **options)
    footer = picker._footer(800 - 2 * picker.MARGIN)
    assert picker.small.size(footer)[0] <= 800 - 2 * picker.MARGIN
    if hint:
        assert hint in footer
    elif not options:
        assert "Ctrl+U" not in footer
    pygame.quit()


def test_picker_ctrl_u_finds_the_decompiler_then_opens_the_selection(tree, fake, monkeypatch):
    import jackvm.decompiler_link as decompiler_link
    from jackvm.file_picker import CANCEL, FIND_DECOMPILER, FilePicker
    from jackvm.locate_app import FOUND
    from jackvm.player import choose_program

    monkeypatch.delenv("JACKDECOMP")
    found = {}

    def fake_locate(surface, app):
        found["app"] = fake
        return FOUND, fake, "Found Jack decompiler"

    seen = []

    def fake_run(self):
        seen.append((self.offer_find_decompiler, self.open_in_decompiler is not None, self.state.message))
        if len(seen) == 1:
            select(self.state, "Pong")
            return FIND_DECOMPILER, self.state.decompile_targets()
        return CANCEL, None

    monkeypatch.setattr(decompiler_link, "locate", fake_locate)
    monkeypatch.setattr(FilePicker, "run", fake_run)
    pygame.init()
    surface = pygame.display.set_mode((800, 560))
    decompiler = Decompiler(lambda: found.get("app"))
    assert choose_program(surface, VirtualMachine(), tree, decompiler=decompiler) == (CANCEL, None)
    assert seen[0][:2] == (True, False)  # first: "Ctrl+U: find the decompiler"
    assert seen[1] == (False, True, "Opened Pong/ in the Jack decompiler")  # then: found, and opened
    assert wait_for(tree / "Pong" / "opened.txt")
    pygame.quit()


def test_picker_ctrl_q_in_the_decompiler_chooser_quits(tree, monkeypatch):
    import jackvm.decompiler_link as decompiler_link
    from jackvm.file_picker import FIND_DECOMPILER, QUIT, FilePicker
    from jackvm.locate_app import QUIT as LOCATE_QUIT
    from jackvm.player import choose_program

    monkeypatch.delenv("JACKDECOMP")
    monkeypatch.setattr(decompiler_link, "locate", lambda surface, app: (LOCATE_QUIT, None, ""))
    monkeypatch.setattr(FilePicker, "run", lambda self: (FIND_DECOMPILER, None))
    pygame.init()
    surface = pygame.display.set_mode((800, 560))
    assert choose_program(surface, VirtualMachine(), tree, decompiler=Decompiler(lambda: None)) == (QUIT, None)
    pygame.quit()


def test_ctrl_o_passes_the_players_decompiler_to_the_picker(fake, program, monkeypatch):
    import jackvm.player as player_module
    from jackvm.file_picker import CANCEL

    decompiler = Decompiler(lambda: fake)
    seen = {}

    def fake_choose(*args, **kwargs):
        seen.update(kwargs)
        return CANCEL, None

    monkeypatch.setattr(player_module, "choose_program", fake_choose)
    p = make_player(program, decompiler)
    ctrl(pygame.K_o)
    assert p._handle_events()
    assert seen["decompiler"] is decompiler
    pygame.quit()
