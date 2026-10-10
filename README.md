# JackVM-py 🐍

A **Jack Virtual Machine** written in plain, heavily commented Python, built for
learning. It is a port of [jackvm-rs](https://github.com/jcon/jackvm-rs), which
does the same job in Rust + WebAssembly in the browser.

It runs the `.vm` programs you produce in the
[nand2tetris](https://www.nand2tetris.org) course (*The Elements of Computing
Systems*): Pong, Space Invaders, your own Jack games. It shows them in a
desktop window and has a **live memory debugger** beside it.

🛠️ **Companion project:** [jack-compiler](https://github.com/kpillai2017/jack-compiler)
compiles Jack to VM code with compiler-style error messages. Install both, and
jackvm runs `.jack` source directly. See
[Running Jack source directly](#running-jack-source-directly-with-jack-compiler).

```
╔══════════════════════════════════════════╗  ┌─ STATUS ─────────────┐
║                                          ║  │ RUNNING  pc 9338 sub │
║                                          ║  └──────────────────────┘
║        512 x 256 Hack screen             ║  ┌─ CALL STACK ─────────┐
║        (your game runs here)             ║  ┌─ REGISTERS ──────────┐
║                                          ║  │ SP LCL ARG THIS THAT │
╚══════════════════════════════════════════╝  ┌─ STACK ──────────────┐
┌─ SHORTCUTS ──────────────────────────────┐  │ ...          <- SP   │
│ Ctrl+P pause   Ctrl+N step   ...         │  └──────────────────────┘
└──────────────────────────────────────────┘
```

The game screen has a frame around it, and the shortcuts are listed just
below it. The debugger on the right is a column of boxes. If the program
crashes, an **ERROR** box appears with the message. The window is always
sized so that box fits.

---

## 1. What you need

| Tool | Version | Check with |
|------|---------|-----------|
| Python | 3.9 or newer | `python3 --version` |
| pip | any recent | `python3 -m pip --version` |

That's it. The only libraries are **pygame** (window + keyboard) and **pytest**
(tests).

> **New to Python on a Mac?** `python3` is usually already installed. If not,
> install it from [python.org](https://www.python.org/downloads/) or with
> Homebrew: `brew install python`.

---

## 2. Install

Get the code. Either clone the repository with git, or download it as a ZIP
from GitHub (green **Code** button, then **Download ZIP**) and unzip it:

```bash
git clone https://github.com/kpillai2017/jackvm-py.git
cd jackvm-py
```

Then open a terminal **in this folder** (`jackvm-py`) and run:

```bash
# 1. (Recommended) create a "virtual environment": a private copy of Python
#    for this project, so its libraries don't clash with anything else.
python3 -m venv .venv

# 2. Switch it on. You need to do this again each time you open a new terminal.
source .venv/bin/activate          # macOS / Linux
# .venv\Scripts\activate           # Windows (PowerShell / cmd)

# 3. Update pip (a new environment can come with an old one), then install
#    the libraries.
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

Your prompt now starts with `(.venv)`. Type `deactivate` to switch it off.

---

## 3. Run a game

### The easy way: choose it in a window

```bash
python3 -m jackvm
```

`-m jackvm` means "run the `jackvm` package". With no program named, a file
browser opens in the `games/` folder:

```
Choose a .vm file, or a folder of .vm files
.../jackvm-py/games
 <-  ..  (parent folder)
 [+] average/                                   [play 9 files]
 [+] pong/                                      [play 4 files]
 [+] space-invaders/                           [play 12 files]
 ...
 [ Play this folder ]  [ Quit ]
```

You can play **either** of these:

* **A folder of `.vm` files.** Click **`[play N files]`** next to a folder,
  or open the folder and click **Play this folder**. A Jack program is
  usually one `.vm` file per class. For example, `games/pong/` holds
  `Main.vm`, `Ball.vm`, `Bat.vm` and `PongGame.vm`, and all of them run
  together.
* **A single `.vm` file.** Click it.

| In the picker | Action |
|---|---|
| Click, or Enter | open a folder / play a `.vm` file |
| `[play N files]`, or Ctrl+Enter | play all `.vm` files in that folder |
| Backspace or ← | go up to the parent folder |
| ↑ ↓ PgUp PgDn, mouse wheel | move through the list |
| Esc / Quit | quit. When you came here from a program (Esc or Ctrl+O), the button reads **Back**, and Esc returns to that program |
| Ctrl+Q | quit |
| Ctrl+J | without jack-compiler: find it ([how](#running-jack-source-directly-with-jack-compiler)); after a failed compile: open the code in its window |

If the files you choose contain a mistake, the picker stays open and shows
the problem (with its line number) in red at the top.

While a game is running, press **Ctrl+O** to open the picker again and
switch to another program. Use `--gui` to open the picker in a folder of
your choice: `python3 -m jackvm --gui ~/nand2tetris/projects`.

### The quick way: name it on the command line

```bash
python3 -m jackvm pong                     # a bundled game, by name
python3 -m jackvm games/space-invaders     # a folder of .vm files
python3 -m jackvm ~/nand2tetris/projects/11/Pong/   # any folder
python3 -m jackvm games/hello-world/Main.vm         # a single .vm file
python3 -m jackvm Main.vm Ball.vm Bat.vm   # several files
```

Bundled games (see [games/README.md](games/README.md) for controls). Each one
is a folder in `games/`: `pong`, `space-invaders`, `square-game`,
`hello-world`, `average`.

### Player shortcuts

Hold **Ctrl** (or **Cmd ⌘** on a Mac) so the game doesn't receive the key:

| Shortcut | Action |
|----------|--------|
| Ctrl+P | pause / resume |
| Ctrl+N | run **one** instruction (step), handy when paused |
| Ctrl+R | restart the program |
| Ctrl+D | show / hide the debugger panel |
| Ctrl+O | open another program (the file picker) |
| Ctrl+J | open the program's `.jack` sources in [jack-compiler](https://github.com/kpillai2017/jack-compiler)'s window (the first time, it asks where jack-compiler is) |
| Ctrl+U | open the program's `.vm` files in [jack-decompiler](https://github.com/kpillai2017/jack-decompiler)'s window, which turns them back into Jack source ([details](#decompiling-vm-code-with-jack-decompiler)) |
| **Hold** Esc for 1 s | go back to the file picker (a bar shows the countdown; let go to cancel) |
| Esc, once the program has finished | go back to the file picker straight away |
| Ctrl+Q | quit (closing the window works too) |

In the file picker you can choose another program, or press Esc (or
**Back**) to return to the one you were playing.

#### Why do I have to *hold* Esc?

Some games use Esc themselves. Pong, for example, ends the game when you
press it. So while a program is running, Esc always goes to the game, and a
quick tap never leaves it. If you keep holding it, a "Keep holding Esc to go
back..." bar fills up over one second and then the file picker opens.

Once the program has **finished** (status HALTED) or **crashed** (status
ERROR), the game can't read the keyboard any more. Then a single Esc press
goes back, and a banner on the screen tells you so.

### Useful options

```bash
python3 -m jackvm --help                 # list every option
python3 -m jackvm pong --scale 3         # bigger window
python3 -m jackvm pong --no-debugger     # just the game
python3 -m jackvm pong --paused          # start paused, then Ctrl+N to step
python3 -m jackvm pong --watch 8000:8005 # show memory 8000..8005 in the debugger
python3 -m jackvm pong --on-colour '#33ff33' --off-colour '#002200'   # retro green
python3 -m jackvm pong --ticks-per-frame 40000   # fixed speed, like the original
```

### No window? Use headless mode

This runs the VM in the terminal and prints the screen as text. It's useful
for quick checks or for machines without a display:

```bash
python3 -m jackvm hello-world --headless --ticks 1000000
```

---

## 4. Run the tests

```bash
python3 -m pytest           # all 139 tests, takes a few seconds
python3 -m pytest -v        # list every test by name
python3 -m pytest tests/test_vm.py -k neg    # just the tests with "neg" in the name
```

No window opens while the tests run: `tests/conftest.py` gives pygame a
pretend screen. On GitHub the same tests run automatically after every push,
on Linux, macOS and Windows (see the **Actions** tab).

The tests are a good way to learn what each instruction does. Many of them
were ported straight from the Rust project. Those use the expected values from
the official nand2tetris test scripts.

---

## 5. Running your own nand2tetris programs

1. Write your Jack program (e.g. `projects/09/MyGame/*.jack`).
2. Compile it to `.vm` files with the course's compiler:
   ```bash
   tools/JackCompiler.sh projects/09/MyGame      # Windows: JackCompiler.bat
   ```
   (Or use the compiler you built in project 11, or
   [jack-compiler](https://github.com/kpillai2017/jack-compiler). With
   jack-compiler you can skip this step: see below.)
3. Run the folder:
   ```bash
   python3 -m jackvm projects/09/MyGame
   ```
   Or run `python3 -m jackvm`, browse to `MyGame/` in the picker and click
   `[play N files]`.

You **don't** need to include the OS `.vm` files. If your program has
`Main.main` but no `Sys.init`, the built-in Jack OS (`jackvm/os/JackOS.vm`)
is added automatically. If you write your *own* OS class (e.g. your project
12 `Math.vm`), yours is used instead of the built-in one.

### Running Jack source directly (with jack-compiler)

[**jack-compiler**](https://github.com/kpillai2017/jack-compiler) is a
companion project in its own repository: a Jack-to-VM compiler with
compiler-style error messages and its own window (`jackc-gui`). If it's
installed too, you can skip step 2 and run the **Jack source** itself:

```bash
python3 -m jackvm projects/09/MyGame          # compiles the .jack files, then runs them
python3 -m jackvm projects/09/MyGame/Main.jack   # one file means its whole folder
```

- The picker lists `.jack` files and offers `[compile+play N .jack]` for
  folders. When a folder has both, the `.jack` files win, because they're
  the ones you've been editing.
- The `.vm` output goes into a temporary folder, so your project folder
  isn't changed.
- If the code has a mistake, the compiler's message is shown (for example
  `Main.jack:3:7: error: 'x' is not declared`), and **Ctrl+J** opens the
  folder in `jackc-gui`, which marks each mistake in the code.
- While a program runs, **Ctrl+J** opens its sources in `jackc-gui`. There,
  **Ctrl+J** runs them back here.

Set it up once, side by side:

```bash
git clone https://github.com/kpillai2017/jackvm-py.git
git clone https://github.com/kpillai2017/jack-compiler.git
python3 -m venv .venv && source .venv/bin/activate
pip install -e ./jackvm-py -e "./jack-compiler[gui]"   # one environment: found automatically
```

Each app finds the other like this (the first match wins; see
[`jackvm/integrations.py`](jackvm/integrations.py)):

1. **An environment variable**: `JACKC` / `JACKC_GUI` (and `JACKVM` for the
   other direction), e.g. `JACKC="/path/to/jack-compiler/.venv/bin/jackc"`.
   Set it to `off` to switch the integration off.
2. **The config file** shared by both apps, so they find each other from any
   folder and any environment:

   ```ini
   # ~/.config/jack-tools/config.ini   (Windows: %APPDATA%\jack-tools\config.ini)
   [apps]
   jackc = ~/code/jack-compiler       ; a folder: its bin/, .venv, venv, env or .direnv/* is searched
   jackvm = ~/code/jackvm-py          ; for the compiler's Ctrl+J
   # jackc-gui = /full/path/to/jackc-gui   ; or give a command (found next to jackc otherwise)
   # jackc = off                           ; switch it off
   ```

   A value is either the project's folder (the app installed in a virtual
   environment inside it, or just its requirements: then its source is run
   with that environment's Python) or the full path of the command. The file
   follows `XDG_CONFIG_HOME`, and `JACK_TOOLS_CONFIG=/some/file.ini` points
   to a different one.

   [`config.example.ini`](config.example.ini) is a commented template with
   every setting. Copy it into place and uncomment the lines you need:

   ```bash
   mkdir -p ~/.config/jack-tools && cp config.example.ini ~/.config/jack-tools/config.ini
   ```
3. **The same Python environment**: both packages register themselves in
   the `jack_tools` entry-point group, so `pip install -e` is enough.
4. **The `PATH`**: a `jackc` / `jackc-gui` command installed anywhere else.

**The easiest way to set it up:** without the compiler, everything works as
before, and the shortcuts box shows `Ctrl+J find compiler...`. Press it (or
**Ctrl+J** in the file picker), open your `jack-compiler` folder in the chooser
(folders where it can run are marked `[use]`), and press **Use this folder**.
That saves `jackc = <the folder>` in the config file, and from then on both apps
find each other from any folder. If the lookup is switched off (`JACKC=off`, or
`off` in the config file), the shortcut reads `Ctrl+J compiler (not installed)`.
The two apps only run each other's commands and never import each other's code.

### Decompiling VM code (with jack-decompiler)

[jack-decompiler](https://github.com/kpillai2017/jack-decompiler) turns `.vm`
files back into readable Jack source. When it's installed, **Ctrl+U**
("un-compile") opens the running program in its window. It's found the same
four ways as the compiler (`jackvm/decompiler_link.py`):

1. `JACKDECOMP="python3 -m jack_decompiler"` (or `JACKDECOMP=off`)
2. `jackdecomp = ~/code/jack-decompiler` under `[apps]` in the config file
3. `pip install -e ../jack-decompiler` into the same environment
4. a `jackdecomp` command on the `PATH`

Until it's found, the shortcuts box shows `Ctrl+U find decompiler...`: press
it, open your `jack-decompiler` folder and press **Use this folder**.

**Ctrl+U works in the file picker too**, without running anything: it opens
the selected `.vm` file, or all the `.vm` files of the selected folder (on the
`..` row: the folder you're in), in the decompiler.

---

## 6. How the code is organised

Each file does one job and starts with a long explanation. Read them in this
order (more detail in **[LEARNING_GUIDE.md](LEARNING_GUIDE.md)**):

```
jackvm-py/
├── jackvm/
│   ├── memory_map.py  ① the memory layout (SP, LCL, screen, keyboard, ...)
│   ├── commands.py    ② the 9 kinds of VM instruction
│   ├── parser.py      ③ .vm text  → command objects + address book
│   ├── vm.py          ④ the VM: fetch, advance, execute  ★ the heart
│   ├── jack_os.py     ⑤ glues the Jack OS onto your program
│   ├── os/JackOS.vm      the Jack OS itself (compiled VM code)
│   ├── screen.py      ⑥ screen memory → pixels
│   ├── keyboard.py    ⑦ key presses   → keyboard memory
│   ├── debugger.py    ⑧ the live register/stack panel
│   ├── player.py      ⑨ the pygame window and main loop
│   ├── program_files.py ⑩ finding .vm files (file, folder or game name)
│   ├── file_picker.py ⑪ the "choose a program" browser (GUI)
│   ├── main.py        ⑫ the command line (python -m jackvm ...)
│   ├── jack_sources.py   run .jack source by calling jack-compiler first
│   ├── integrations.py   find jack-compiler (shared with that repository)
│   ├── decompiler_link.py Ctrl+U: open the program in jack-decompiler
│   └── locate_app.py     "where is it?" folder chooser for Ctrl+J (shared too)
├── games/             ready-to-run programs, one folder per game
│   └── pong/          Main.vm, Ball.vm, Bat.vm, PongGame.vm (one per class)
├── tests/             pytest tests (+ fixtures/ for long test programs)
│   └── conftest.py    shared set-up: no real window or sound during tests
├── .github/workflows/ GitHub runs the tests on every push (tests.yml)
├── LEARNING_GUIDE.md  a guided tour with exercises
├── requirements.txt   libraries to install
├── config.example.ini template for ~/.config/jack-tools/config.ini (finding jack-compiler)
├── pyproject.toml     project + pytest settings
└── LICENSE            MIT (keeps the original jackvm-rs copyright notice)
```

How the pieces connect:

```
  .vm text ──► parser ──► commands + addresses ──► jack_os (adds OS) ──► VirtualMachine
                                                                          │   ▲
                                         screen.py ◄── memory[16384..] ───┘   │
                                         debugger.py ◄── registers/stack      │
                                         keyboard.py ──► memory[24576] ───────┘
                                                 ▲
                                    player.py (pygame window, 60 frames/s)
                                                 ▲
                   file_picker.py (choose a file/folder) ──► program_files.py ──► .vm text
```

---

## 7. Differences from jackvm-rs

| | jackvm-rs | jackvm-py |
|---|---|---|
| Runs in | the browser (WebAssembly) | a desktop window (pygame) |
| Speed | 40,000 instructions per frame | about 2 million instructions/s (similar) |
| Debugger | registers + stack cells 256–267 | registers, TEMP, top of stack, call stack, PC + next instruction, watched addresses, single-step |
| Keyboard | last key only; released key → 0 | remembers held keys (release one, the other still counts) |
| Loading | one `.vm` text, built into the page | a file picker (file or folder), or files / folders / a game name on the command line; Ctrl+O switches program |
| Errors | Rust panic | clear messages with line numbers; `Sys.error` codes explained |
| Extras | | `--headless` text mode, colour options |

Two small bugs in the original are fixed here. Its debugger labelled
addresses 1 and 2 as `ARG` and `LCL`; they are really `LCL` (1) and `ARG` (2).
Its key table also had no Page Down key.

---

## 8. Troubleshooting

* **`ModuleNotFoundError: No module named 'pygame'`.** Activate the virtual
  environment (`source .venv/bin/activate`) and run
  `python3 -m pip install -r requirements.txt`.
* **`jackvm: command not found`.** The `jackvm` command only exists after
  `python3 -m pip install -e .` in the active virtual environment.
  `requirements.txt` alone installs pygame but no command: use
  `python3 -m jackvm` then. A *new* environment is always empty, including
  the one direnv's `layout python` makes in an `.envrc`, so install into it
  once. `which python` should point inside it.
* **`No module named jackvm`.** Run the command from inside the `jackvm-py`
  folder, or install it with `python3 -m pip install -e .` and then just type
  `jackvm pong`. (If that says *"editable mode currently requires a
  setuptools-based build"*, your pip is too old: run
  `python3 -m pip install --upgrade pip` first.)
* **The game ignores my keys.** Click the game window first so it has focus.
  Letters are sent as upper-case (that's how Hack works).
* **The game is too fast or too slow.** Try `--ticks-per-frame 20000`
  (slower) or a larger number (faster, if your computer can keep up).

## Acknowledgements

This project would not exist without
**[jackvm-rs](https://github.com/jcon/jackvm-rs) by Jim Connell**. jackvm-py is
a port of it, and its source code was the reference throughout:

| jackvm-rs | What jackvm-py took from it |
|---|---|
| `vm/src/vm.rs`, `vm/src/compiler.rs` | how each VM instruction behaves, the call/return frame layout, and parsing `.vm` text. Re-written in Python as `vm.py` and `parser.py` |
| `vm/src/jack_os.rs` | the Jack OS, as compiled VM code. Copied unchanged into `jackvm/os/JackOS.vm` |
| `web/src/web_vm.rs` | the keyboard codes (`keyboard.py`) and how pixels are drawn (`screen.py`) |
| `jackvm-rs.github.io/src/js/memory-debugger.js` | the idea and layout of the live memory debugger (`debugger.py`) |
| `vm/tests/*.rs` | the integration tests, ported to `tests/test_integration.py`, `tests/test_os_library.py` and `tests/fixtures/` |
| `jackvm-rs.github.io/src/vms/*.vm` | the bundled programs in `games/`, split into one file per class |

Thank you, Jim, for writing such a readable VM and for releasing it under the
MIT licence.

Other people's work bundled here:

* **Jack OS, Pong, Square Game, Average and Hello World** come from the
  nand2tetris course by Noam Nisan and Shimon Schocken,
  [nand2tetris.org](https://www.nand2tetris.org/software).
* **Space Invaders** clone by Jim Connell:
  [jcon/SpaceInvaders](https://github.com/jcon/SpaceInvaders).
* Graphics and input use [pygame](https://www.pygame.org), and the tests use
  [pytest](https://pytest.org).

## Licence

MIT, the same as jackvm-rs. See [LICENSE](LICENSE). It keeps the original
copyright notice (© 2020 Jim Connell), as the MIT licence requires for
derived works. The bundled `.vm` programs remain the work of their original
authors (listed above).
