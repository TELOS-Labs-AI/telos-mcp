"""`telos_verify_kit_record`: the kit record check of `telos_receipt.record`, carried over MCP (M1 to M6).

M1 for accepted string inputs, after the empty-string mapping, the tool's answer is the answer of
   `telos_receipt.record.check_record(receipt, witness or None, reading or None)`, unchanged, and nothing more is
   claimed (A5.1): (a) under the real default pins, (b) WITNESSED under a TEST-ONLY substitution of the loaded
   reader's default pins by the canary pins. (b) is test wiring: it shows the reader's state is carried through,
   not authenticity under the production pins. Arguments the protocol refuses are not part of this claim.
A4 a witness row and a reading given as strings through `mcp.call_tool` reach `check_record` byte for byte; the
   empty string is "not supplied".
A5 per argument: omitted and empty are the same answer, a non-empty invalid string is never "not supplied" (A5.1).
   Two boundaries (A5.2). Protocol: an argument that is not a JSON string is refused by the framework and the
   tool function is not invoked; in-process `call_tool` and real stdio, measured on mcp 1.26.0 only. Application
   (a direct Python call): every value gets a dictionary and no `Exception` is raised.
M2 no engine call, no file left behind, no socket and no process.
M3 the size caps and the non-string refusals, each beside a valid call; no exception leaves the tool.
M4 the tool list is the six 0.1.2 names plus this one, and the six old tools answer as 0.1.2 answered.
M5 with `telos_receipt.record` unimportable the server starts, the six old tools answer as before and this tool
   says `tool_unavailable`, beside a normal environment.
M6 no `pins` argument; every report says `pins: "default"`.

Fixtures: `kit_record_fixtures/` is a byte copy of the telos-receipt repository's committed canary fixtures (see
PROVENANCE.json there). Canary PUBLIC pins only. No test opens a socket, a real key or a real service.
`old_tools_golden.json` is what telos-mcp 0.1.2 (b53473a) answered with the clock frozen (see old_tools_golden.py).
"""
import asyncio
import builtins
import contextlib
import functools
import hashlib
import importlib
import inspect
import json
import os
import socket
import subprocess
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from unittest import mock

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.fastmcp.exceptions import ToolError

import old_tools_golden
from telos_mcp import __version__, engine, engine_stub, server

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
FIXTURES = TESTS / "kit_record_fixtures"
ORACLE = json.loads((FIXTURES / "oracle.json").read_text(encoding="utf-8"))
PROVENANCE = json.loads((FIXTURES / "PROVENANCE.json").read_text(encoding="utf-8"))
GOLDEN_BYTES = old_tools_golden.GOLDEN.read_bytes()
GOLDEN = json.loads(GOLDEN_BYTES)
NAMES = ("receipt.json", "witness.json", "reading.json")
ARGUMENTS = ("receipt_json", "witness_json", "reading_json")
CAPS = (1048576, 4096, 32768)
FIXTURE_NAMES = ("witnessed", "not_witnessed", "refused")
TOOL = "telos_verify_kit_record"
TOOL_UNAVAILABLE = {"ok": False, "reason": "tool_unavailable"}
INVALID_ARGUMENT = {"ok": False, "reason": "invalid_argument"}
TOO_LARGE = {"ok": False, "reason": "input_too_large"}
FRAMEWORK_REFUSED = "refused by the MCP framework before the tool ran"
GROUP = getattr(builtins, "BaseExceptionGroup", Exception)


@pytest.fixture(autouse=True)
def stub_engine(monkeypatch):
    monkeypatch.setenv("TELOS_MCP_ENGINE", "stub")


# ----------------------------------------------------------------------------------------------------- helpers

def tool():
    api = getattr(server, TOOL, None)
    assert callable(api), "the kit record MCP tool is missing"
    return api


def answer(*args, **kwargs):
    """The tool called as a function. An exception leaving it is a failed guarantee, not a broken test."""
    api = tool()
    try:
        return api(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"{TOOL} raised {type(e).__name__}: {e}")


def record():
    try:
        return importlib.import_module("telos_receipt.record")
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"telos_receipt.record is not importable in this environment: {type(e).__name__}: {e}")


def raw(name):
    """(receipt, witness, reading) of one fixture as bytes; None for a file the fixture does not have."""
    return tuple((FIXTURES / name / f).read_bytes() if (FIXTURES / name / f).exists() else None for f in NAMES)


def texts(name):
    """The same three as the strings an MCP client sends; "" for a file the fixture does not have."""
    return tuple("" if blob is None else blob.decode("utf-8") for blob in raw(name))


def supplied(name):
    """The MCP arguments for one fixture: only the files it has."""
    return {key: text for key, text in zip(ARGUMENTS, texts(name)) if text != ""}


def protocol(arguments, name=TOOL):
    """The tool asked through the server's own `mcp.call_tool` (argument validation included): its structured
    answer, or FRAMEWORK_REFUSED when the framework refused the arguments or the tool raised."""
    tool()

    async def ask():
        return await server.mcp.call_tool(name, arguments)

    try:
        content, structured = asyncio.run(ask())
    except Exception:  # noqa: BLE001  (ToolError: validation, or an exception that left the tool)
        return FRAMEWORK_REFUSED
    assert json.loads(content[0].text) == structured
    return structured


@contextlib.contextmanager
def count_tool_invocations():
    """Every invocation of the function the server has registered for the tool, counted by a wrapper put on the
    registered tool for the length of the block (FastMCP keeps it as `fn`; reaches `mcp._tool_manager`)."""
    registered = server.mcp._tool_manager.get_tool(TOOL)
    assert registered is not None and registered.fn is tool()
    real, calls = registered.fn, []

    @functools.wraps(real)
    def counted(*args, **kwargs):
        calls.append((args, kwargs))
        return real(*args, **kwargs)

    with mock.patch.object(registered, "fn", counted):
        yield calls


