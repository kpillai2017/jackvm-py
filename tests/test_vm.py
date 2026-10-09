"""
test_vm.py - Unit tests for individual VM instructions.
======================================================

Ported from the unit tests inside the original vm/src/vm.rs. Most tests build
a list of command objects by hand, run them, and inspect the stack/memory.
Reading these is a good way to learn exactly what each instruction does.
"""

import pytest

from jackvm.commands import Arithmetic, Call, Function, Goto, IfGoto, Pop, Push, Return
from jackvm.memory_map import ARG, FALSE, LCL, SP, STACK_START, STATIC_START, TEMP_START, THAT, THIS, TRUE, to_int16
from jackvm.vm import SysError, VirtualMachine, VMError, assign_static_addresses


def run_commands(commands, ticks=100):
    """Load a hand-made list of commands and run them."""
    vm = VirtualMachine()
    vm.load(commands)
    vm.run(ticks)
    return vm


def top_of_stack(vm):
    return vm.peek(vm.peek(SP) - 1)


def const(n):
    return Push("constant", to_int16(n))


# ---------------------------------------------------------------------------
# 16-bit numbers
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "value, expected",
    [(0, 0), (5, 5), (32767, 32767), (32768, -32768), (65535, -1), (-32769, 32767), (-1, -1)],
)
def test_to_int16_wraps_like_real_hardware(value, expected):
    assert to_int16(value) == expected


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------
def test_add_instruction():
    vm = run_commands([const(8), const(7), Arithmetic("add")])
    assert vm.peek(SP) == STACK_START + 1
    assert top_of_stack(vm) == 15


def test_arithmetic_and_overflows():
    vm = run_commands([
        const(2), const(2), Arithmetic("add"), Pop("static", 0),
        const(4), const(4), Arithmetic("add"), Pop("static", 1),
        const(1024), const(1024), Arithmetic("add"), Pop("static", 2),
        const(16384), const(16384), Arithmetic("add"), Pop("static", 3),
        const(4), Arithmetic("neg"), const(4), Arithmetic("sub"), Pop("static", 4),
        const(16384), Arithmetic("neg"), const(32767), Arithmetic("sub"), Pop("static", 5),
    ])  # fmt: skip
    assert vm.peek(STATIC_START + 0) == 4
    assert vm.peek(STATIC_START + 1) == 8
    assert vm.peek(STATIC_START + 2) == 2048
    assert vm.peek(STATIC_START + 3) == -32768  # 16384 + 16384 overflows
    assert vm.peek(STATIC_START + 4) == -8
    assert vm.peek(STATIC_START + 5) == 16385  # -16384 - 32767 = -49151 underflows (+65536)


def test_sub_instruction():
    vm = run_commands([const(16), const(7), Arithmetic("sub")])
    assert top_of_stack(vm) == 9  # 16 - 7, not 7 - 16


def test_and_instruction():
    vm = run_commands([
        const(3), const(5), Arithmetic("and"), Pop("static", 0),
        const(-32768), const(32767), Arithmetic("and"), Pop("static", 1),  # no bits overlap
        const(-32768), const(-1), Arithmetic("and"), Pop("static", 2),  # only the top bit overlaps
    ])  # fmt: skip
    assert vm.peek(STATIC_START + 0) == 1
    assert vm.peek(STATIC_START + 1) == 0
    assert vm.peek(STATIC_START + 2) == -32768


def test_or_instruction():
    vm = run_commands([
        const(3), const(4), Arithmetic("or"), Pop("static", 0),
        const(-32768), const(32767), Arithmetic("or"), Pop("static", 1),  # all bits set
    ])  # fmt: skip
    assert vm.peek(STATIC_START + 0) == 7
    assert vm.peek(STATIC_START + 1) == -1


@pytest.mark.parametrize(
    "x, y, operator, expected",
    [
        (88, 89, "eq", FALSE), (101, 101, "eq", TRUE),
        (88, 89, "lt", TRUE), (101, 101, "lt", FALSE),
        (105, 55, "gt", TRUE), (9998, 9999, "gt", FALSE),
    ],
)  # fmt: skip
def test_comparisons_push_true_or_false(x, y, operator, expected):
    vm = run_commands([const(x), const(y), Arithmetic(operator)])
    assert vm.peek(SP) == STACK_START + 1
    assert top_of_stack(vm) == expected


