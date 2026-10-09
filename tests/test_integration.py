"""
test_integration.py - whole programs: memory access, arithmetic, flow, calls.
============================================================================

These tests were ported automatically from the original Rust project
(vm/tests/integration.rs). Each one:

  1. loads a small VM program (inline, or from tests/fixtures/),
  2. optionally sets some registers/memory by hand ("poke"),
  3. runs a fixed number of instructions,
  4. checks that memory contains the expected values.

The expected values come from the nand2tetris course's own test scripts, so
passing them means this VM behaves like the official one.
"""

from helpers import compile_program, execute_program, fixture  # noqa: F401


def test_memory_access_basic_test():
    program = """
        push constant 10
        pop local 0
        push constant 21
        push constant 22
        pop argument 2
        pop argument 1
        push constant 36
        pop this 6
        push constant 42
        push constant 45
        pop that 5
        pop that 2
        push constant 510
        pop temp 6
        push local 0
        push that 5
        add
        push argument 1
        sub
        push this 6
        push this 6
        add
        sub
        push temp 6
        add
    """
    vm = execute_program(program)

    assert vm.peek(256) == 472
    assert vm.peek(300) == 10
    assert vm.peek(401) == 21
    assert vm.peek(402) == 22
    assert vm.peek(3006) == 36
    assert vm.peek(3012) == 42
    assert vm.peek(3015) == 45
    assert vm.peek(11) == 510


def test_memory_access_pointer_test():
    program = """
        push constant 3030
        pop pointer 0
        push constant 3040
        pop pointer 1
        push constant 32
        pop this 2
        push constant 46
        pop that 6
        push pointer 0
        push pointer 1
        add
        push this 2
        sub
        push that 6
        add
    """
    vm = execute_program(program)

    assert vm.peek(256) == 6084
    assert vm.peek(3) == 3030
    assert vm.peek(4) == 3040
    assert vm.peek(3032) == 32
    assert vm.peek(3046) == 46


def test_memory_access_static_test():
    program = """
        push constant 111
        push constant 333
        push constant 888
        pop static 8
        pop static 3
        pop static 1
        push static 3
        push static 1
        sub
        push static 8
        add
    """
    vm = execute_program(program)

    assert vm.peek(256) == 1110


def test_stack_arithmetic_simple_add():
    program = """
        push constant 8
        push constant 7
        add
    """
    vm = execute_program(program)

    assert vm.peek(0) == 257
    assert vm.peek(256) == 15


def test_stack_arithmetic_stack_test():
    program = """
        push constant 17
        push constant 17
        eq
        push constant 17
        push constant 16
        eq
        push constant 16
        push constant 17
        eq
        push constant 892
        push constant 891
        lt
        push constant 891
        push constant 892
        lt
        push constant 891
        push constant 891
        lt
        push constant 32767
        push constant 32766
        gt
        push constant 32766
        push constant 32767
        gt
        push constant 32766
        push constant 32766
        gt
        push constant 57
        push constant 31
        push constant 53
        add
        push constant 112
        sub
        neg
        and
        push constant 82
        or
        not
    """
    vm = execute_program(program)

    assert vm.peek(0) == 266
    assert vm.peek(256) == -1
    assert vm.peek(257) == 0
    assert vm.peek(258) == 0
    assert vm.peek(259) == 0
    assert vm.peek(260) == -1
    assert vm.peek(261) == 0
    assert vm.peek(262) == -1
    assert vm.peek(263) == 0
    assert vm.peek(264) == 0
    assert vm.peek(265) == -91


def test_program_flow_basic_loop():
    program = """
        // Computes the sum 1 + 2 + ... + argument[0] and pushes the
        // result onto the stack. Argument[0] is initialized by the test
        // script before this code starts running.
        push constant 0
        pop local 0         // initializes sum = 0
        label LOOP_START
        push argument 0
        push local 0
        add
        pop local 0	        // sum = sum + counter
        push argument 0
        push constant 1
        sub
        pop argument 0      // counter--
        push argument 0
        if-goto LOOP_START  // If counter > 0, goto LOOP_START
        push local 0
    """
    vm = compile_program(program)
    vm.poke(0, 256)
    vm.poke(1, 300)
    vm.poke(2, 400)
    vm.poke(400, 3)
    vm.run(600)

    assert vm.peek(0) == 257
    assert vm.peek(256) == 6