def protocol_outcome(arguments):
    """(`"answer"`, structured answer) or (`"framework error"`, message) for one in-process `mcp.call_tool`."""
    tool()

    async def ask():
        return await server.mcp.call_tool(TOOL, arguments)

    try:
        content, structured = asyncio.run(ask())
    except ToolError as e:
        return "framework error", str(e)
    return "answer", structured


def is_argument_validation_error(message, argument):
    """The framework's own refusal of one argument, as mcp 1.26.0 with pydantic 2 words it."""
    return ("validation error" in message and argument in message and "Input should be a valid string" in message
            and '"ok"' not in message)


class Seen(list):
    pins = 0


@contextlib.contextmanager
def spy_on_check_record():
    """Every call the tool makes to `telos_receipt.record.check_record`, as (receipt, witness, reading); an
    argument that was not passed is None. `seen.pins` counts the calls that passed `pins` at all."""
    module = record()
    real = module.check_record
    seen = Seen()

    def spy(*args, **kwargs):
        bound = inspect.signature(real).bind(*args, **kwargs).arguments
        seen.append((bound.get("receipt"), bound.get("witness"), bound.get("reading")))
        seen.pins += "pins" in bound
        return real(*args, **kwargs)

    with mock.patch.object(module, "check_record", spy):
        yield seen


@contextlib.contextmanager
def canary_default_pins():
    """TEST-ONLY SUBSTITUTION. The SDK's witnessed fixture is signed by a canary key, and the tool has no `pins`
    argument, so with the real default pins it reads NOT_WITNESSED. Here the default pins of the reader that
    `telos_receipt.record` has loaded are replaced by the canary PUBLIC pins for the length of the block. The tool
    is not patched and is called exactly as a client calls it. Reaches the SDK's private `_kit()`."""
    kit = record()._kit()
    assert not isinstance(kit, str), kit
    with mock.patch.object(kit.witness, "PINS", kit.witness.Pins(**ORACLE["canary_pins"])):
        yield


def padded(text, size):
    assert len(text.encode("utf-8")) <= size
    return text + " " * (size - len(text.encode("utf-8")))  # trailing JSON whitespace: the same document


def structured_part(collected):
    """The part of a collection that no framework renders: what each tool returned."""
    return old_tools_golden.render([[c["label"], c["tool"], c["arguments"], c["structured"]]
                                    for c in collected["calls"]])


# ------------------------------------------------------------------------------------------------ the fixtures

def test_fixtures_are_the_sdk_fixtures_byte_for_byte():
    assert PROVENANCE["source_commit"] == "804b38165fa8baebda3c200d8d6c75261fc6d4ec"
    found = {p.relative_to(FIXTURES).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(FIXTURES.rglob("*")) if p.is_file() and p.name != "PROVENANCE.json"}
    assert found == PROVENANCE["sha256"]


# ---------------------------------------------------------------------------------------------------------- M1

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_m1a_under_the_default_pins_the_answer_is_check_records_answer(name):
    expected = record().check_record(*raw(name))
    assert expected["ok"] is True and expected["pins"] == "default"
    assert expected["report"] == ORACLE["fixtures"][name]["pinned_key_cli"]  # what the kit reader printed
    assert expected["witness_state"] == "NOT_WITNESSED"  # also the canary-signed fixture: not the pinned key
    assert answer(*texts(name)) == expected
    assert protocol(supplied(name)) == expected


def test_m1a_the_canary_signed_fixture_reads_not_witnessed_under_the_default_pins():
    result = answer(*texts("witnessed"))
    assert (result["witness_state"], result["report"]["witness_reason"]) == ("NOT_WITNESSED", "WITNESS_FILE_INVALID")


def test_m1b_witnessed_is_carried_unchanged_under_test_only_canary_default_pins():
    before = answer(*texts("witnessed"))
    assert before["witness_state"] == "NOT_WITNESSED"
    with canary_default_pins():  # TEST-ONLY SUBSTITUTION of the reader's default pins; the tool is untouched
        expected = record().check_record(*raw("witnessed"))
        direct = answer(*texts("witnessed"))
        through_mcp = protocol(supplied("witnessed"))
        beside = answer(*texts("not_witnessed"))
    assert expected["witness_state"] == "WITNESSED"
    assert expected["report"] == ORACLE["fixtures"]["witnessed"]["canary_pins"]
    assert direct == expected
    assert through_mcp == expected
    assert direct["pins"] == "default"
    assert beside["witness_state"] == "NOT_WITNESSED"
    assert answer(*texts("witnessed")) == before  # the substitution is over


def test_m1_the_answer_carries_every_key_of_the_sdk_result():
    result = answer(*texts("not_witnessed"))
    assert sorted(result) == ["kit_reader", "ok", "pins", "report", "witness_state"]
    assert result["kit_reader"] == {"commit": record().KIT_COMMIT, "files": dict(record().KIT_FILES)}


# ------------------------------------------------------- A4: strings through the protocol, byte for byte

@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_a4_files_given_as_strings_through_call_tool_reach_check_record_byte_identical(name):
    receipt, witness, reading = raw(name)
    with spy_on_check_record() as seen:
        result = protocol(supplied(name))
    assert result != FRAMEWORK_REFUSED, "a witness row or a reading given as a string must reach the tool"
    assert seen == [(receipt, witness, reading)]
    assert result == record().check_record(receipt, witness, reading)


