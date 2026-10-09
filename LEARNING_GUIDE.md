# Learning guide: how a virtual machine works

This guide walks you through the code in a sensible order. Each step says
**what to read**, **what to notice**, and gives a small **exercise**. You don't
need to know the nand2tetris course to follow it, but it helps.

Take your time. The whole VM (`vm.py`) is only about 250 lines of real code.

---

## Step 0 – Play first

```bash
python3 -m jackvm pong
```

Watch the debugger panel while you play. The numbers flying past are the VM's
memory. By the end of this guide you'll know what every one of them means.

---

## Step 1 – Memory is everything (`jackvm/memory_map.py`)

**Read:** the whole file. It's mostly constants.

**Notice:**
* The computer has **one** list of numbers (memory). Registers, variables,
  the stack, the screen and the keyboard are all just *addresses* in it.
* Every value is a 16-bit signed number (−32768 … 32767), and
  `to_int16()` makes Python numbers wrap around like real hardware.

**Exercise:** in a Python shell (`python3`), try:

```python
from jackvm.memory_map import to_int16
to_int16(32767 + 1)    # what do you get? why?
to_int16(-1 & 0xFFFF)  # 65535 as 16 bits... is -1!
```

---

## Step 2 – The instructions (`jackvm/commands.py`)

**Read:** the module docstring table, then skim the classes.

**Notice:** there are only nine kinds of instruction. Every Jack program,
including Space Invaders, is built from just these.

**Exercise:** look inside `games/hello-world/Main.vm`. Can you find each kind
of instruction? Which kind is missing? (Hint: is there a `pop` to `that`?)
Then open the bigger `games/pong/` folder. Each file is one Jack class.

---

## Step 3 – From text to objects (`jackvm/parser.py`)

**Read:** the docstring's *worked example*, then `parse_program()` and
`parse_line()`.

**Notice:**
* A command's **address** is just its position in the list.
* `label` lines don't become commands. They only record an address in the
  **address book** (`program.addresses`).
* Labels get their function's name in front (`Main.main$LOOP`), so every
  function can have its own `LOOP`.

**Exercise:**

```python
from jackvm.parser import parse_program
p = parse_program("""
function Main.main 0
label LOOP
push constant 1
goto LOOP
""")
print(p.commands)
print(p.addresses)
```

Now introduce a typo (`psh constant 1`) and look at the error message.

---

## Step 4 – The heart: running instructions (`jackvm/vm.py`)

This is the most important file. Go slowly.

### 4a. The loop: `tick()`
**Read:** the top docstring and `tick()`.

Every instruction is: **fetch** → **advance pc** → **execute**. A jump just
overwrites `pc` during "execute".

### 4b. The stack: `_stack_push`, `_stack_pop`, `_execute_arithmetic`
**Notice** that `push 9, push 4, sub` gives `9 - 4`. The *second* value
pushed is popped *first*.

**Exercise:** step through a tiny program and watch the stack:

```python
from jackvm import VirtualMachine
vm = VirtualMachine()
vm.load_source("push constant 9\npush constant 4\nsub\n")
for _ in range(3):
    print(vm.current_instruction(), end="   ->   ")
    vm.tick()
    sp = vm.peek(0)
    print("SP =", sp, " stack =", vm.memory[256:sp])
```

### 4c. Segments: `_segment_address`
`local 2` means "address `memory[LCL] + 2`". `LCL` holds an **address** (a
pointer), not a value. That's the key idea behind local variables, objects
(`this`) and arrays (`that`).

### 4d. Function calls: `_execute_call` and `_execute_return`
**Read** them with the frame diagram at the top of `vm.py` beside you.
This is the hardest part of the whole project, so it's fine to read it a few
times.

**Exercise:** run the program from `test_call_and_return_leave_only_the_result`
in `tests/test_vm.py`, using `vm.tick()` one step at a time. Print
`vm.memory[256:vm.peek(0)]` after each step. Can you see the 5-slot frame
appear after `call` and disappear after `return`?

Or do it visually: `python3 -m jackvm pong --paused`, then press **Ctrl+N**
again and again and watch `CALL STACK`, `LCL`, `ARG` and `STACK`.

---

## Step 5 – The operating system (`jackvm/jack_os.py`, `jackvm/os/JackOS.vm`)

**Read:** `jack_os.py` (short), then search `JackOS.vm` for
`function Math.multiply` and `function Keyboard.keyPressed`.

**Notice:**
* The OS is just more VM code, glued onto the end of your program
  ("linking"), with its addresses shifted.
* `Keyboard.keyPressed` is literally `push constant 24576`, then
  `call Memory.peek 1`. Reading the keyboard means reading memory!

**Exercise:** how many instructions does the OS add? (Compare
`len(vm.commands)` for `hello-world` with the number of lines in
`games/hello-world/Main.vm`.)

---

## Step 6 – Pixels (`jackvm/screen.py`)

**Read:** the docstring, `pixel_is_on()` (the simple version), then
`ScreenRenderer` (the fast version).

