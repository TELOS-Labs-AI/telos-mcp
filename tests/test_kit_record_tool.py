"""`telos_verify_kit_record`: the kit record check of `telos_receipt.record`, carried over MCP (M1 to M6).

M1 the tool's answer is `telos_receipt.record.check_record`'s answer, unchanged: (a) under the real default pins,
   (b) WITNESSED under a TEST-ONLY substitution of the loaded reader's default pins by the canary pins.
A4 a witness row and a reading given as strings through `mcp.call_tool` reach `check_record` byte for byte; the
   empty string is "not supplied".
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


@pytest.mark.parametrize("value", ['{"a": 1}\n', "[1, 2]", "null", "12", '"quoted"', " ", "true", "not json",
                                   '  {"k": "’ é"}  '])
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


@pytest.mark.parametrize("bad", [None, 7, ["{}"], {"a": 1}], ids=repr)
@pytest.mark.parametrize("argument", ARGUMENTS)
def test_m3_a_non_string_argument_through_the_protocol_never_gives_a_report(argument, bad):
    arguments = supplied("witnessed")
    assert protocol(arguments)["ok"] is True
    with spy_on_check_record() as seen:
        outcome = protocol(dict(arguments, **{argument: bad}))
    assert outcome in (FRAMEWORK_REFUSED, INVALID_ARGUMENT)
    assert seen == []


def test_m3_an_empty_receipt_is_passed_on_as_it_is():
    with spy_on_check_record() as seen:
        result = answer("")
    assert seen == [(b"", None, None)]
    assert result == record().check_record(b"")


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