# Strings a "helpful" change would alter: a decomposed character (NFC/NFKC would compose it), a leading U+FEFF,
# CR LF and a lone CR, white space around, a composed character beside its decomposed form. The bytes expected
# are written out, not computed by the call under test.
EXACT_BYTES = {
    "decomposed e + U+0301": ('{"k": "e\u0301"}', b'{"k": "e\xcc\x81"}'),
    "composed U+00E9": ('{"k": "\u00e9"}', b'{"k": "\xc3\xa9"}'),
    "leading U+FEFF": ("\ufeff{}", b"\xef\xbb\xbf{}"),
    "U+FEFF inside and at the end": ('{"k": "\ufeff"}\ufeff', b'{"k": "\xef\xbb\xbf"}\xef\xbb\xbf'),
    "CR LF line ends": ('{"a": 1,\r\n "b": 2}\r\n', b'{"a": 1,\r\n "b": 2}\r\n'),
    "lone CR": ('{"a": 1}\r', b'{"a": 1}\r'),
    "compatibility character U+FB01": ('{"k": "\ufb01"}', b'{"k": "\xef\xac\x81"}'),
    "white space around": ("\t {} \n\n", b"\t {} \n\n"),
}


@pytest.mark.parametrize("label", list(EXACT_BYTES))
@pytest.mark.parametrize("position", [0, 1, 2])
def test_f1_the_exact_bytes_of_each_argument_reach_check_record_nothing_normalised(position, label):
    text, exact = EXACT_BYTES[label]
    files = list(texts("witnessed"))
    files[position] = text
    expected = [tuple(exact if index == position else files[index].encode("utf-8") for index in range(3))]
    with spy_on_check_record() as seen:
        direct = answer(*files)
    assert seen == expected, (ARGUMENTS[position], label)
    with spy_on_check_record() as seen:
        through_mcp = protocol(dict(zip(ARGUMENTS, files)))
    assert seen == expected, (ARGUMENTS[position], label)
    assert direct == through_mcp == record().check_record(*expected[0])


@pytest.mark.parametrize("value", ['{"a": 1}\n', "[1, 2]", "null", "12", '"quoted"', " ", "true", "not json",
                                   '  {"k": "’ é"}  ', '{"k": "e\u0301"}', "\ufeff{}",
                                   '{"a": 1}\r\n'])
def test_a4_any_non_empty_string_goes_through_untouched_in_either_optional_argument(value):
    receipt = texts("not_witnessed")[0]
    for argument in ("witness_json", "reading_json"):
        with spy_on_check_record() as seen:
            result = protocol({"receipt_json": receipt, argument: value})
        assert result != FRAMEWORK_REFUSED, (argument, value)
        given = value.encode("utf-8")
        expected = (receipt.encode("utf-8"), given, None) if argument == "witness_json" else (
            receipt.encode("utf-8"), None, given)
        assert seen == [expected], (argument, value)


def test_a4_the_empty_string_is_not_supplied_beside_a_supplied_file():
    receipt, witness, reading = texts("witnessed")
    receipt_only = record().check_record(receipt.encode("utf-8"))
    for call in (lambda: answer(receipt), lambda: answer(receipt, "", ""),
                 lambda: answer(receipt, witness_json="", reading_json=""),
                 lambda: protocol({"receipt_json": receipt}),
                 lambda: protocol({"receipt_json": receipt, "witness_json": "", "reading_json": ""})):
        with spy_on_check_record() as seen:
            assert call() == receipt_only
        assert seen == [(receipt.encode("utf-8"), None, None)]  # absent: None, never b""
    assert receipt_only["report"]["reading"] == {"state": "READING_ABSENT"}
    with spy_on_check_record() as seen:
        with_reading = answer(receipt, "", reading)
    assert seen == [(receipt.encode("utf-8"), None, reading.encode("utf-8"))]
    assert with_reading == record().check_record(receipt.encode("utf-8"), None, reading.encode("utf-8"))
    assert with_reading != receipt_only


def state_of(argument, result):
    """What the reader says of one optional file."""
    if argument == "witness_json":
        return result["witness_state"], result["report"].get("witness_reason")
    return result["report"]["reading"]["state"]


def pins_that_tell_the_three_apart(argument):
    """The witness row: the TEST-ONLY canary pins, under which the valid row reads WITNESSED (under the default
    pins it reads WITNESS_FILE_INVALID, the same as an invalid one). The reading: the real default pins (beside
    a WITNESSED row an absent and an invalid reading both read READING_CHANGED)."""
    return canary_default_pins() if argument == "witness_json" else contextlib.nullcontext()


VALID_FILE = {"witness_json": ("WITNESSED", None), "reading_json": "READING_SAVED"}
NOT_SUPPLIED = {"witness_json": ("NOT_WITNESSED", "WITNESS_NOT_REQUESTED"), "reading_json": "READING_ABSENT"}
INVALID_FILE = {"witness_json": ("NOT_WITNESSED", "WITNESS_FILE_INVALID"), "reading_json": "READING_INVALID"}


@pytest.mark.parametrize("invalid", ["not json", " ", "{}", "null", "0"])
@pytest.mark.parametrize("argument", ["witness_json", "reading_json"])
def test_a5_1_one_argument_omitted_empty_or_invalid_beside_valid_the_other_always_supplied(argument, invalid):
    """One of the two optional arguments at a time; the other is the valid file throughout (its bytes are
    checked at `check_record` in every call)."""
    valid = dict(zip(ARGUMENTS, texts("witnessed")))
    index = ARGUMENTS.index(argument)
    as_bytes = [valid[a].encode("utf-8") for a in ARGUMENTS]

    def sent(value):
        return tuple(value if i == index else as_bytes[i] for i in range(3))

    def both_ways(arguments):
        with spy_on_check_record() as seen:
            outcomes = (answer(**arguments), protocol(arguments))
        assert outcomes[0] == outcomes[1]
        assert len(seen) == 2 and seen[0] == seen[1]
        return outcomes[0], seen[0]

    with pins_that_tell_the_three_apart(argument):
        # beside: the valid file is supplied and read
        supplied_answer, supplied_bytes = both_ways(valid)
        assert supplied_bytes == sent(as_bytes[index])
        assert supplied_answer == record().check_record(*as_bytes)
        assert state_of(argument, supplied_answer) == VALID_FILE[argument]
        # omitted, and the empty string: absent (None) for this argument alone, and the same answer
        omitted, omitted_bytes = both_ways({a: valid[a] for a in ARGUMENTS if a != argument})
        empty, empty_bytes = both_ways(dict(valid, **{argument: ""}))
        assert omitted_bytes == empty_bytes == sent(None)
        assert omitted == empty == record().check_record(*sent(None))
        assert state_of(argument, omitted) == NOT_SUPPLIED[argument]
        # a non-empty invalid string: its exact bytes, the reader's own answer for them, never "not supplied"
        refused, refused_bytes = both_ways(dict(valid, **{argument: invalid}))
        assert refused_bytes == sent(invalid.encode("utf-8"))
        assert refused == record().check_record(*sent(invalid.encode("utf-8")))
        assert state_of(argument, refused) == INVALID_FILE[argument]
    assert len({json.dumps(r, sort_keys=True) for r in (supplied_answer, omitted, refused)}) == 3


