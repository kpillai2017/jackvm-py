"""
test_player.py - Tests for the player window: quitting with Esc, and layout.
==========================================================================

We use SDL's "dummy" video driver (no real window appears) and a FAKE CLOCK,
so a test can "hold Esc for exactly 1 second" without actually waiting.
"""

import pytest

import pygame

from jackvm import VirtualMachine
from jackvm.debugger import build_sections
from jackvm.memory_map import KEYBOARD
from jackvm.player import (
    ESC_HOLD_SECONDS,
    FRAME_COLOUR,
    MARGIN,
    DebuggerPanel,
    Player,
)

LOOP_FOREVER = "function Sys.init 0\nlabel L\ngoto L\n"


class FakeClock:
    """Stands in for time.perf_counter(); we move time forward by hand."""

    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


@pytest.fixture
def player():
    vm = VirtualMachine()
    vm.load_source(LOOP_FOREVER)
    p = Player(vm)
    p.now = FakeClock()
    p._open_window()
    yield p
    pygame.quit()


def send(player, *events):
    """Put events in pygame's queue and let the player handle them."""
    for event in events:
        pygame.event.post(event)
    return player._handle_events()


def esc_down():
    return pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0, unicode="\x1b")


def esc_up():
    return pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0)


# --- Esc while the program is running -----------------------------------------
def test_a_quick_esc_tap_goes_to_the_game_and_does_not_quit(player):
    assert send(player, esc_down()) is True
    assert player.vm.peek(KEYBOARD) == 140  # the game sees Esc (Hack code 140)
    player.now.t += 0.2
    assert send(player, esc_up()) is True
    assert player.vm.peek(KEYBOARD) == 0
    assert player.esc_hold_progress() == 0.0
    assert not player._esc_held_long_enough()


def test_holding_esc_for_one_second_quits(player):
    send(player, esc_down())
    player.now.t += ESC_HOLD_SECONDS / 2
    assert player.esc_hold_progress() == pytest.approx(0.5)
    assert not player._esc_held_long_enough()
    assert player.vm.peek(KEYBOARD) == 140  # still passed to the game while held

    player.now.t += ESC_HOLD_SECONDS / 2
    assert player._esc_held_long_enough()


def test_letting_go_just_before_the_end_cancels(player):
    send(player, esc_down())
    player.now.t += ESC_HOLD_SECONDS * 0.95
    send(player, esc_up())
    player.now.t += 10
    assert not player._esc_held_long_enough()


def test_switching_windows_resets_the_countdown(player):
    send(player, esc_down())
    player.now.t += 0.5
    send(player, pygame.event.Event(pygame.WINDOWFOCUSLOST))
    player.now.t += 5
    assert player.esc_hold_progress() == 0.0
    assert player.vm.peek(KEYBOARD) == 0


def test_the_bar_is_drawn_while_holding(player):
    send(player, esc_down())
    player.now.t += 0.6
    player._draw()  # must not crash; the banner sits over the bottom of the screen
    banner_y = player.screen_rect.bottom - 10 - 20
    assert player.window.get_at((player.screen_rect.centerx, banner_y))[:3] != (255, 255, 255)


# --- Esc once the program has finished ------------------------------------------
def test_one_esc_press_quits_when_the_program_has_halted(player):
    player.vm.load_source("function Sys.init 0\ncall Sys.halt 0\n")
    player.vm.run(10)
    assert player.vm.is_halted()
    assert send(player, esc_down()) is False  # quit immediately


def test_one_esc_press_quits_after_a_runtime_error(player):
    player.error = "Stack underflow"
    assert send(player, esc_down()) is False


def test_ctrl_q_still_quits_and_other_keys_dont(player):
    assert send(player, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, mod=0, unicode=" ")) is True
    assert send(player, pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q, mod=pygame.KMOD_CTRL, unicode="")) is False


# --- layout and borders ---------------------------------------------------------------
def test_window_has_margins_a_framed_screen_and_the_panel(player):
    width, height = player.window.get_size()
    assert player.screen_rect.topleft == (MARGIN, MARGIN)
    assert width == MARGIN + 1024 + MARGIN + DebuggerPanel.WIDTH + MARGIN
    assert height >= MARGIN + 512 + MARGIN

    player._draw()
    # The frame is drawn just outside the screen, on every side.
    rect = player.screen_rect
    for x, y in [(rect.centerx, rect.top - 4), (rect.centerx, rect.bottom + 4), (rect.left - 4, rect.centery), (rect.right + 4, rect.centery)]:
        assert player.window.get_at((x, y))[:3] == FRAME_COLOUR, (x, y)
    # The panel's first box has a border too.
    panel_x = rect.right + MARGIN
    assert player.window.get_at((panel_x, MARGIN + 40))[:3] == DebuggerPanel.BORDER


def test_hiding_the_debugger_shrinks_the_window(player):
    player._handle_shortcut(pygame.K_d)
    # Without the debugger the window is just the framed screen plus the
    # shortcuts box underneath it.
    assert player.window.get_size() == (
        MARGIN + 1024 + MARGIN,
        player.shortcuts_rect.bottom + MARGIN,
    )
    player._draw()


def test_the_error_box_fits_even_with_a_small_screen():
    # At scale 1 the game screen is short, so the debugger column decides the
    # window height. A crash adds an ERROR box: everything must still fit.
    vm = VirtualMachine()
    vm.load_source("function Sys.init 0\ncall Sys.init 0\nreturn\n")  # recurses forever
    p = Player(vm, scale=1, watch=[8000, 8001])
    p._open_window()
    try:
        while not p.error:
            p._run_vm_for_one_frame()
        sections = build_sections(vm, p._status(), 0.0, p.watch, p.error)
        assert sections[1].title == "ERROR"
        panel_bottom = MARGIN + p.panel.required_height(sections)
        assert panel_bottom + MARGIN <= p.window.get_size()[1]
        p._draw()  # and drawing a VM whose SP ran off the end doesn't crash
    finally:
        pygame.quit()
