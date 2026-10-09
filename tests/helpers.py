"""
helpers.py - Shared helpers for the tests (a port of vm/tests/helper.rs).
"""

from __future__ import annotations

from pathlib import Path

from jackvm import VirtualMachine

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    """Read a long test program from tests/fixtures/."""
    return (FIXTURES / name).read_text(encoding="utf-8")


def compile_program(source: str) -> VirtualMachine:
    """Parse and load a program (adding the OS if it needs one). Doesn't run it."""
    vm = VirtualMachine()
    vm.load_source(source)  # raises ParseError if the program is wrong
    return vm


def execute_program(source: str) -> VirtualMachine:
    """
    Load a program, set up the registers the way the nand2tetris test
    scripts do, and run 100 instructions.

        SP=256  LCL=300  ARG=400  THIS=3000  THAT=3010
    """
    vm = compile_program(source)
    vm.poke(0, 256)
    vm.poke(1, 300)
    vm.poke(2, 400)
    vm.poke(3, 3000)
    vm.poke(4, 3010)
    vm.run(100)
    return vm
