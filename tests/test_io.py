"""
test_io.py - Tests for the screen, keyboard, debugger and command line.
=====================================================================

These parts talk to the outside world. We test the logic WITHOUT opening a
window: the screen renderer only produces bytes, the keyboard only writes to
memory, and the debugger only produces text.
"""

import pygame
import pytest

from jackvm import VirtualMachine
from jackvm.debugger import CALL_STACK_ROWS, ERROR_MAX_ROWS, ERROR_WRAP, build_sections, wrap_error
from jackvm.keyboard import Keyboard, hack_key_code
from jackvm.main import main, parse_colour, parse_watch
from jackvm.program_files import GAMES_FOLDER, describe, list_games, read_program, resolve_paths
from jackvm.memory_map import KEYBOARD, SCREEN_START
from jackvm.screen import ScreenRenderer, pixel_is_on, to_ascii

ON, OFF = (0, 0, 0), (255, 255, 255)


# --- screen ------------------------------------------------------------------
def blank_memory():
    vm = VirtualMachine()
    return vm.memory


def test_bit_0_is_the_leftmost_pixel():
    memory = blank_memory()
    memory[SCREEN_START] = 5  # binary ...0101 -> pixels 0 and 2
    assert [pixel_is_on(memory, x, 0) for x in range(4)] == [True, False, True, False]


def test_negative_words_light_the_last_pixel():
    memory = blank_memory()
    memory[SCREEN_START + 32 + 1] = -32768  # only bit 15 set; row 1, word 1
    assert pixel_is_on(memory, 16 + 15, 1)
    assert not pixel_is_on(memory, 16 + 14, 1)


def test_fast_renderer_matches_the_simple_definition():
    memory = blank_memory()
    for i, value in enumerate([1, -1, 0x00F0, -32768, 12345]):
        memory[SCREEN_START + i * 33] = value  # spread over rows and columns
    rgb = ScreenRenderer(ON, OFF).to_rgb_bytes(memory)
    assert len(rgb) == 512 * 256 * 3
    for y in range(0, 6):
        for x in range(0, 512):
            offset = (y * 512 + x) * 3
            expected = ON if pixel_is_on(memory, x, y) else OFF
            assert tuple(rgb[offset : offset + 3]) == expected, (x, y)


def test_ascii_view():
    memory = blank_memory()
    memory[SCREEN_START] = 1
    picture = to_ascii(memory).splitlines()
    assert len(picture) == 32 and len(picture[0]) == 128
    assert picture[0][0] == "#" and picture[0][1] == "."


# --- keyboard ----------------------------------------------------------------
@pytest.mark.parametrize(
    "key, text, code",
    [
        (pygame.K_a, "a", 65),  # letters are always upper-case
        (pygame.K_a, "A", 65),
        (pygame.K_1, "1", 49),
        (pygame.K_SPACE, " ", 32),
        (pygame.K_1, "!", 33),  # shifted symbols use the typed character
        (pygame.K_RETURN, "\r", 128),
        (pygame.K_BACKSPACE, "\b", 129),
        (pygame.K_LEFT, "", 130),
        (pygame.K_UP, "", 131),
        (pygame.K_RIGHT, "", 132),
        (pygame.K_DOWN, "", 133),
        (pygame.K_ESCAPE, "\x1b", 140),
        (pygame.K_F1, "", 141),
        (pygame.K_F12, "", 152),
        (pygame.K_q, "", 81),  # no text (e.g. Alt held): still worked out
        (pygame.K_LSHIFT, "", None),  # Shift alone means nothing to Hack
    ],
)
def test_hack_key_codes(key, text, code):
    assert hack_key_code(key, text) == code


def test_keyboard_register_follows_held_keys():
    vm = VirtualMachine()
    keyboard = Keyboard(vm)
    keyboard.press(pygame.K_LEFT)
    assert vm.peek(KEYBOARD) == 130
    keyboard.press(pygame.K_SPACE, " ")
    assert vm.peek(KEYBOARD) == 32
    keyboard.release(pygame.K_SPACE)
    assert vm.peek(KEYBOARD) == 130  # back to the key still held
    keyboard.release(pygame.K_LEFT)
    assert vm.peek(KEYBOARD) == 0
    keyboard.press(pygame.K_x, "x")
    keyboard.release_all()
    assert vm.peek(KEYBOARD) == 0


# --- debugger ----------------------------------------------------------------
def section_rows(sections):
    """{section title: [row words, ...]} - easy to search in tests."""
    return {s.title: [text.split() for text, _ in s.rows] for s in sections}