**Notice:** bit 0 of a word is the **leftmost** pixel. The fast version
uses a *lookup table* so it can draw 60 frames a second in pure Python.

**Exercise:** draw something without any Jack code:

```bash
cat > /tmp/draw.vm <<'EOF'
function Sys.init 0
push constant 0
not                  // 0 with every bit flipped = -1 = all 16 pixels on
pop temp 0           // keep it in temp 0
push constant 16384  // the address of the screen's first word...
pop pointer 1        // ...becomes THAT, so "that N" = screen word N
push temp 0
pop that 0           // row 0, pixels 0-15
push temp 0
pop that 32          // row 1 (each row is 32 words), pixels 0-15
label END
goto END
EOF
python3 -m jackvm /tmp/draw.vm
```

(VM constants can't be negative, so `push constant -1` is not allowed. That's
why we make −1 with `not`.)

What appears in the top-left corner? Change `that 32` to `that 33`. Then
replace the `push constant 0` and `not` lines with `push constant 1`. Which
single pixel lights up now?

---

## Step 7 – Keys (`jackvm/keyboard.py`)

**Read:** the whole file.

**Notice:** pressing a key just *writes a number* to address 24576. Releasing
it writes 0 (or the code of another key you're still holding).

**Exercise:** run `python3 -m jackvm pong --paused --watch 24576`. Hold an
arrow key and press Ctrl+N. Watch the value change.

---

## Step 8 – Seeing inside (`jackvm/debugger.py`)

**Read:** `build_sections()`. It turns the VM's state into a list of
`Section`s (a title plus rows of text) and never draws anything. That's why
it's easy to test (`tests/test_io.py`). `DebuggerPanel.draw_box()` then draws
each section as a box with a border and a title strip.

**Notice:**
* `_peek_text()` refuses to crash on an address outside memory. A debugger
  is needed most when something has gone wrong, such as a stack overflow
  pushing SP off the end of memory.
* `largest_sections()` builds the panel at its **tallest** (status ERROR,
  with a full ERROR box). The player sizes the window from that, so a crash
  never pushes boxes off the bottom.

**Exercise:** add a new row to the STATUS box that shows the current
function's static base address (`vm.call_stack[-1][1]`).

---

## Step 9 – Putting it together (`jackvm/player.py`, `jackvm/main.py`)

**Read:** `Player.run()` and the four steps of the main loop.

**Notice:** it's the same loop as nearly every video game: handle input,
update, draw, wait.

**Notice** how quitting with Esc works (`_handle_events`, `esc_hold_progress`).
Pong uses Esc itself, so the player can't just quit when it sees one. It
records *when* Esc went down and quits only if the key is still held one
second later. Tests can't wait a real second, so the clock is an attribute
(`self.now`) that `tests/test_player.py` swaps for a fake one it moves forward
by hand. That trick is called *dependency injection*.

Then read `jackvm/program_files.py` (how a file, a folder or a game name
becomes a list of `.vm` files) and `jackvm/file_picker.py` (the "choose a
program" window).

**Notice** how `file_picker.py` is split in two:
* `PickerState` is pure logic: which folder we're in, what's selected, what
  a click does. It never touches pygame, so `tests/test_file_picker.py` can
  test it without a window.
* `FilePicker` only draws that state and turns mouse/keyboard events into
  calls on it. Remembering where each row was drawn (`_row_rects`) is how a
  click gets matched to a row. That's called *hit testing*.

**Exercise:** add a "type to jump" feature to the picker. Pressing a letter
should select the first entry starting with that letter. (Hint: handle
`event.unicode` in `_handle_event` and add a method to `PickerState`.)

---

## Bigger challenges

1. **Instruction counter per function:** count how many instructions each
   function runs (a "profiler"). Which function does Pong spend the most time
   in? *(Spoiler: `Math.multiply` or `Sys.wait`.)*
2. **Faster `Math.multiply`:** add a special case to `_execute_call`, just like
   `Sys.halt`, that does the multiply in Python. How much faster does Pong
   run? (The official Java emulator does this for the whole OS.)
3. **Breakpoints:** add a `--break Main.main` option that pauses the player
   when that function is called.
4. **Memory view:** add a second debugger page (toggle with Ctrl+M) that shows
   the heap (from address 2048) as a grid.
5. **Write a translator:** nand2tetris project 7/8 asks you to turn VM code
   into Hack assembly. The parser in this project is already half the job!

---

## Glossary

| Word | Meaning |
|------|---------|
| **address** | the position of a slot in memory (or of a command in the program) |
| **pc** | *program counter*: address of the next instruction |
| **stack** | the pile of numbers at 256+ that instructions work on |
| **SP** | *stack pointer* (memory[0]): address of the next free stack slot |
| **segment** | a named area push/pop can use: local, argument, this, that, ... |
| **frame** | the 5 values `call` saves so `return` can restore the caller |
| **tick** | running one instruction |
| **linking** | joining separately parsed code and fixing up addresses |
| **memory-mapped I/O** | using ordinary memory addresses for the screen and keyboard |
| **true / false** | −1 (all bits on) and 0 |