def test_not_instruction():
    vm = run_commands([
        const(-1), Arithmetic("not"), Pop("static", 0),
        const(0), Arithmetic("not"), Pop("static", 1),
        const(32767), Arithmetic("neg"), const(1), Arithmetic("sub"), Arithmetic("not"), Pop("static", 2),
    ])  # fmt: skip
    assert vm.peek(STATIC_START + 0) == 0
    assert vm.peek(STATIC_START + 1) == -1
    assert vm.peek(STATIC_START + 2) == 32767


def test_neg_instruction():
    vm = run_commands([
        const(-99), Arithmetic("neg"), Pop("static", 0),
        const(54), Arithmetic("neg"), Pop("static", 1),
        const(-32768), Arithmetic("neg"), Pop("static", 2),  # -(-32768) wraps back to -32768
    ])  # fmt: skip
    assert vm.peek(STATIC_START + 0) == 99
    assert vm.peek(STATIC_START + 1) == -54
    assert vm.peek(STATIC_START + 2) == -32768


def test_execute_one_tick_at_a_time():
    vm = VirtualMachine()
    vm.load([const(8), const(7), Arithmetic("add")])
    vm.tick()
    assert vm.peek(SP) == STACK_START + 1 and top_of_stack(vm) == 8
    vm.tick()
    assert vm.peek(SP) == STACK_START + 2 and top_of_stack(vm) == 7
    vm.tick()
    assert vm.peek(SP) == STACK_START + 1 and top_of_stack(vm) == 15
    assert vm.is_halted()
    assert vm.ticks == 3


# ---------------------------------------------------------------------------
# Push / pop with every segment
# ---------------------------------------------------------------------------
def test_push_from_every_segment():
    vm = VirtualMachine()
    vm.load([
        Push("local", 0), Push("argument", 0), Push("this", 0), Push("that", 0),
        Push("pointer", 0), Push("pointer", 1), Push("static", 4), Push("temp", 2),
    ])  # fmt: skip
    vm.memory[LCL], vm.memory[256] = 256, 100
    vm.memory[ARG], vm.memory[257] = 257, 200
    vm.memory[THIS], vm.memory[258] = 258, 300
    vm.memory[THAT], vm.memory[259] = 259, 400
    vm.memory[STATIC_START + 4] = 500
    vm.memory[TEMP_START + 2] = 600
    vm.memory[SP] = 260
    vm.run(8)

    assert vm.memory[260:268] == [100, 200, 300, 400, 258, 259, 500, 600]


def test_pop_to_every_segment():
    vm = VirtualMachine()
    vm.load([
        Pop("local", 0), Pop("argument", 0), Pop("this", 0), Pop("that", 0),
        Pop("pointer", 0), Pop("pointer", 1), Pop("static", 4), Pop("temp", 2),
    ])  # fmt: skip
    vm.memory[LCL], vm.memory[ARG], vm.memory[THIS], vm.memory[THAT] = 300, 310, 320, 330
    vm.memory[SP] = 256
    # Push in reverse order so the first pop gets 100, the second 200, ...
    for value in [40, 30, 20, 10, 400, 300, 200, 100]:
        vm.memory[vm.memory[SP]] = value
        vm.memory[SP] += 1
    vm.run(8)

    assert vm.peek(300) == 100  # local 0 (LCL was 300)
    assert vm.peek(310) == 200  # argument 0
    assert vm.peek(320) == 300  # this 0
    assert vm.peek(330) == 400  # that 0
    assert vm.peek(THIS) == 10  # pointer 0 *is* THIS
    assert vm.peek(THAT) == 20  # pointer 1 *is* THAT
    assert vm.peek(STATIC_START + 4) == 30
    assert vm.peek(TEMP_START + 2) == 40
    assert vm.peek(SP) == 256  # everything we pushed was popped


# ---------------------------------------------------------------------------
# Jumps
# ---------------------------------------------------------------------------
def test_if_goto():
    vm = VirtualMachine()
    vm.load(
        [
            Push("local", 2),  # 0
            Push("argument", 0),
            Arithmetic("gt"),
            Arithmetic("not"),
            Push("local", 2),
            const(0),  # 5
            Arithmetic("lt"),
            Arithmetic("not"),
            Arithmetic("and"),
            IfGoto("IF_TRUE1"),
            Goto("IF_FALSE1"),  # 10
            const(1),  # 11 = IF_TRUE1
            Pop("static", 0),
            Goto("END_IF1"),
            const(2),  # 14 = IF_FALSE1
            Pop("static", 0),
            # 16 = END_IF1
        ],
        addresses={"IF_TRUE1": 11, "IF_FALSE1": 14, "END_IF1": 16},
    )
    vm.memory[ARG], vm.memory[256] = 256, 9
    vm.memory[LCL], vm.memory[259] = 257, 4
    vm.memory[SP] = 261
    vm.run(100)
    assert vm.peek(STATIC_START) == 1  # 0 <= 4 <= 9, so the "true" branch ran


