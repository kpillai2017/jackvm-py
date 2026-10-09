"""
conftest.py - shared set-up for every test.
===========================================

pytest automatically loads this file BEFORE it imports any test module, so
it's the right place for settings that must be in place before pygame starts.

SDL (the library underneath pygame) reads these environment variables when
it starts up:

* SDL_VIDEODRIVER=dummy  -> draw into memory; no real window pops up.
                            Tests still get real pixels they can check.
* SDL_AUDIODRIVER=dummy  -> no sound card needed (CI machines don't have one).

`setdefault` means: only if not already set, so you can still override
them from the shell when you want to watch a test draw, e.g.
`SDL_VIDEODRIVER=cocoa python3 -m pytest tests/test_player.py`.
"""

import os
import tempfile

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")  # skip pygame's "Hello from..." banner

# Never pick up a real Jack compiler installed on this machine: tests that
# need one pass a fake (see tests/test_jack_sources.py). "off" disables it.
os.environ["JACKC"] = "off"
os.environ["JACKC_GUI"] = "off"

# ...and never read or write the real config file (~/.config/jack-tools/config.ini):
# tests that need one make their own (see tests/test_locate_app.py).
os.environ["JACK_TOOLS_CONFIG"] = os.path.join(tempfile.gettempdir(), f"jack-tools-tests-{os.getpid()}", "config.ini")
