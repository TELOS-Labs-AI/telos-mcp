"""Stub tools say they are stubs and promise nothing they cannot serve (M1, M3)."""

import asyncio
import json
from pathlib import Path

import pytest

from telos_mcp import server

WINDOW = {"start_iso": "2026-04-25T00:00:00Z", "end_iso": "2026-04-26T00:00:00Z"}
REPLAY = {"receipt_id": "synthetic-receipt", "alt_config_path": "alt.yaml"}


@pytest.fixture(autouse=True)
def stub_engine(monkeypatch):
    monkeypatch.setenv("TELOS_MCP_ENGINE", "stub")


def _structured(name, args):
    _content, structured = asyncio.run(server.mcp.call_tool(name, args))
    return structured


def test_replay_reports_that_nothing_was_queued():
    result = _structured("telos_replay", REPLAY)
    assert result["stub"] is True
    assert result["status"] == "stub_not_queued"
    assert result["receipt_id"] == REPLAY["receipt_id"]
    assert result["alt_config_path"] == REPLAY["alt_config_path"]
    assert result["job_id"].startswith("ccrs::")


def test_replay_offers_no_uri_or_runtime_for_a_job_that_does_not_exist():
    result = _structured("telos_replay", REPLAY)
    assert "result_uri" not in result
    assert "estimated_runtime_seconds" not in result
    assert "queued_at" not in result


def test_every_uri_a_tool_returns_is_served():
    # Valid neighbour: a registered template resolves.
    asyncio.run(server.mcp.read_resource("telos://centroids/purpose"))
    for name, args in (("telos_replay", REPLAY), ("telos_audit", WINDOW)):
        for value in json.dumps(_structured(name, args)).split('"'):
            if value.startswith("telos://"):
                asyncio.run(server.mcp.read_resource(value))  # raises if unserved


def test_replay_description_says_nothing_runs():
    tools = asyncio.run(server.mcp.list_tools())
    description = next(t.description for t in tools if t.name == "telos_replay")
    assert "telos://replay/" not in description
    assert "nothing is queued" in " ".join(description.split()).lower()


def test_audit_result_and_every_entry_are_flagged_stub():
    result = _structured("telos_audit", WINDOW)
    assert result["count"] == 3
    assert result["stub"] is True
    assert all(entry["stub"] is True for entry in result["entries"])


def test_audit_resource_entries_are_flagged_stub():
    contents = asyncio.run(server.mcp.read_resource("telos://audit/2026-04-25"))
    entries = json.loads(next(iter(contents)).content)
    assert len(entries) == 3
    assert all(entry["stub"] is True for entry in entries)


def test_empty_audit_window_is_still_flagged_stub():
    result = _structured("telos_audit", {"start_iso": "2026-04-26T00:00:00Z",
                                         "end_iso": "2026-04-25T00:00:00Z"})
    assert result["entries"] == []
    assert result["stub"] is True


def test_audit_walkthrough_prompt_tells_the_model_about_stub_entries():
    text = server.audit_walkthrough("2026-04-25", "2026-04-26")
    assert "`stub: true`" in text
    assert "synthetic" in text


def test_readme_rows_match_stub_behaviour():
    text = " ".join((Path(__file__).resolve().parents[1] / "README.md").read_text().split())
    assert "Queue a CCRS counterfactual replay" not in text
    assert "nothing is queued" in text.lower()
    assert "synthetic entries flagged `stub: true`" in text


def test_server_instructions_say_replays_queue_nothing():
    # Beside the tool's own response: what the server tells the client at
    # initialization must agree with what telos_replay returns.
    assert _structured("telos_replay", REPLAY)["status"] == "stub_not_queued"
    text = " ".join(server.mcp.instructions.split())
    assert "queue CCRS" not in text
    assert "nothing is queued" in text.lower()


def test_real_stdio_initialization_text_agrees_with_the_replay_response():
    import os
    import sys

    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def session_run():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "telos_mcp.server"],
            env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONPATH": ""},
        )
        async with (
            stdio_client(params, errlog=sys.stderr) as (read, write),
            ClientSession(read, write) as session,
        ):
            init = await session.initialize()
            replay = await session.call_tool("telos_replay", REPLAY)
            return init.instructions, replay.structuredContent

    instructions, replay = asyncio.run(asyncio.wait_for(session_run(), timeout=20))
    assert replay["status"] == "stub_not_queued"
    text = " ".join(instructions.split())
    assert "queue CCRS" not in text
    assert "nothing is queued" in text.lower()


def _parse(ts):
    from datetime import datetime

    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


@pytest.mark.parametrize(
    "start, end",
    [
        ("2026-04-25T00:00:00Z", "2026-04-26T00:00:00Z"),
        ("2026-04-25T00:00:00.100Z", "2026-04-25T00:00:00.500Z"),
        ("2026-04-25T00:00:59.900Z", "2026-04-25T00:01:00.300Z"),
    ],
    ids=["whole-seconds", "fraction-within-one-second", "fraction-across-a-second"],
)
def test_every_audit_entry_lies_inside_its_window(start, end):
    entries = _structured("telos_audit", {"start_iso": start, "end_iso": end})["entries"]
    assert len(entries) == 3
    for entry in entries:
        assert _parse(start) < _parse(entry["timestamp"]) < _parse(end), entry["timestamp"]


def test_whole_second_windows_keep_whole_second_timestamps():
    entries = _structured("telos_audit", WINDOW)["entries"]
    assert [e["timestamp"] for e in entries] == [
        "2026-04-25T06:00:00+00:00", "2026-04-25T12:00:00+00:00", "2026-04-25T18:00:00+00:00",
    ]


@pytest.mark.parametrize(
    "start, end, count",
    [
        ("2026-04-25T00:00:00Z", "2026-04-26T00:00:00Z", 3),
        ("2026-04-25T00:00:00.100Z", "2026-04-25T00:00:00.500Z", 3),
        ("2026-04-25T00:00:00.000004Z", "2026-04-25T00:00:00.000008Z", 3),
        ("2026-04-25T00:00:00.000001Z", "2026-04-25T00:00:00.000004Z", 2),
        ("2026-04-25T00:00:00.000001Z", "2026-04-25T00:00:00.000003Z", 1),
        ("2026-04-25T00:00:00.000001Z", "2026-04-25T00:00:00.000002Z", 0),
    ],
    ids=["normal", "fraction-100-500ms", "4us", "3us", "2us", "1us"],
)
def test_narrow_windows_return_fewer_entries_never_one_outside(start, end, count):
    # Beside a normal window: a window too narrow for three distinct interior
    # timestamps at microsecond resolution returns fewer, never one on or
    # outside a bound.
    result = _structured("telos_audit", {"start_iso": start, "end_iso": end})
    stamps = [_parse(e["timestamp"]) for e in result["entries"]]
    assert all(_parse(start) < s < _parse(end) for s in stamps), stamps
    assert stamps == sorted(set(stamps))
    assert result["count"] == len(stamps) == count
    assert result["stub"] is True


def test_audit_docstrings_say_narrow_windows_return_fewer_entries():
    from telos_mcp import engine_stub

    stub_doc = " ".join(engine_stub.audit_window.__doc__.split())
    assert "Stub: three deterministic, invented entries" not in stub_doc
    assert "returns fewer entries, or none" in stub_doc
    tools = asyncio.run(server.mcp.list_tools())
    tool_doc = " ".join(next(t.description for t in tools if t.name == "telos_audit").split())
    assert "three invented entries for any valid window" not in tool_doc
    assert "fewer for a window too narrow" in tool_doc