def test_jump_to_unknown_label_is_a_clear_error():
    vm = VirtualMachine()
    vm.load([Goto("NOWHERE")])
    with pytest.raises(VMError, match="NOWHERE"):
        vm.tick()


# ---------------------------------------------------------------------------
# Static variables
# ---------------------------------------------------------------------------
def test_each_class_gets_its_own_static_block():
    commands = [
        Function("Test1.main", 0), const(2), const(1), Push("static", 0), Push("static", 1), Return(),
        Function("Test2.main", 0), const(4), const(3), Push("static", 0), Push("static", 1), Return(),
    ]  # fmt: skip
    assert assign_static_addresses(commands) == {"Test1": 16, "Test2": 18}


# ---------------------------------------------------------------------------
# Calls, returns and the special OS functions
# ---------------------------------------------------------------------------
def test_call_and_return_leave_only_the_result():
    vm = VirtualMachine()
    vm.load_source(
        """
        function Sys.init 0
        push constant 10
        push constant 20
        call Main.add 2      // leaves 30 where the 10 was
        label END
        goto END

        function Main.add 1  // one local, unused
        push argument 0
        push argument 1
        add
        return
        """
    )
    vm.run(100)
    assert vm.peek(SP) == 257  # only one value left on the stack...
    assert vm.peek(256) == 30  # ...and it's the result
    assert vm.call_stack == [("Sys.init", STATIC_START)]


def test_call_sys_halt_halts_vm():
    vm = VirtualMachine()
    vm.load([const(89), Call("Sys.halt", 0), const(23), Arithmetic("lt")])
    vm.tick()
    assert not vm.is_halted()
    vm.tick()
    assert vm.pc == 4
    assert vm.is_halted()
    assert vm.current_instruction() == "HALT"


def test_sys_error_raises_with_a_helpful_message():
    vm = VirtualMachine()
    vm.load_source(
        """
        function Main.main 0
        push constant 1
        push constant 0
        call Math.divide 2
        return
        """
    )
    # The OS start-up (fonts, screen, memory) takes a few hundred thousand
    # instructions before Main.main even begins - so run plenty.
    with pytest.raises(SysError, match="division by zero") as info:
        vm.run(5_000_000)
    assert info.value.code == 3


def test_stack_underflow_is_detected():
    vm = VirtualMachine()
    vm.load([Arithmetic("add")])
    vm.memory[SP] = 0
    with pytest.raises(VMError, match="underflow"):
        vm.tick()


def test_infinite_recursion_is_reported_as_stack_overflow():
    vm = VirtualMachine()
    vm.load_source("function Sys.init 0\ncall Sys.init 0\n")  # calls itself forever
    with pytest.raises(VMError, match="Stack overflow"):
        vm.run(1_000_000)


def test_reading_past_the_end_of_memory_is_a_clear_error():
    vm = VirtualMachine()
    vm.load([Push("constant", 30000), Pop("pointer", 1), Push("that", 0)])
    with pytest.raises(VMError, match="'that 0' tried to use address 30000, which is outside memory"):
        vm.run(3)


def test_restart_resets_everything():
    vm = VirtualMachine()
    vm.load_source("function Main.main 0\npush constant 5\npop static 0\nlabel L\ngoto L\n")
    vm.run(5_000)
    assert vm.ticks > 0
    vm.restart()
    assert vm.ticks == 0
    assert vm.peek(SP) == STACK_START
    assert vm.pc == vm.addresses["Sys.init"]
    assert vm.call_stack == []


def test_os_is_added_only_when_needed():
    with_main = VirtualMachine()
    with_main.load_source("function Main.main 0\npush constant 0\nreturn\n")
    assert "Math.multiply" in with_main.addresses  # OS was added

    own_sys = VirtualMachine()
    own_sys.load_source("function Sys.init 0\nlabel L\ngoto L\n")
    assert "Math.multiply" not in own_sys.addresses  # brought its own Sys.init
    assert len(own_sys.commands) == 2
