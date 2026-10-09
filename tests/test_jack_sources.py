"""
test_jack_sources.py - Running .jack source through the Jack compiler.
=====================================================================

The real compiler lives in another repository (jack-compiler), so these
tests use a tiny FAKE `jackc`: a Python script that turns each Main.jack
into a Main.vm - or, if the file contains the word BROKEN, prints an error
the way the real compiler does and exits with code 1.
"""

import subprocess
import sys
from types import SimpleNamespace

import pygame
import pytest

from jackvm import VirtualMachine, __version__
from jackvm.file_picker import PickerState, list_entries
from jackvm.integrations import JACKC, JACKC_GUI, JACKVM, Companion, find, not_found_message
from jackvm.jack_sources import JackCompileError, JackTools, describe_program, source_folder_for
from jackvm.main import main
from jackvm.player import Player

FAKE_JACKC = """
import pathlib, sys
folder, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[3])
failed = False
for jack in sorted(folder.glob('*.jack')):
    if 'BROKEN' in jack.read_text():
        print(f"{jack}:3:7: error: 'x' is not declared")
        print('   = help: declare it with var')
        failed = True
    else:
        name = jack.stem
        (out / f'{name}.vm').write_text(f'function {name}.main 0\\npush constant 0\\nreturn\\n')
sys.exit(1 if failed else 0)
"""

FAKE_GUI = """
import pathlib, sys
pathlib.Path(sys.argv[1], 'opened.txt').write_text('yes')
"""

GOOD = "class Main { function void main() { return; } }\n"


def script(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text)
    return [sys.executable, str(path)]


@pytest.fixture
def tools(tmp_path):
    """JackTools with the fake jackc and a fake jackc-gui."""
    jackc = Companion(JACKC, script(tmp_path, "fake_jackc.py", FAKE_JACKC), "test")
    gui = Companion(JACKC_GUI, script(tmp_path, "fake_gui.py", FAKE_GUI), "test")
    return JackTools(lambda: jackc, lambda: gui)


@pytest.fixture
def no_compiler():
    return JackTools(lambda: None, lambda: None)


@pytest.fixture
def square(tmp_path):
    folder = tmp_path / "Square"
    folder.mkdir()
    (folder / "Main.jack").write_text(GOOD)
    (folder / "Square.jack").write_text(GOOD.replace("Main", "Square"))
    return folder


# --- finding the compiler ---------------------------------------------------------
def test_the_lookup_order_is_setting_then_same_environment_then_path():
    def on_path(name):
        return f"/opt/bin/{name}"

    assert find(JACKC, environ={"JACKC": "jackc --x"}, entry_points=[], which=on_path).command == ["jackc", "--x"]
    assert find(JACKC, environ={"JACKC": "off"}, entry_points=[], which=on_path) is None
    same_env = [SimpleNamespace(name="compiler", value="json.tool:main")]
    assert find(JACKC, environ={}, entry_points=same_env, which=on_path).found_by == "same Python environment"
    assert find(JACKC, environ={}, entry_points=[], which=on_path).command == ["/opt/bin/jackc"]
    assert find(JACKC, environ={}, entry_points=[], which=lambda n: None) is None


def test_this_vm_advertises_itself_for_the_compiler_to_find():
    found = find(JACKVM, environ={}, which=lambda n: None)
    assert found is not None and found.found_by == "same Python environment"
    done = found.run(["--version"], timeout=60)
    assert done.returncode == 0 and done.stdout.strip() == f"jackvm {__version__}"


# --- compiling before running ----------------------------------------------------
def test_a_jack_folder_is_compiled_into_a_temporary_folder(tools, square):
    files = tools.prepare([str(square)])
    assert [f.name for f in files] == ["Main.vm", "Square.vm"]
    assert files[0].parent != square and not list(square.glob("*.vm"))  # sources left alone
    assert source_folder_for(files) == square.resolve()
    assert describe_program(files) == "Square/ (compiled from .jack, 2 files)"
    one = tools.prepare([str(square / "Square.jack")])  # one file means its whole folder
    assert [f.name for f in one] == ["Main.vm", "Square.vm"]


