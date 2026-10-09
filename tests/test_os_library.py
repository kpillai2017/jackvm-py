"""
test_os_library.py - the Jack OS classes Math, Memory and Array.
==================================================================

These tests were ported automatically from the original Rust project
(vm/tests/integration_math.rs, integration_memory.rs, integration_array.rs). Each one:

  1. loads a small VM program (inline, or from tests/fixtures/),
  2. optionally sets some registers/memory by hand ("poke"),
  3. runs a fixed number of instructions,
  4. checks that memory contains the expected values.

The expected values come from the nand2tetris course's own test scripts, so
passing them means this VM behaves like the official one.
"""

from helpers import compile_program, fixture


def test_os_math():
    vm = compile_program(fixture("os_math.vm"))
    vm.run(1_000_000)

    assert vm.peek(8000) == 6
    assert vm.peek(8001) == -180
    assert vm.peek(8002) == -18000
    assert vm.peek(8003) == -18000
    assert vm.peek(8004) == 0
    assert vm.peek(8005) == 3
    assert vm.peek(8006) == -3000
    assert vm.peek(8007) == 0
    assert vm.peek(8008) == 3
    assert vm.peek(8009) == 181
    assert vm.peek(8010) == 123
    assert vm.peek(8011) == 123
    assert vm.peek(8012) == 27
    assert vm.peek(8013) == 32767
    assert vm.peek(8015) == 100 // 7
    assert vm.peek(8016) == 200 // 400
    assert vm.peek(8017) == 64 // 4
    assert vm.peek(8018) == 50 // 7
    assert vm.peek(8019) == 700 // 99
    assert vm.peek(8020) == 0


def test_os_memory():
    vm = compile_program(fixture("os_memory.vm"))
    vm.run(1_000_000)

    assert vm.peek(8000) == 333
    assert vm.peek(8001) == 334
    assert vm.peek(8002) == 222
    assert vm.peek(8003) == 122
    assert vm.peek(8004) == 100
    assert vm.peek(8005) == 10


def test_os_array():
    vm = compile_program(fixture("os_array.vm"))
    vm.run(1_000_000)

    assert vm.peek(8000) == 222
    assert vm.peek(8001) == 122
    assert vm.peek(8002) == 100
    assert vm.peek(8003) == 10