def test_a5_1_the_sdk_still_tells_a_zero_byte_file_from_no_file_and_the_tool_cannot():
    receipt, witness, reading = raw("witnessed")
    for index, argument in ((1, "witness_json"), (2, "reading_json")):
        absent = [receipt, witness, reading]
        absent[index] = None
        zero_bytes = [receipt, witness, reading]
        zero_bytes[index] = b""
        with pins_that_tell_the_three_apart(argument):
            sdk_absent, sdk_zero = record().check_record(*absent), record().check_record(*zero_bytes)
            through_tool = answer(**dict(zip(ARGUMENTS, texts("witnessed")), **{argument: ""}))
        assert state_of(argument, sdk_absent) == NOT_SUPPLIED[argument]
        assert state_of(argument, sdk_zero) == INVALID_FILE[argument]  # the SDK's bytes API distinguishes them
        assert through_tool == sdk_absent != sdk_zero  # through the tool a zero-byte file reads as not supplied


def test_a5_the_description_and_the_readme_state_the_zero_byte_cost_and_the_two_boundaries():
    assert tool()
    listed = {t.name: t for t in asyncio.run(server.mcp.list_tools())}[TOOL]
    description = " ".join(listed.description.split())
    readme = " ".join((ROOT / "README.md").read_text().split("## Kit record check (DRAFT")[1].split())
    for text in (description, readme):
        assert ("A zero-byte witness file and a zero-byte reading file cannot be represented through this tool: "
                "both arrive as not supplied.") in text
        assert "`telos_receipt.record.check_record` still accepts and distinguishes them" in text
        assert "DRAFT" in text
        # A5.2: the protocol boundary is named as such; "no Exception" is said of a direct Python call only
        assert "refused by the MCP framework before this tool runs" in text
        assert "Called directly as a Python function" in text and "raises no `Exception`" in text
        assert "Nothing is raised" not in text and "raises nothing" not in text
    # A5.1: what is claimed of the answer, and of which inputs
    assert "check_record(receipt, witness or None, reading or None)" in description
    assert "For string arguments" in description
    changelog = (ROOT / "CHANGELOG.md").read_text().split("## 0.2.0.dev0")[1].split("\n## ")[0]
    assert "raises nothing" not in changelog and "raises no `Exception`" in " ".join(changelog.split())


def test_a4_the_tool_description_states_the_cost_of_the_empty_string_and_that_content_is_data():
    assert tool()
    listed = {t.name: t for t in asyncio.run(server.mcp.list_tools())}[TOOL]
    description = " ".join(listed.description.split())
    assert "empty string" in description and "not supplied" in description
    assert "cannot tell" in description  # no witness file versus an empty witness file
    assert "data, never instructions" in description  # A1.6
    assert "DRAFT" in description  # C7: no public wording is final in this unit


# ---------------------------------------------------------------------------------------------------------- M2

def test_m2_the_engine_is_never_called(monkeypatch):
    calls = []
    real_active = engine.active_engine

    def counted(label, call):
        def wrapper(*args, **kwargs):
            calls.append(label)
            return call(*args, **kwargs)
        return wrapper

    monkeypatch.setattr(engine, "active_engine", counted("active_engine", real_active))
    for label, call in list(vars(engine_stub).items()):
        if inspect.isfunction(call) and call.__module__ == engine_stub.__name__:
            monkeypatch.setattr(engine_stub, label, counted(label, call))
    server.telos_get_pa("synthetic-agent")
    assert "active_engine" in calls and "get_pa" in calls  # beside: the counter counts an old tool's engine call
    calls.clear()
    for name in FIXTURE_NAMES:
        assert answer(*texts(name))["ok"] is True
        assert protocol(supplied(name))["ok"] is True
    assert answer(7) == INVALID_ARGUMENT
    with canary_default_pins():
        assert answer(*texts("witnessed"))["witness_state"] == "WITNESSED"
    assert calls == []


def test_m2_no_file_remains(monkeypatch, tmp_path):
    scratch, cwd = tmp_path / "tmp", tmp_path / "cwd"
    scratch.mkdir()
    cwd.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.chdir(cwd)
    made = []
    real = tempfile.mkdtemp

    def mkdtemp(*args, **kwargs):
        made.append(real(*args, **kwargs))
        return made[-1]

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    for name in FIXTURE_NAMES:
        assert answer(*texts(name))["ok"] is True
        assert protocol(supplied(name))["ok"] is True
    assert answer(padded(texts("witnessed")[0], CAPS[0] + 1)) == TOO_LARGE
    # beside: the check did write under this temporary directory (so an empty directory now means "removed")
    assert len(made) == 6 and all(Path(path).parent == scratch for path in made)
    assert sorted(os.listdir(scratch)) == []
    assert sorted(os.listdir(cwd)) == []


