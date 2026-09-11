"""Public five-dimension contract, using synthetic unsigned fixtures only."""

import asyncio
import json
from pathlib import Path

import pytest

from telos_mcp import engine, engine_stub, server

EXPECTED_DIMENSIONS = ("purpose", "scope", "boundary", "tool", "chain")
SYNTHETIC_ACTION = {
    "action_name": "synthetic_test_only",
    "action_params": {"path": "fixture.txt"},
    "agent_id": "synthetic-agent",
}


@pytest.fixture(autouse=True)
def stub_engine(monkeypatch):
    monkeypatch.setenv("TELOS_MCP_ENGINE", "stub")


@pytest.mark.parametrize("params", [{}, {"path": "fixture.txt"}, {"nested": [1, None, True]}])
def test_score_emits_exactly_five_dimensions(params):
    result = server.telos_score("synthetic_test_only", params, "synthetic-agent")
    assert tuple(result["scores"]) == EXPECTED_DIMENSIONS
    assert result["stub"] is True


def test_retained_fixture_scores_and_verdict_are_unchanged():
    result = server.telos_score(**SYNTHETIC_ACTION)
    assert {name: result["scores"][name] for name in EXPECTED_DIMENSIONS} == {
        "purpose": 0.259,
        "scope": 0.4928,
        "boundary": 0.5267,
        "tool": 0.5419,
        "chain": 0.4064,
    }
    assert result["verdict"] == "ESCALATE"


def test_composite_averages_only_the_five_fixture_scores():
    result = server.telos_score(**SYNTHETIC_ACTION)
    assert result["composite_score"] == 0.4454
    assert result["receipt"]["payload"]["composite_score"] == 0.4454


def test_receipt_covers_the_five_scores_and_still_verifies_unsigned():
    result = server.telos_score(**SYNTHETIC_ACTION)
    receipt = result["receipt"]
    assert tuple(receipt["payload"]["scores"]) == EXPECTED_DIMENSIONS
    assert receipt["payload"]["scores"] == result["scores"]
    assert receipt["signature"] is None
    assert receipt["signing_status"] == "unsigned_integrity_hash"
    verified = server.telos_verify(json.dumps(receipt))
    assert verified["match"] is True
    assert verified["signature_verified"] is False


def test_pa_advertises_only_the_five_centroid_dimensions():
    assert server.telos_get_pa("synthetic-agent")["centroid_dimensions"] == list(
        EXPECTED_DIMENSIONS
    )


@pytest.mark.parametrize("dimension", EXPECTED_DIMENSIONS)
def test_each_current_centroid_is_readable(dimension):
    result = json.loads(server.centroids_resource(dimension))
    assert "error" not in result
    assert result["dimension"] == dimension
    assert result["compiled_from"] == "stub-corpus"


@pytest.mark.parametrize("dimension", ["codebase_fidelity", "unknown-synthetic-dimension"])
def test_deprecated_and_unknown_centroids_refuse_with_the_exact_reason(dimension):
    assert json.loads(server.centroids_resource(dimension)) == {
        "error": f"unknown dimension: {dimension}",
        "valid_dimensions": list(EXPECTED_DIMENSIONS),
    }


def test_mcp_tool_serialization_contains_only_five_dimensions():
    response = asyncio.run(server.mcp.call_tool("telos_score", SYNTHETIC_ACTION))
    content, structured = response
    text_result = json.loads(content[0].text)
    for result in (text_result, structured):
        assert tuple(result["scores"]) == EXPECTED_DIMENSIONS
        assert tuple(result["receipt"]["payload"]["scores"]) == EXPECTED_DIMENSIONS
        assert result["composite_score"] == 0.4454


def test_mcp_centroid_resource_refuses_the_deprecated_dimension():
    resources = asyncio.run(server.mcp.read_resource("telos://centroids/codebase_fidelity"))
    assert json.loads(next(iter(resources)).content) == {
        "error": "unknown dimension: codebase_fidelity",
        "valid_dimensions": list(EXPECTED_DIMENSIONS),
    }


def test_registered_mcp_descriptions_match_the_five_dimension_surface():
    tools = asyncio.run(server.mcp.list_tools())
    description = next(tool.description for tool in tools if tool.name == "telos_score")
    assert "5-dimension" in description
    assert "codebase_fidelity" not in description
    templates = asyncio.run(server.mcp.list_resource_templates())
    description = next(
        template.description for template in templates
        if template.uriTemplate == "telos://centroids/{dimension}"
    )
    assert "Valid dimensions: purpose, scope, boundary, tool, chain." in description
    assert "codebase_fidelity" not in description


def test_readme_agrees_with_emitted_dimensions():
    text = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    assert "codebase_fidelity" not in text
    assert "the five canonical centroid dimensions" in " ".join(text.split())
    for dimension in EXPECTED_DIMENSIONS:
        assert f"`{dimension}`" in text


def test_dispatcher_default_remains_the_stub(monkeypatch):
    monkeypatch.delenv("TELOS_MCP_ENGINE", raising=False)
    assert engine.active_engine() is engine_stub
