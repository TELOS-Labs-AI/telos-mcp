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