def test_m2_sockets_and_processes_patched_to_raise_change_nothing(monkeypatch):
    expected = {name: answer(*texts(name)) for name in FIXTURE_NAMES}
    with canary_default_pins():
        expected_witnessed = answer(*texts("witnessed"))
    assert expected_witnessed["witness_state"] == "WITNESSED"
    used = []

    def refuse(*args, **kwargs):
        used.append(args)
        raise OSError("no network and no process in this test")

    for attribute in ("socket", "create_connection", "getaddrinfo", "socketpair", "create_server"):
        monkeypatch.setattr(socket, attribute, refuse)
    monkeypatch.setattr(subprocess, "Popen", refuse)
    monkeypatch.setattr(os, "system", refuse)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", 9))  # beside: the patch does raise
    used.clear()
    for name in FIXTURE_NAMES:
        assert answer(*texts(name)) == expected[name]
    with canary_default_pins():
        assert answer(*texts("witnessed")) == expected_witnessed
    assert used == []


# ---------------------------------------------------------------------------------------------------------- M3

@pytest.mark.parametrize("position", [0, 1, 2])
def test_m3_one_byte_over_a_cap_is_refused_beside_the_same_input_at_the_cap(position):
    files = list(texts("witnessed"))
    at_cap = list(files)
    at_cap[position] = padded(files[position], CAPS[position])
    over = list(files)
    over[position] = padded(files[position], CAPS[position] + 1)
    at_cap_bytes = tuple(text.encode("utf-8") for text in at_cap)
    assert len(at_cap_bytes[position]) == CAPS[position]
    expected = record().check_record(*at_cap_bytes)
    assert expected["ok"] is True
    assert answer(*at_cap) == expected
    assert protocol(dict(zip(ARGUMENTS, at_cap))) == expected
    assert answer(*over) == TOO_LARGE
    assert protocol(dict(zip(ARGUMENTS, over))) == TOO_LARGE


def test_m3_the_caps_are_in_utf8_bytes_not_characters():
    receipt = texts("witnessed")[0]
    characters = 3000  # under the row cap of 4,096 as characters
    one_byte_each, two_bytes_each = "e" * characters, "é" * characters
    assert len(two_bytes_each.encode("utf-8")) == 6000 > CAPS[1]
    expected = record().check_record(receipt.encode("utf-8"), one_byte_each.encode("utf-8"))
    assert expected["ok"] is True
    assert answer(receipt, one_byte_each) == expected
    assert answer(receipt, two_bytes_each) == TOO_LARGE
    assert protocol({"receipt_json": receipt, "witness_json": two_bytes_each}) == TOO_LARGE


class Text(str):
    """A str subclass: not the type the tool takes."""


@pytest.mark.parametrize("bad", [None, 7, 1.5, True, b'{"a": 1}', bytearray(b"{}"), ["{}"], {"a": 1},
                                 Text('{"a": 1}')], ids=repr)
@pytest.mark.parametrize("position", [0, 1, 2])
def test_m3_a_non_string_input_is_refused_beside_a_valid_call(position, bad):
    files = list(texts("witnessed"))
    assert answer(*files)["ok"] is True
    files[position] = bad
    with spy_on_check_record() as seen:
        assert answer(*files) == INVALID_ARGUMENT
    assert seen == []  # refused before the check


@pytest.mark.parametrize("position", [0, 1, 2])
def test_m3_a_string_utf8_cannot_carry_is_refused_beside_a_valid_call(position):
    files = list(texts("witnessed"))
    assert answer(*files)["ok"] is True
    files[position] = files[position][:-1] + "\ud800"  # a lone surrogate
    with spy_on_check_record() as seen:
        assert answer(*files) == INVALID_ARGUMENT
    assert seen == []


NOT_A_STRING = {"null": None, "number": 7, "boolean": True, "array": ["{}"], "object": {"a": 1}}


@pytest.mark.parametrize("kind", list(NOT_A_STRING))
@pytest.mark.parametrize("argument", ARGUMENTS)
def test_a5_2_protocol_boundary_call_tool_refuses_a_non_string_and_the_tool_is_not_invoked(argument, kind):
    """Protocol boundary, in-process `mcp.call_tool`. Measured on mcp 1.26.0 only."""
    arguments = supplied("witnessed")
    with count_tool_invocations() as invoked, spy_on_check_record() as seen:
        beside = protocol_outcome(arguments)
        assert beside[0] == "answer" and beside[1]["ok"] is True
        assert len(invoked) == 1 and len(seen) == 1  # beside: a valid call is counted
        outcome, message = protocol_outcome(dict(arguments, **{argument: NOT_A_STRING[kind]}))
    assert outcome == "framework error", message
    assert is_argument_validation_error(message, argument), message
    assert len(invoked) == 1, "the tool function was invoked for an argument that is not a string"
    assert len(seen) == 1


def test_a5_2_a_lone_surrogate_through_call_tool_gives_no_report():
    """In-process `call_tool` hands the Python str on, so this reaches the tool (measured on mcp 1.26.0) and gets
    the application boundary's answer. Required: no report, and `check_record` is not called."""
    arguments = supplied("witnessed")
    for argument in ARGUMENTS:
        with count_tool_invocations() as invoked, spy_on_check_record() as seen:
            outcome, detail = protocol_outcome(dict(arguments, **{argument: arguments[argument][:-1] + "\ud800"}))
        assert seen == []
        assert outcome == "framework error" or detail == INVALID_ARGUMENT, detail
        if old_tools_golden.made_with() == GOLDEN["made_with"]:  # the measured outcome under these versions
            assert (outcome, detail, len(invoked)) == ("answer", INVALID_ARGUMENT, 1)


def test_m3_an_empty_receipt_is_passed_on_as_it_is():
    with spy_on_check_record() as seen:
        result = answer("")
    assert seen == [(b"", None, None)]
    assert result == record().check_record(b"")
    # A5.1: `receipt_json` has no sentinel. Zero bytes get a report, not a refusal, and this is that report.
    assert (result["ok"], result["witness_state"], result["pins"]) == (True, "NOT_WITNESSED", "default")
    assert (result["report"]["structure"], result["report"]["errors"]) == ("INVALID", ["malformed record"])
    assert protocol({"receipt_json": ""}) == result