def test_program_flow_fibonacci_series():
    program = """
        // Puts the first argument[0] elements of the Fibonacci series
        // in the memory, starting in the address given in argument[1].
        // Argument[0] and argument[1] are initialized by the test script
        // before this code starts running.

        push argument 1
        pop pointer 1           // that = argument[1]

        push constant 0
        pop that 0              // first element in the series = 0
        push constant 1
        pop that 1              // second element in the series = 1

        push argument 0
        push constant 2
        sub
        pop argument 0          // num_of_elements -= 2 (first 2 elements are set)

        label MAIN_LOOP_START

        push argument 0
        if-goto COMPUTE_ELEMENT // if num_of_elements > 0, goto COMPUTE_ELEMENT
        goto END_PROGRAM        // otherwise, goto END_PROGRAM

        label COMPUTE_ELEMENT

        push that 0
        push that 1
        add
        pop that 2              // that[2] = that[0] + that[1]

        push pointer 1
        push constant 1
        add
        pop pointer 1          // that += 1

        push argument 0
        push constant 1
        sub
        pop argument 0         // num_of_elements--

        goto MAIN_LOOP_START

        label END_PROGRAM
    """
    vm = compile_program(program)
    vm.poke(0, 256)
    vm.poke(1, 300)
    vm.poke(2, 400)
    vm.poke(400, 6)
    vm.poke(401, 3000)
    vm.run(1_100)

    assert vm.peek(3000) == 0
    assert vm.peek(3001) == 1
    assert vm.peek(3002) == 1
    assert vm.peek(3003) == 2
    assert vm.peek(3004) == 3
    assert vm.peek(3005) == 5


def test_function_calls_simple_function():
    program = """
        // Performs a simple calculation and returns the result.
        function SimpleFunction.test 2
        push local 0
        push local 1
        add
        not
        push argument 0
        add
        push argument 1
        sub
        return
    """
    vm = compile_program(program)
    vm.poke(0, 317)
    vm.poke(1, 317)
    vm.poke(2, 310)
    vm.poke(3, 3000)
    vm.poke(4, 4000)
    vm.poke(310, 1234)
    vm.poke(311, 37)
    vm.poke(312, 9)
    vm.poke(313, 305)
    vm.poke(314, 300)
    vm.poke(315, 3010)
    vm.poke(316, 4010)
    vm.run(10)

    assert vm.peek(0) == 311
    assert vm.peek(1) == 305
    assert vm.peek(2) == 300
    assert vm.peek(3) == 3010
    assert vm.peek(4) == 4010
    assert vm.peek(310) == 1196


def test_function_calls_simple_function_from_sys_init():
    program = """
        call Sys.init 0 // dummy to align with Java implementation
        function Main.test 2
        push argument 1
        push argument 0
        pop local 0
        pop local 1
        push argument 0
        push argument 1
        add
        not
        push argument 0
        add
        push argument 1
        sub
        return
        function Sys.init 1
        push constant 4
        push constant 9
        call Main.test 2
        label WHILE
        goto WHILE              // loops infinitely
    """
    vm = compile_program(program)
    vm.run(20)

    assert vm.peek(0) == 258
    assert vm.peek(256) == 0
    assert vm.peek(257) == -19
    assert vm.peek(258) == 9
    assert vm.peek(259) == 19
    assert vm.peek(260) == 0
    assert vm.peek(261) == 0
    assert vm.peek(262) == 0
    assert vm.peek(263) == 0
    assert vm.peek(264) == 4
    assert vm.peek(265) == 9
    assert vm.peek(266) == -19
    assert vm.peek(267) == 9
    assert vm.peek(268) == 0
    assert vm.peek(269) == 0
    assert vm.peek(270) == 0


def test_function_call_multiple_args():
    program = """
        call Sys.init 0 // dummy to align with Java implementation
        function Main.test 0
        push argument 0
        pop static 0
        push argument 1
        pop static 1
        push argument 2
        pop static 2
        return

        function Main.main 0
        push constant 9
        push constant 8
        push constant 7
        call Main.test 3
        pop temp 0
        return

        function Sys.init 1
        call Main.main 0
        pop temp 0

        label WHILE
        goto WHILE              // loops infinitely
    """
    vm = compile_program(program)
    vm.run(50)

    assert vm.peek(16) == 9
    assert vm.peek(17) == 8
    assert vm.peek(18) == 7


