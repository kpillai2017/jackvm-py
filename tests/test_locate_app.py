"""
Tests for setting up the companion app from a folder: running a checkout
from its source, saving the config file (integrations.py), and the "where
is it?" folder chooser (locate_app.py). The same tests live in both
repositories, like the two shared files they test.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jackvm import integrations  # noqa: E402
from jackvm.integrations import (  # noqa: E402
    JACKC,
    JACKC_GUI,
    JACKVM,
    can_configure,
    check_folder,
    find,
    read_config,
    save_setting,
    source_command,
    start_folder_for,
)
from jackvm.locate_app import CANCEL, FOUND, QUIT, LocateState, config_key_for  # noqa: E402

FAKE_MAIN = """
import sys
from pathlib import Path

def main():
    Path(sys.argv[-1]).write_text(" ".join([Path(sys.argv[0]).name, *sys.argv[1:-1]]))
    return 0
"""


def make_checkout(folder: Path, package: str, with_python: bool = True) -> Path:
    """A checkout of `package` with a .venv whose python is this one - but no installed command."""
    (folder / package).mkdir(parents=True)
    (folder / package / "__init__.py").write_text("")
    (folder / package / "main.py").write_text(FAKE_MAIN)
    if with_python:
        bin_dir = folder / ".venv" / ("Scripts" if os.name == "nt" else "bin")
        bin_dir.mkdir(parents=True)
        os.symlink(sys.executable, bin_dir / ("python.exe" if os.name == "nt" else "python"))
    return folder


def config_env(tmp_path, **settings):
    path = tmp_path / "jack-tools" / "config.ini"
    environ = {"JACK_TOOLS_CONFIG": str(path)}
    if settings:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[apps]\n" + "".join(f"{k} = {v}\n" for k, v in settings.items()))
    return environ, path


def make_installed(folder: Path, name: str) -> Path:
    bin_dir = folder / ".venv" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    command = bin_dir / name
    command.write_text("#!/bin/sh\n")
    command.chmod(0o755)
    return command


# --- running a checkout from its source ------------------------------------------------
@pytest.mark.skipif(os.name == "nt", reason="symlinking python.exe isn't allowed on Windows runners")
def test_a_checkout_without_an_installed_command_runs_from_its_source(tmp_path):
    from dataclasses import replace

    app = replace(JACKVM, entry="fakevm.main:main")  # (the real jackvm needs pygame)
    checkout = make_checkout(tmp_path / "jackvm-py", "fakevm")
    command = source_command(checkout, app)
    assert command is not None and command[0].endswith("python")
    out = tmp_path / "ran.txt"
    subprocess.run([*command, "Pong/", str(out)], check=True, timeout=60)
    assert out.read_text() == "jackvm Pong/"  # sys.argv[0] is the app's name


def test_source_command_needs_the_package_and_a_python(tmp_path):
    assert source_command(tmp_path, JACKVM) is None  # no jackvm/ package here
    bare = make_checkout(tmp_path / "bare", "jackvm", with_python=False)
    assert source_command(bare, JACKVM) is None  # no virtual environment to run it with


@pytest.mark.skipif(os.name == "nt", reason="POSIX executables")
def test_check_folder_prefers_the_installed_command(tmp_path):
    command = make_installed(tmp_path, "jackvm")
    found = check_folder(JACKVM, tmp_path)
    assert found is not None and found.command == [str(command)]
    assert check_folder(JACKVM, tmp_path / "missing") is None
    assert check_folder(JACKC, tmp_path) is None


# --- the config file ----------------------------------------------------------------
def test_save_setting_creates_the_file(tmp_path):
    environ, path = config_env(tmp_path)
    assert save_setting("jackvm", "/code/jackvm-py", environ) == path
    assert read_config(path) == {"jackvm": "/code/jackvm-py"}


def test_save_setting_keeps_comments_and_other_settings(tmp_path):
    environ, path = config_env(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("# my tools\n[other]\njackvm = keep\n\n[apps]\n; the compiler\njackc = /old\nJackVM = /old-vm\n")
    save_setting("jackvm", "/new-vm", environ)
    save_setting("jackc", "/new", environ)
    text = path.read_text()
    assert "# my tools" in text and "; the compiler" in text and "[other]\njackvm = keep" in text
    assert read_config(path) == {"jackc": "/new", "jackvm": "/new-vm"}


def test_save_setting_adds_the_section_to_an_existing_file(tmp_path):
    environ, path = config_env(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text("[other]\nx = 1")
    save_setting("jackc", "/c", environ)
    assert path.read_text() == "[other]\nx = 1\n\n[apps]\njackc = /c\n"


def test_save_setting_without_a_home_folder():
    with pytest.raises(OSError):
        save_setting("jackvm", "/x", {})


def test_can_configure(tmp_path):
    environ, _ = config_env(tmp_path)
    assert can_configure(JACKVM, environ)
    assert not can_configure(JACKVM, {**environ, "JACKVM": "/some/jackvm"})  # the variable wins anyway
    assert not can_configure(JACKVM, {**environ, "JACKVM": "off"})
    off, _ = config_env(tmp_path, jackvm="off")
    assert not can_configure(JACKVM, off) and can_configure(JACKC, off)
    assert not can_configure(JACKVM, {})  # nowhere to save it


@pytest.mark.skipif(os.name == "nt", reason="POSIX executables")
def test_a_saved_folder_is_found_from_then_on(tmp_path):
    make_installed(tmp_path / "jack-compiler", "jackc")
    make_installed(tmp_path / "jack-compiler", "jackc-gui")
    environ, path = config_env(tmp_path)
    save_setting(config_key_for(JACKC_GUI), str(tmp_path / "jack-compiler"), environ)
    assert read_config(path) == {"jackc": str(tmp_path / "jack-compiler")}  # one key finds both
    for app in (JACKC, JACKC_GUI):
        found = find(app, environ, entry_points=[], which=lambda _name: None)
        assert found is not None and found.found_by.startswith("config file")


def test_the_chooser_starts_next_to_this_checkout():
    assert start_folder_for(JACKVM) == Path(integrations.__file__).resolve().parent.parent.parent


# --- the chooser's logic -----------------------------------------------------------------
def fake_check(app, folder):
    return "found" if (folder / "has-it").exists() else None


@pytest.fixture
def code_folder(tmp_path):
    for name in ("alpha", JACKVM.repo, "zeta", ".hidden"):
        (tmp_path / name).mkdir()
    (tmp_path / JACKVM.repo / "has-it").write_text("")
    (tmp_path / "notes.txt").write_text("")
    return tmp_path


def test_rows_show_folders_and_which_have_the_app(code_folder):
    state = LocateState(JACKVM, code_folder, fake_check)
    assert [(p.name, ok) for p, ok in state.entries[1:]] == [("alpha", False), ("jackvm-py", True), ("zeta", False)]
    assert state.is_parent_row(0)
    assert state.entries[state.selected][0].name == "jackvm-py"  # the usual name is selected


def test_use_a_folder_or_get_told_why_not(code_folder):
    state = LocateState(JACKVM, code_folder, fake_check)
    assert state.use() is None and "No jackvm in" in state.message and state.chosen is None
    assert state.use_selected() == "found" and state.chosen == (code_folder / "jackvm-py").resolve()
    state.activate()  # open jackvm-py/
    assert state.directory.name == "jackvm-py" and state.use() == "found"
    state.go_up()
    assert state.entries[state.selected][0].name == "jackvm-py"


def test_navigation(code_folder):
    state = LocateState(JACKVM, code_folder, fake_check)
    state.move(-10)
    state.activate()  # the ".." row
    assert state.directory == code_folder.resolve().parent
    state.open_folder(code_folder / "missing")  # unreadable: just empty
    assert state.entries[1:] == []


# --- the chooser's window ------------------------------------------------------------
pygame = pytest.importorskip("pygame")


@pytest.fixture
def chooser(code_folder, tmp_path):
    from jackvm.locate_app import FolderChooser

    pygame.init()
    surface = pygame.display.set_mode((820, 560))
    environ, path = config_env(tmp_path)
    found = FolderChooser(surface, JACKVM, code_folder, environ, check=fake_check)
    found.config_file = path
    yield found
    pygame.quit()


def key(k, mod=0):
    return pygame.event.Event(pygame.KEYDOWN, key=k, mod=mod, unicode="")


def test_ctrl_enter_uses_the_selected_folder_and_saves_it(chooser):
    chooser.draw()
    assert chooser._handle_event(key(pygame.K_RETURN, pygame.KMOD_CTRL)) == (FOUND, "found")
    assert read_config(chooser.config_file) == {"jackvm": str(chooser.state.chosen)}
    assert chooser.saved_to == chooser.config_file


def test_clicking_use_on_a_row(chooser):
    chooser.draw()
    row = next(r for r in chooser._row_rects if r[2] is not None)
    event = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=row[2].center)
    assert chooser._handle_event(event) == (FOUND, "found")


def test_a_folder_without_the_app_keeps_the_chooser_open(chooser):
    chooser.draw()
    click = pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=chooser._use_button.center)
    assert chooser._handle_event(click) is None and "No jackvm" in chooser.state.message
    chooser.draw()  # the message fits (it's cut if it must be)


def test_esc_goes_back_and_ctrl_q_quits(chooser):
    chooser._esc_needs_release = True  # opened by a held Esc: ignore its repeats
    assert chooser._handle_event(key(pygame.K_ESCAPE)) is None
    chooser._handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_ESCAPE, mod=0))
    assert chooser._handle_event(key(pygame.K_ESCAPE)) == (CANCEL, None)
    assert chooser._handle_event(key(pygame.K_q, pygame.KMOD_CTRL)) == (QUIT, None)
    assert chooser._handle_event(pygame.event.Event(pygame.QUIT)) == (QUIT, None)


def test_keys_move_and_open(chooser):
    chooser.draw()
    chooser._handle_event(key(pygame.K_HOME))
    assert chooser.state.selected == 0
    chooser._handle_event(key(pygame.K_DOWN))
    chooser._handle_event(key(pygame.K_RIGHT))  # open alpha/
    assert chooser.state.directory.name == "alpha"
    chooser._handle_event(key(pygame.K_BACKSPACE))
    assert chooser.state.entries[chooser.state.selected][0].name == "alpha"
    chooser.draw()


def test_the_footer_fits(chooser):
    for width in (300, 500, 800):
        assert chooser.small.size(chooser.footer(width))[0] <= width or len(chooser.footer(width).split("   ")) == 2


def test_comments_can_end_a_line_in_the_config_file(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text("[apps]\njackvm = ~/code/jackvm-py   ; my checkout\njackc = /c#sharp/jack-compiler  # here\n")
    assert read_config(path) == {"jackvm": "~/code/jackvm-py", "jackc": "/c#sharp/jack-compiler"}


# --- config.example.ini (the template, shared by both repositories) ---------------------
TEMPLATE = ROOT / "config.example.ini"


def test_the_template_changes_nothing_until_you_edit_it(tmp_path):
    environ, path = config_env(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    assert read_config(path) == {}  # every example is commented out
    assert can_configure(JACKVM, environ)


def test_the_template_documents_every_app():
    text = TEMPLATE.read_text(encoding="utf-8")
    assert "[apps]" in text
    for app in (JACKVM, JACKC, JACKC_GUI):
        assert f"; {app.executable} = " in text


def test_each_example_in_the_template_works_once_uncommented(tmp_path):
    examples = [line[2:] for line in TEMPLATE.read_text(encoding="utf-8").splitlines() if line.startswith("; ")]
    assert len(examples) >= 6
    path = tmp_path / "config.ini"
    for example in examples:
        path.write_text(f"[apps]\n{example}\n", encoding="utf-8")
        key, _, value = example.partition(" = ")
        assert read_config(path) == {key: value}


def test_the_chooser_can_save_into_a_copy_of_the_template(tmp_path):
    environ, path = config_env(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(TEMPLATE.read_text(encoding="utf-8"), encoding="utf-8")
    save_setting("jackvm", "/code/jackvm-py", environ)
    assert read_config(path) == {"jackvm": "/code/jackvm-py"}
    assert "; jackvm = ~/code/jackvm-py" in path.read_text()  # the examples are kept


def test_a_new_config_file_points_to_the_template(tmp_path):
    environ, path = config_env(tmp_path)
    save_setting("jackc", "/c", environ)
    assert path.read_text().startswith("# jack-tools config") and "config.example.ini" in path.read_text()
    assert path.read_text().endswith("\n[apps]\njackc = /c\n")