@pytest.mark.parametrize("failure", ["raises", "returns a list", "returns None", "returns a string"])
def test_m3_no_exception_and_no_non_dict_leaves_the_tool_beside_a_normal_call(failure, monkeypatch):
    files = texts("witnessed")
    normal = answer(*files)
    assert normal["ok"] is True

    def broken(*args, **kwargs):
        if failure == "raises":
            raise RuntimeError("an SDK that breaks its own promise")
        return {"returns a list": [normal], "returns None": None, "returns a string": json.dumps(normal)}[failure]

    monkeypatch.setattr(record(), "check_record", broken)
    assert answer(*files) == TOOL_UNAVAILABLE
    assert protocol(supplied("witnessed")) == TOOL_UNAVAILABLE
    monkeypatch.undo()
    assert answer(*files) == normal


# ---------------------------------------------------------------------------------------------------------- M4

def test_m4_the_tool_list_is_the_six_old_names_plus_the_new_one():
    names = [t.name for t in asyncio.run(server.mcp.list_tools())]
    assert sorted(names) == sorted((*old_tools_golden.OLD_TOOLS, TOOL))
    assert len(names) == 7


def test_m4_the_six_old_tools_return_what_0_1_2_returned():
    assert GOLDEN["base_commit"] == "b53473a3d6a48ad8ab42b7c8d3d20d1eff631bd3"
    assert sorted(GOLDEN["tools"]) == sorted(old_tools_golden.OLD_TOOLS)
    assert {c["tool"] for c in GOLDEN["calls"]} == set(old_tools_golden.OLD_TOOLS)
    assert structured_part(old_tools_golden.collect_in_process()) == structured_part(GOLDEN)


def test_m4_the_six_old_tools_are_listed_and_rendered_byte_identically_to_0_1_2():
    here = old_tools_golden.made_with()
    if here != GOLDEN["made_with"]:
        pytest.skip(f"old_tools_golden.json was made with {GOLDEN['made_with']}, this is {here}: the listing and "
                    "the text blocks are rendered by those packages. Make the file again from b53473a here.")
    assert old_tools_golden.render(old_tools_golden.collect_in_process()) == GOLDEN_BYTES


# ------------------------------------------------------------------------------------------ real stdio, M4, M5

BOOT = r'''
import sys
mode = sys.argv[1]
if mode != "normal":
    class Unimportable:
        @staticmethod
        def find_spec(name, path=None, target=None):
            if name == "telos_receipt.record":
                if mode == "python_3_10":
                    raise RuntimeError("telos_receipt.record needs Python 3.11 or later")
                raise ModuleNotFoundError("No module named 'telos_receipt.record'", name=name)
            return None
    sys.meta_path.insert(0, Unimportable)
import old_tools_golden
old_tools_golden.freeze()
from telos_mcp import server
if len(sys.argv) > 2:  # count every invocation of the registered tool function in a file the test reads
    registered = server.mcp._tool_manager.get_tool("telos_verify_kit_record")
    real = registered.fn
    def counted(*args, **kwargs):
        with open(sys.argv[2], "a") as log:
            log.write("invoked\n")
        return real(*args, **kwargs)
    registered.fn = counted
server.main()
'''
MODES = ("normal", "sdk_without_record", "python_3_10")


def over_stdio(mode):
    """A real server process over stdio, in one of MODES: what it lists, what the six old tools answer (frozen
    clock) and what the new tool answers. Never reads package metadata. A server that does not start or does not
    answer is a failed guarantee."""
    params = StdioServerParameters(
        command=sys.executable, args=["-B", "-c", BOOT, mode], cwd=str(ROOT),
        env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONPATH": os.pathsep.join((str(ROOT), str(TESTS), os.environ.get("PYTHONPATH", "")))})

    async def exercise():
        async with stdio_client(params, errlog=sys.stderr) as streams, ClientSession(*streams) as session:
            started = await session.initialize()
            listed = (await session.list_tools()).tools
            old = await old_tools_golden.collect_session(session)
            kit = {}
            for name in FIXTURE_NAMES:
                result = await session.call_tool(TOOL, supplied(name))
                kit[name] = ("TOOL ERROR: " + result.content[0].text if result.isError
                             else (result.structuredContent, json.loads(result.content[0].text)))
            return {"server": (started.serverInfo.name, started.serverInfo.version),
                    "names": [t.name for t in listed], "old": old, "kit": kit}

    try:
        return asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    except (Exception, GROUP) as e:  # noqa: BLE001
        pytest.fail(f"the server did not start or did not answer over stdio ({mode}): {type(e).__name__}: {e}")


@pytest.fixture(scope="module")
def stdio():
    cache = {}

    def get(mode):
        if mode not in cache:
            cache[mode] = over_stdio(mode)
        return cache[mode]

    return get


def stdio_parameters(*boot_arguments):
    return StdioServerParameters(
        command=sys.executable, args=["-B", "-c", BOOT, *boot_arguments], cwd=str(ROOT),
        env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONDONTWRITEBYTECODE": "1",
             "PYTHONPATH": os.pathsep.join((str(ROOT), str(TESTS), os.environ.get("PYTHONPATH", "")))})