def test_debugger_sections_show_registers_stack_and_watches():
    vm = VirtualMachine()
    vm.load_source("push constant 7\npush constant 8\n")
    vm.run(2)
    sections = build_sections(vm, "PAUSED", 1.5e6, watch=[8000])
    assert [s.title for s in sections] == [
        "STATUS", "CALL STACK (innermost first)", "REGISTERS", "STACK (top is nearest SP)", "WATCHED ADDRESSES",
    ]  # fmt: skip
    rows = section_rows(sections)
    assert ["PAUSED"] in rows["STATUS"]
    assert ["speed", "1.50", "M", "instructions/s"] in rows["STATUS"]
    assert ["0", "SP", "258"] in rows["REGISTERS"]  # address, name, value
    assert ["KEYBOARD", "(24576)", "0"] in rows["REGISTERS"]
    assert ["257", "8"] in rows["STACK (top is nearest SP)"]  # top of the stack
    assert ["258", "0", "<-", "SP"] in rows["STACK (top is nearest SP)"]  # next free slot
    assert ["8000", "0"] in rows["WATCHED ADDRESSES"]


def test_call_stack_box_keeps_a_fixed_height():
    # So the boxes below it don't jump up and down while a game runs.
    vm = VirtualMachine()
    [call_stack] = [s for s in build_sections(vm, "RUNNING", 0) if s.title.startswith("CALL STACK")]
    assert len(call_stack.rows) == 1  # just "(none)"...
    assert call_stack.row_count == CALL_STACK_ROWS + 1  # ...but space is reserved


def test_debugger_shows_errors_and_how_to_quit():
    vm = VirtualMachine()
    sections = build_sections(vm, "ERROR", 0, error="Stack underflow")
    assert sections[1].title == "ERROR"
    assert ("Stack underflow", "error") in sections[1].rows
    assert ["Program", "finished:", "press", "Esc", "to", "quit"] in section_rows(sections)["STATUS"]


def test_error_messages_wrap_between_words_and_are_capped():
    message = "Stack overflow: the stack ran past the end of memory in function Main.main."
    lines = wrap_error(message)
    assert " ".join(lines) == message  # nothing lost, no word split in two
    assert all(len(line) <= ERROR_WRAP for line in lines)

    huge = wrap_error("word " * 200)
    assert len(huge) == ERROR_MAX_ROWS
    assert huge[-1].endswith("...")  # shows the message was cut short


def test_debugger_survives_sp_past_the_end_of_memory():
    # After a stack overflow SP can point outside memory. The debugger must
    # still draw (that's when you need it most!), showing "----" there.
    vm = VirtualMachine()
    end = len(vm.memory)
    vm.poke(0, end + 3)
    sections = build_sections(vm, "ERROR", 0, watch=[end + 1], error="Stack overflow")
    rows = section_rows(sections)
    stack = rows["STACK (top is nearest SP)"]
    assert [str(end - 1), "0"] in stack  # the last real cell is still shown
    assert [str(end), "----"] in stack  # past the end: shown, not crashed
    assert [str(end + 1), "----"] in rows["WATCHED ADDRESSES"]


# --- command line ------------------------------------------------------------
def test_resolve_bundled_game_names_files_and_folders(tmp_path):
    # A game name finds games/<name>/ - one .vm file per Jack class.
    assert [f.name for f in resolve_paths(["pong"])] == ["Ball.vm", "Bat.vm", "Main.vm", "PongGame.vm"]
    single = resolve_paths([str(GAMES_FOLDER / "hello-world" / "Main.vm")])
    assert [f.name for f in single] == ["Main.vm"]
    (tmp_path / "B.vm").write_text("function B.f 0\n")
    (tmp_path / "A.vm").write_text("function A.f 0\n")
    files = resolve_paths([str(tmp_path)])
    assert [f.name for f in files] == ["A.vm", "B.vm"]
    assert read_program(files) == "function A.f 0\n\nfunction B.f 0\n"
    with pytest.raises(FileNotFoundError):
        resolve_paths(["no-such-game"])


def test_bundled_games_are_listed_and_described():
    assert list_games() == ["average", "hello-world", "pong", "space-invaders", "square-game"]
    assert describe(resolve_paths(["pong"])) == "pong/ (4 files)"
    assert describe(resolve_paths(["hello-world"])) == "Main.vm"


def test_headless_needs_a_program(capsys):
    with pytest.raises(SystemExit):
        main(["--headless"])
    assert "--headless needs a program" in capsys.readouterr().err


def test_option_parsers():
    assert parse_colour("#ff8800") == (255, 136, 0)
    assert parse_watch("8000") == [8000]
    assert parse_watch("10:12") == [10, 11, 12]


def test_headless_hello_world_prints_the_screen(capsys):
    assert main(["hello-world", "--headless", "--ticks", "1000000"]) == 0
    output = capsys.readouterr().out
    assert "program is halted" in output
    assert "#" in output  # something was drawn


def test_cli_reports_parse_errors(tmp_path, capsys):
    bad = tmp_path / "bad.vm"
    bad.write_text("push constant 1\nfly away\n")
    assert main([str(bad), "--headless"]) == 1
    assert "line 2: Unrecognised instruction 'fly'" in capsys.readouterr().err