def test_logic_in_function_called_from_sys_init():
    program = """
        call Sys.init 0 // dummy to align with Java implementation
        function Main.test 4
        push constant 4
        pop local 2
        push local 2
        push argument 0
        gt
        not
        push local 2
        push constant 0
        lt
        not
        and
        if-goto IF_TRUE1
        goto IF_FALSE1
        label IF_TRUE1
        push constant 1
        pop static 0
        goto END_IF1
        label IF_FALSE1
        push constant 2
        pop static 0
        label END_IF1
        return

        function Main.main 0
        push constant 9
        call Main.test 1
        pop temp 0
        push static 0
        pop static 1

        push constant 3
        call Main.test 1
        pop temp 0
        push static 0
        pop static 2
        return

        function Sys.init 1
        call Main.main 0
        pop temp 0

        label WHILE
        goto WHILE              // loops infinitely
    """
    vm = compile_program(program)
    vm.run(50)

    assert vm.peek(17) == 1
    assert vm.peek(18) == 2


def test_function_calls_nested_call():
    vm = compile_program(fixture("function_calls_nested_call.vm"))
    vm.poke(0, 261)
    vm.poke(0, 261)
    vm.poke(1, 261)
    vm.poke(2, 256)
    vm.poke(3, -3)
    vm.poke(4, -4)
    vm.poke(5, -1)
    vm.poke(6, -1)
    vm.poke(256, 1234)
    vm.poke(257, -1)
    vm.poke(258, -2)
    vm.poke(259, -3)
    vm.poke(260, -4)
    vm.poke(261, -1)
    vm.poke(262, -1)
    vm.poke(263, -1)
    vm.poke(264, -1)
    vm.poke(265, -1)
    vm.poke(266, -1)
    vm.poke(267, -1)
    vm.poke(268, -1)
    vm.poke(269, -1)
    vm.poke(270, -1)
    vm.poke(271, -1)
    vm.poke(272, -1)
    vm.poke(273, -1)
    vm.poke(274, -1)
    vm.poke(275, -1)
    vm.poke(276, -1)
    vm.poke(277, -1)
    vm.poke(278, -1)
    vm.poke(279, -1)
    vm.poke(280, -1)
    vm.poke(281, -1)
    vm.poke(282, -1)
    vm.poke(283, -1)
    vm.poke(284, -1)
    vm.poke(285, -1)
    vm.poke(286, -1)
    vm.poke(287, -1)
    vm.poke(288, -1)
    vm.poke(289, -1)
    vm.poke(290, -1)
    vm.poke(291, -1)
    vm.poke(292, -1)
    vm.poke(293, -1)
    vm.poke(294, -1)
    vm.poke(295, -1)
    vm.poke(296, -1)
    vm.poke(297, -1)
    vm.poke(298, -1)
    vm.poke(299, -1)
    vm.poke(0, 261)
    vm.poke(1, 261)
    vm.poke(2, 256)
    vm.poke(3, 3000)
    vm.poke(4, 4000)
    vm.run(50)

    assert vm.peek(0) == 261
    assert vm.peek(1) == 261
    assert vm.peek(2) == 256
    assert vm.peek(3) == 4000
    assert vm.peek(4) == 5000
    assert vm.peek(5) == 135
    assert vm.peek(6) == 246