@pytest.fixture(scope="module")
def stdio_boundary(tmp_path_factory):
    """One real server over stdio whose registered tool function is counted: a valid call, then every kind of
    non-string for every argument, then a valid call again. {label: (isError, text, structured, invocations)},
    or, when the server did not start or did not answer, a sentence saying so (each test then fails by its own
    assertion, not by a setup error)."""
    log = tmp_path_factory.mktemp("invocations") / "tool-invocations.log"
    log.write_text("")
    valid = supplied("witnessed")
    cases = [("valid first", valid)]
    cases += [((argument, kind), dict(valid, **{argument: value}))
              for argument in ARGUMENTS for kind, value in NOT_A_STRING.items()]
    cases += [("valid last", valid)]

    async def exercise():
        seen = {}
        async with (stdio_client(stdio_parameters("normal", str(log)), errlog=sys.stderr) as streams,
                    ClientSession(*streams) as session):
            await session.initialize()
            for label, arguments in cases:
                before = len(log.read_text().splitlines())
                result = await session.call_tool(TOOL, arguments)
                seen[label] = (result.isError, result.content[0].text, result.structuredContent,
                               len(log.read_text().splitlines()) - before)
        return seen

    try:
        return asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    except (Exception, GROUP) as e:  # noqa: BLE001
        return f"the server did not start or did not answer over stdio: {type(e).__name__}: {e}"


@pytest.mark.parametrize("kind", list(NOT_A_STRING))
@pytest.mark.parametrize("argument", ARGUMENTS)
def test_a5_2_protocol_boundary_stdio_refuses_a_non_string_and_the_tool_is_not_invoked(argument, kind, stdio_boundary):
    """Protocol boundary, real stdio. Measured on mcp 1.26.0 only."""
    assert isinstance(stdio_boundary, dict), stdio_boundary
    expected = record().check_record(*raw("witnessed"))
    for beside in ("valid first", "valid last"):  # beside: a valid call is answered and counted, before and after
        assert stdio_boundary[beside][0] is False and stdio_boundary[beside][2:] == (expected, 1), beside
    is_error, text, structured, invocations = stdio_boundary[(argument, kind)]
    assert is_error is True, text
    assert is_argument_validation_error(text, argument), text
    assert structured is None
    assert invocations == 0, "the tool function was invoked for an argument that is not a string"


@pytest.mark.parametrize("argument", ARGUMENTS)
def test_a5_2_a_lone_surrogate_over_stdio_gives_no_report(argument, tmp_path):
    """Whatever the transport does with it. Measured on mcp 1.26.0: the client cannot send it (the call ends in
    an error on the client side) and the tool function is never invoked. Required: no report."""
    log = tmp_path / "tool-invocations.log"
    log.write_text("")
    arguments = supplied("witnessed")
    arguments[argument] = arguments[argument][:-1] + "\ud800"

    async def exercise():
        async with (stdio_client(stdio_parameters("normal", str(log)), errlog=sys.stderr) as streams,
                    ClientSession(*streams) as session):
            await session.initialize()
            result = await session.call_tool(TOOL, arguments)
            return result.isError, result.content[0].text, result.structuredContent

    try:
        outcome = ("answered",) + asyncio.run(asyncio.wait_for(exercise(), timeout=60))
    except (Exception, GROUP) as e:  # noqa: BLE001
        outcome = ("client or transport error", type(e).__name__)
    invocations = len(log.read_text().splitlines())
    if outcome[0] == "answered":
        assert outcome[1] is True or outcome[3] == INVALID_ARGUMENT, outcome  # an error or the refusal: no report
    if old_tools_golden.made_with() == GOLDEN["made_with"]:  # the measured outcome under these versions
        assert (outcome[0], invocations) == ("client or transport error", 0), outcome


@pytest.mark.parametrize("mode", MODES)
def test_m4_m5_the_server_starts_and_lists_seven_tools_over_stdio(mode, stdio):
    seen = stdio(mode)
    assert seen["server"] == ("telos-governance", __version__)
    assert sorted(seen["names"]) == sorted((*old_tools_golden.OLD_TOOLS, TOOL))
    assert len(seen["names"]) == 7


@pytest.mark.parametrize("mode", MODES)
def test_m4_m5_the_six_old_tools_answer_as_0_1_2_over_stdio(mode, stdio):
    seen = stdio(mode)
    assert structured_part(seen["old"]) == structured_part(GOLDEN)
    if old_tools_golden.made_with() == GOLDEN["made_with"]:
        assert old_tools_golden.render(seen["old"]) == GOLDEN_BYTES  # listing and text blocks too


def test_m1_a4_the_new_tool_answers_as_check_record_over_stdio(stdio):
    seen = stdio("normal")
    for name in FIXTURE_NAMES:
        expected = record().check_record(*raw(name))
        assert expected["ok"] is True
        assert seen["kit"][name] == (expected, expected), name


@pytest.mark.parametrize("mode", ["sdk_without_record", "python_3_10"])
def test_m5_the_new_tool_says_tool_unavailable_over_stdio_beside_a_normal_environment(mode, stdio):
    normal = stdio("normal")
    for name in FIXTURE_NAMES:
        assert normal["kit"][name] == (record().check_record(*raw(name)),) * 2, name  # beside: a report
    seen = stdio(mode)
    for name in FIXTURE_NAMES:
        assert seen["kit"][name] == (TOOL_UNAVAILABLE, TOOL_UNAVAILABLE), name


class Unimportable:
    """A finder under which `telos_receipt.record` raises what it raises on Python 3.10."""

    @staticmethod
    def find_spec(name, path=None, target=None):
        if name == "telos_receipt.record":
            raise RuntimeError("telos_receipt.record needs Python 3.11 or later")
        return None