def test_vm_files_and_games_are_not_touched(tools, tmp_path):
    (tmp_path / "Main.vm").write_text("function Main.main 0\npush constant 0\nreturn\n")
    assert tools.prepare([str(tmp_path / "Main.vm")]) == [tmp_path / "Main.vm"]
    assert tools.prepare(["pong"])[0].parent.name == "pong"
    assert source_folder_for([tmp_path / "Main.vm"]) is None  # no .jack next to it


def test_compile_errors_come_back_short_with_the_full_output(tools, square):
    (square / "Square.jack").write_text("BROKEN")
    with pytest.raises(JackCompileError) as caught:
        tools.prepare([str(square)])
    assert str(caught.value) == "Square.jack:3:7: error: 'x' is not declared"
    assert caught.value.folder == square.resolve() and "= help: declare it" in caught.value.output


def test_without_a_compiler_old_vm_files_still_play_and_jack_explains(no_compiler, square):
    with pytest.raises(FileNotFoundError) as caught:
        no_compiler.prepare([str(square)])
    assert str(caught.value).endswith(f"is Jack source code (.jack), so it needs the Jack compiler.\n{not_found_message(JACKC)}")
    (square / "Main.vm").write_text("function Main.main 0\npush constant 0\nreturn\n")
    assert [f.name for f in no_compiler.prepare([str(square)])] == ["Main.vm"]
    assert not no_compiler.can_compile


def test_ctrl_j_opens_the_sources_in_the_compiler_gui(tools, no_compiler, square):
    assert tools.open_in_compiler(square) == "Opened Square/ in the Jack compiler"
    for _ in range(100):  # the fake GUI runs in the background
        if (square / "opened.txt").exists():
            break
        subprocess.run([sys.executable, "-c", "import time; time.sleep(0.05)"])
    assert (square / "opened.txt").read_text() == "yes"
    assert tools.open_in_compiler(None) == "No .jack sources next to this program"
    assert no_compiler.open_in_compiler(square) == not_found_message(JACKC_GUI)  # (depends on the setup)


# --- the command line and the picker -----------------------------------------------
def test_the_command_line_compiles_jack_source(tmp_path, square, monkeypatch, capsys):
    monkeypatch.setenv("JACKC", " ".join(f'"{p}"' for p in script(tmp_path, "jc.py", FAKE_JACKC)))
    assert main([str(square), "--headless", "--ticks", "10"]) == 0
    assert "Compiling Square/ with the Jack compiler..." in capsys.readouterr().out
    (square / "Main.jack").write_text("BROKEN")
    assert main([str(square), "--headless"]) == 1
    assert "Main.jack:3:7: error: 'x' is not declared" in capsys.readouterr().err


def test_the_picker_lists_jack_only_when_it_can_compile(square):
    plain = [(e.kind, e.path.name, e.jack_count) for e in list_entries(square.parent)]
    assert ("folder", "Square", 0) in plain
    assert ("folder", "Square", 2) in [(e.kind, e.path.name, e.jack_count) for e in list_entries(square.parent, True)]
    state = PickerState(square, can_compile=True)
    assert [e.kind for e in state.entries[1:]] == ["jack", "jack"]
    assert state.play_current_folder() == [square.resolve()]
    assert PickerState(square).play_current_folder() is None  # can't compile: nothing to play


# --- the player ----------------------------------------------------------------------
def test_player_shows_the_shortcut_and_a_notice(tools, no_compiler, square):
    files = tools.prepare([str(square)])
    vm = VirtualMachine()
    vm.load_source("function Sys.init 0\nlabel L\ngoto L\n")
    p = Player(vm, files=files, tools=tools)
    p._open_window()
    assert p.source_folder == square.resolve()
    assert any("Ctrl+J open in compiler" in row for row, _ in p.shortcuts.rows)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, mod=pygame.KMOD_CTRL, unicode=""))
    assert p._handle_events()
    assert p._notice[0] == "Opened Square/ in the Jack compiler"
    p._draw()

    q = Player(vm, files=files, tools=no_compiler)
    q._open_window()
    assert any("Ctrl+J compiler (not installed)" in row for row, _ in q.shortcuts.rows)
    assert q.open_in_compiler() == not_found_message(JACKC_GUI)
    q._draw()  # a long notice is cut to fit
    pygame.quit()