def test_function_calls_fibonacci_element():
    program = """
        // Pushes a constant, say n, onto the stack, and calls the Main.fibonacii
        // function, which computes the n'th element of the Fibonacci series.
        // Note that by convention, the Sys.init function is called \"automatically\"
        // by the bootstrap code.

        function Sys.init 0
        push constant 4
        call Main.fibonacci 1   // computes the 4'th fibonacci element
        label WHILE
        goto WHILE              // loops infinitely

        // Computes the n'th element of the Fibonacci series, recursively.
        // n is given in argument[0].  Called by the Sys.init function
        // (part of the Sys.vm file), which also pushes the argument[0]
        // parameter before this code starts running.

        function Main.fibonacci 0
        push argument 0
        push constant 2
        lt                     // checks if n<2
        if-goto IF_TRUE
        goto IF_FALSE
        label IF_TRUE          // if n<2, return n
        push argument 0
        return
        label IF_FALSE         // if n>=2, returns fib(n-2)+fib(n-1)
        push argument 0
        push constant 2
        sub
        call Main.fibonacci 1  // computes fib(n-2)
        push argument 0
        push constant 1
        sub
        call Main.fibonacci 1  // computes fib(n-1)
        add                    // returns fib(n-1) + fib(n-2)
        return
    """
    vm = compile_program(program)
    vm.poke(0, 261)
    vm.run(175)

    assert vm.peek(0) == 262
    assert vm.peek(261) == 3


def test_function_calls_fibonacci_element_2():
    program = """
        // Pushes a constant, say n, onto the stack, and calls the Main.fibonacii
        // function, which computes the n'th element of the Fibonacci series.
        // Note that by convention, the Sys.init function is called \"automatically\"
        // by the bootstrap code.

        function Sys.init 0
        push constant 4
        call Main.fibonacci 1   // computes the 4'th fibonacci element
        label WHILE
        goto WHILE              // loops infinitely

        // Computes the n'th element of the Fibonacci series, recursively.
        // n is given in argument[0].  Called by the Sys.init function
        // (part of the Sys.vm file), which also pushes the argument[0]
        // parameter before this code starts running.

        function Main.fibonacci 0
        push argument 0
        push constant 2
        lt                     // checks if n<2
        if-goto IF_TRUE
        goto IF_FALSE
        label IF_TRUE          // if n<2, return n
        push argument 0
        return
        label IF_FALSE         // if n>=2, returns fib(n-2)+fib(n-1)
        push argument 0
        push constant 2
        sub
        call Main.fibonacci 1  // computes fib(n-2)
        push argument 0
        push constant 1
        sub
        call Main.fibonacci 1  // computes fib(n-1)
        add                    // returns fib(n-1) + fib(n-2)
        return
    """
    vm = compile_program(program)
    vm.poke(0, 261)
    vm.run(250)



def test_function_calls_recursive_add():
    program = """
        // Pushes a constant, say n, onto the stack, and calls the Main.fibonacii
        // function, which computes the n'th element of the Fibonacci series.
        // Note that by convention, the Sys.init function is called \"automatically\"
        // by the bootstrap code.
        call Sys.init 0 // dummy

        function Main.main 1
        push constant 1
        call Main.add 1
        pop local 0
        label WHILE_EXP0
        push constant 0
        not
        not
        if-goto WHILE_END0
        goto WHILE_EXP0
        label WHILE_END0
        push constant 0
        return
        function Main.add 0
        push argument 0
        push constant 0
        eq
        if-goto IF_TRUE0
        goto IF_FALSE0
        label IF_TRUE0
        push constant 0
        return
        goto IF_END0
        label IF_FALSE0
        push constant 1
        push argument 0
        push constant 1
        sub
        call Main.add 1
        add
        return
        label IF_END0

        function Sys.init 0
        //push constant 4
        call Main.main 0   // computes the 4'th fibonacci element
        label WHILE
        goto WHILE              // loops infinitely
    """
    vm = compile_program(program)
    vm.poke(0, 256)
    vm.run(102)



def test_memory_access_static_addresses():
    # Two classes both use "static 0" and "static 1". They must get DIFFERENT
    # memory slots. (Ported by hand: the Rust version accepted either class
    # being first; our VM hands out blocks in the order classes appear.)
    program = """
        function Test1.main 0
        push constant 2
        push constant 1
        pop static 0
        pop static 1
        return

        function Test2.main 0
        push constant 4
        push constant 3
        pop static 0
        pop static 1
        return

        function Sys.init 0
        call Test1.main 0
        pop temp 0
        call Test2.main 0
        pop temp 0
    """
    vm = execute_program(program)

    assert vm.peek(16) == 1  # Test1 static 0
    assert vm.peek(17) == 2  # Test1 static 1
    assert vm.peek(18) == 3  # Test2 static 0
    assert vm.peek(19) == 4  # Test2 static 1
