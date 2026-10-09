"""
jackvm - a Jack Virtual Machine written in plain, well-commented Python.
=======================================================================

A Python port of jackvm-rs (https://github.com/jcon/jackvm-rs), written for
learning. Suggested reading order (each file builds on the previous ones):

    1. memory_map.py  - the memory layout of the Hack computer
    2. commands.py    - the nine kinds of VM instruction
    3. parser.py      - .vm text  ->  command objects + address book
    4. vm.py          - runs the commands (the heart of the project)
    5. jack_os.py     - adds the Jack OS library to your program
    6. screen.py      - screen memory -> pixels
    7. keyboard.py    - key presses   -> keyboard memory
    8. debugger.py    - the live register / stack view
    9. player.py      - the pygame window and main loop
   10. program_files.py - turns a file / folder / game name into .vm files
   11. file_picker.py - the "choose a program" window (GUI)
   12. main.py        - the command line

Quick use from Python:

    from jackvm import VirtualMachine
    vm = VirtualMachine()
    vm.load_source("push constant 7\\npush constant 8\\nadd")
    vm.run(3)
    print(vm.peek(256))   # -> 15
"""

from .parser import ParseError, parse_program
from .vm import SysError, VirtualMachine, VMError

__all__ = ["VirtualMachine", "VMError", "SysError", "ParseError", "parse_program"]