@pytest.mark.parametrize("how", ["an SDK without record", "Python 3.10"])
def test_m5_in_process_tool_unavailable_and_old_tools_unchanged_beside_a_normal_environment(how, monkeypatch):
    files = texts("witnessed")
    normal = answer(*files)
    assert normal["ok"] is True
    record()
    if how == "an SDK without record":
        monkeypatch.setitem(sys.modules, "telos_receipt.record", None)  # import raises ModuleNotFoundError
    else:
        monkeypatch.delitem(sys.modules, "telos_receipt.record")
        monkeypatch.setattr(sys, "meta_path", [Unimportable, *sys.meta_path])
    with pytest.raises((ImportError, RuntimeError)):
        importlib.import_module("telos_receipt.record")  # beside: it is unimportable here
    assert answer(*files) == TOOL_UNAVAILABLE
    assert answer(files[0]) == TOOL_UNAVAILABLE
    assert protocol(supplied("witnessed")) == TOOL_UNAVAILABLE
    assert sorted(answer(*files)) == ["ok", "reason"]  # exactly two keys: no `pins`, no report
    assert structured_part(old_tools_golden.collect_in_process()) == structured_part(GOLDEN)
    monkeypatch.undo()
    assert answer(*files) == normal


def test_a1_4_importing_the_server_does_not_import_the_record_module_or_the_reader():
    code = ("import sys\nimport telos_mcp.server as s\nimport asyncio\n"
            "names = sorted(t.name for t in asyncio.run(s.mcp.list_tools()))\n"
            "loaded = sorted(n for n in sys.modules if n == 'telos_receipt.record' or '_kit_vendor' in n "
            "or n.startswith('h0a'))\nprint(len(names), loaded)\n")
    done = subprocess.run([sys.executable, "-B", "-c", code], cwd=str(ROOT), capture_output=True, text=True,
                          timeout=60, check=False,
                          env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONDONTWRITEBYTECODE": "1",
                               "PYTHONPATH": os.pathsep.join((str(ROOT), os.environ.get("PYTHONPATH", "")))})
    assert (done.returncode, done.stdout.strip()) == (0, "7 []"), done.stderr


# ---------------------------------------------------------------------------------------------------------- M6

def test_m6_the_tool_takes_three_string_arguments_and_no_pins():
    signature = inspect.signature(tool())
    assert list(signature.parameters) == list(ARGUMENTS)
    assert [p.default for p in signature.parameters.values()] == [inspect.Parameter.empty, "", ""]
    assert all(p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for p in signature.parameters.values())
    schema = {t.name: t for t in asyncio.run(server.mcp.list_tools())}[TOOL].inputSchema
    assert sorted(schema["properties"]) == sorted(ARGUMENTS)
    assert schema["required"] == ["receipt_json"]
    assert [schema["properties"][a]["type"] for a in ARGUMENTS] == ["string"] * 3  # exactly str: never pre-parsed


def test_m6_every_report_says_default_pins_also_when_a_caller_sends_pins():
    canary = dict(ORACLE["canary_pins"])
    for name in FIXTURE_NAMES:
        plain = protocol(supplied(name))
        assert plain["ok"] is True and plain["pins"] == "default"
        assert answer(*texts(name))["pins"] == "default"
        with spy_on_check_record() as seen:
            sent = protocol(dict(supplied(name), pins=canary))
        assert sent in (plain, FRAMEWORK_REFUSED)  # an unknown argument is dropped or refused, never used
        assert seen.pins == 0
    with canary_default_pins():
        assert answer(*texts("witnessed"))["pins"] == "default"


def test_m6_the_unavailable_refusal_has_exactly_two_keys(monkeypatch):
    assert answer(*texts("witnessed"))["pins"] == "default"
    record()
    monkeypatch.setitem(sys.modules, "telos_receipt.record", None)
    refusal = answer(*texts("witnessed"))
    assert refusal == TOOL_UNAVAILABLE and list(refusal) == ["ok", "reason"]


# ------------------------------------------------------------------------------------------- version, C7 drafts

def test_local_version_is_0_2_0_dev0_everywhere_it_is_stated():
    assert __version__ == "0.2.0.dev0"
    project = (ROOT / "pyproject.toml").read_text()
    assert '\nversion = "0.2.0.dev0"\n' in project
    assert '"telos-receipt[native]>=0.2.0.dev0,<0.3",' in project
    assert "telos-receipt[native]>=0.1.1,<0.2" not in project
    manifest = json.loads((ROOT / "server.json").read_text())
    assert manifest["version"] == manifest["packages"][0]["version"] == "0.2.0.dev0"


def test_python_floor_and_mcp_requirement_are_unchanged():
    project = (ROOT / "pyproject.toml").read_text()
    assert '\nrequires-python = ">=3.10"\n' in project
    assert '\n    "mcp>=1.30.0,<2",\n' in project
    assert version("mcp")  # the package under which this run was made is recorded in the log header


def test_new_public_lines_are_marked_draft():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    entry = changelog.split("## 0.1.2")[0]
    assert "## 0.2.0.dev0 (DRAFT" in entry
    lines = [line for line in entry.splitlines() if line.startswith("- ")]
    assert lines and all(line.startswith("- DRAFT: ") for line in lines)
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Kit record check (DRAFT")[1]
    assert TOOL in section and "tool_unavailable" in section
    assert "## Kit record check (DRAFT" not in readme.split("## Native receipt verification scope")[0]


def test_a6_the_wording_keeps_the_three_limits_tes_named_at_r2():
    """r3 (TES 2026-11-12, three LOW): the "no Exception" line names the uncaught MemoryError, the tool description
    carries the measured mcp version, and "nothing left on disk" keeps the SDK's `residual` cleanup-failure case."""
    assert tool()
    listed = {t.name: t for t in asyncio.run(server.mcp.list_tools())}[TOOL]
    description = " ".join(listed.description.split())
    readme = " ".join((ROOT / "README.md").read_text().split("## Kit record check (DRAFT")[1].split())
    changelog = " ".join((ROOT / "CHANGELOG.md").read_text().split("## 0.2.0.dev0")[1].split("\n## ")[0].split())
    for text in (description, readme, changelog):
        assert "raises no `Exception`, with one case no test covers: a `MemoryError`" in text
        assert "measured with `mcp` 1.26.0 only" in text
        assert '`"residual": true`' in text
        assert "every value with a dict and raises no `Exception`." not in text
