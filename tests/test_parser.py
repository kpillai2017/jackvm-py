"""
test_parser.py - Tests for turning .vm text into command objects.
================================================================

Ported (and slightly extended) from the tests inside vm/src/compiler.rs.
"""

import pytest

from jackvm.commands import Arithmetic, Call, Function, Goto, IfGoto, Pop, Push, Return
from jackvm.parser import ParseError, parse_program, strip_comment


def parse_one(line):
    """Parse a single-line program and return its only command."""
    program = parse_program(line)
    assert len(program.commands) == 1
    return program.commands[0]


def problems_for(source):
    """Parse a program we expect to fail and return the problem messages."""
    with pytest.raises(ParseError) as info:
        parse_program(source)
    return [(p.line_number, p.message) for p in info.value.problems]


# --- valid lines -------------------------------------------------------------
def test_push_and_pop():
    assert parse_one("push local 1") == Push("local", 1)
    assert parse_one("push pointer 0") == Push("pointer", 0)
    assert parse_one("pop pointer 1") == Pop("pointer", 1)


@pytest.mark.parametrize("op", ["add", "sub", "neg", "eq", "gt", "lt", "and", "or", "not"])
def test_all_arithmetic_operators(op):
    assert parse_one(op) == Arithmetic(op)


def test_function_call_and_return():
    assert parse_one("function Main.main 3") == Function("Main.main", 3)
    assert parse_one("call Math.multiply 2") == Call("Math.multiply", 2)
    assert parse_one("return") == Return()


def test_comments_blank_lines_and_extra_spaces_are_ignored():
    program = parse_program("// a comment\n\n   push   constant\t5   // five\n\nadd")
    assert program.commands == [Push("constant", 5), Arithmetic("add")]
    assert strip_comment("  push constant 5 // hi ") == "push constant 5"


def test_large_constants_wrap_to_16_bits():
    assert parse_one("push constant 32768") == Push("constant", -32768)


def test_labels_are_scoped_to_their_function():
    program = parse_program(
        """
        function Main.main 0
        label LOOP
        goto LOOP
        if-goto LOOP
        """
    )
    assert program.commands == [
        Function("Main.main", 0),
        Goto("Main.main$LOOP"),
        IfGoto("Main.main$LOOP"),
    ]


def test_addresses_are_recorded_for_functions_and_labels():
    # Labels don't become commands; they name the NEXT command's address.
    program = parse_program(
        """
        push constant 5
        label next_add
        push constant 6
        add
        goto label1
        label label1
        label label2
        function add_two 0
        label before_add
        add
        """
    )
    assert program.addresses == {
        "next_add": 1,
        "label1": 4,
        "label2": 4,
        "add_two": 4,
        "add_two$before_add": 5,
    }
    assert len(program.commands) == 6


# --- invalid lines -----------------------------------------------------------
@pytest.mark.parametrize(
    "line, message_part",
    [
        ("foo constant 5", "Unrecognised instruction"),
        ("push", "expects 2 argument"),
        ("push local", "expects 2 argument"),
        ("push heap 1", "Unknown memory segment"),
        ("push local -1", "zero or more"),
        ("push local x", "found 'x'"),
        ("pop constant 1", "cannot 'pop' into the constant"),
        ("push pointer 2", "pointer segment"),
        ("push temp 8", "temp segment"),
        ("add 1", "expects 0 argument"),
        ("label", "expects 1 argument"),
        ("function Main.main", "expects 2 argument"),
        ("call Foo.bar -2", "zero or more"),
        ("return 1", "expects 0 argument"),
    ],
)
def test_invalid_lines_report_helpful_errors(line, message_part):
    [(line_number, message)] = problems_for(line)
    assert line_number == 1
    assert message_part in message


def test_all_problems_are_reported_with_line_numbers():
    problems = problems_for("push constant 1\nfoo\nadd\nbar 2\n")
    assert [line for line, _ in problems] == [2, 4]


def test_duplicate_function_names_are_rejected():
    problems = problems_for("function A.f 0\nreturn\nfunction A.f 0\nreturn\n")
    assert problems == [(3, "'A.f' is defined more than once")]


def test_bundled_os_and_games_parse_cleanly():
    from jackvm.jack_os import os_program
    from jackvm.program_files import list_games, read_program, resolve_paths

    assert "Sys.init" in os_program().addresses
    games = list_games()
    assert len(games) == 5
    for game in games:
        program = parse_program(read_program(resolve_paths([game])))
        assert "Main.main" in program.addresses, game
