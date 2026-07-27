"""telos-mcp server: MCP protocol surface for TELOS governance.

Exposes 5 tools, 3 resource templates, and 2 prompts via FastMCP. All engine
calls route through `engine_stub` in v0.1; v0.2 swaps in real `telos-gov`
calls (see engine_stub.py for the swap protocol).

Run:
    python -m telos_mcp.server          # stdio transport (Claude Desktop default)
    mcp dev telos_mcp/server.py         # dev/inspector mode

The module-level `mcp` object is the FastMCP instance; tooling (mcp install,
mcp dev, ASGI mounts) discovers it by name.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from telos_mcp import engine

# Engine calls route through the dispatcher (engine.py). With the default flag
# (TELOS_MCP_ENGINE unset / "stub") active_engine() returns the engine_stub
# module object unchanged -- object identity, so the dispatcher adds no
# indirection over a direct stub call. Setting the flag to "real" loads the
# dormant real-engine seam, which fails closed until wired.

mcp = FastMCP(
    name="telos-governance",
    instructions=(
        "TELOS governance server. Score proposed agent actions, verify receipts, "
        "inspect Purpose Anchors, query the audit chain, and queue CCRS "
        "counterfactual replays. Returns a verdict in {EXECUTE, CLARIFY, "
        "ESCALATE} for every scored action. The stub engine produces synthetic "
        "scores and UNSIGNED integrity-hash receipts (signature: null, "
        "signing_status: unsigned_integrity_hash) in the shared telos-receipt "
        "envelope; the real engine and a real signer wire in behind the same "
        "shape with no schema break."
    ),
)


# =========================================================================
# Tools
# =========================================================================

@mcp.tool()
def telos_score(action_name: str, action_params: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """Score a proposed agent action against the active Purpose Anchor.

    Returns a verdict (EXECUTE / CLARIFY / ESCALATE) plus a 6-dimension
    score breakdown across purpose, scope, boundary, tool, chain, and
    codebase_fidelity. Each call also mints an unsigned integrity-hash
    receipt (shared telos-receipt envelope) that `telos_verify` -- and the
    telos-trust-surface -- can verify with no translation.

    Args:
        action_name: Name of the action being proposed (e.g. "write_file").
        action_params: Parameter dict the agent intends to pass to the action.
        agent_id: Stable identifier of the agent proposing the action.

    Returns:
        Dict with keys: verdict, composite_score, scores, agent_id,
        action_name, receipt, stub, engine.
    """
    return engine.active_engine().score_action(action_name=action_name, action_params=action_params, agent_id=agent_id)


@mcp.tool()
def telos_verify(receipt_json: str) -> dict[str, Any]:
    """Verify an unsigned integrity-hash receipt offline.

    Recomputes the receipt's integrity hash over its canonical payload using
    the shared telos-receipt contract -- the same verifier the trust surface
    runs -- so the answer matches end-to-end. Key-free; not a signature check.

    Args:
        receipt_json: The receipt to verify, either as a JSON string or as
            a JSON object (clients may pass either; both are accepted).

    Returns:
        Dict with keys: match (bool), stated_integrity_hash,
        recomputed_integrity_hash, covered_fields, signing_status, note, reason.
    """
    return engine.active_engine().verify_receipt(receipt_json)


@mcp.tool()
def telos_get_pa(agent_id: str) -> dict[str, Any]:
    """Return the active Purpose Anchor for an agent.

    The PA is the governance contract: purpose statement, hard boundaries,
    declared scope, allowed tool list, and the centroid dimensions used to
    score the agent's actions.

    Args:
        agent_id: Stable identifier of the agent whose PA to load.

    Returns:
        Dict with keys: agent_id, pa_id, purpose, boundaries, scope,
        allowed_tools, centroid_dimensions, compiled_at, stub.
    """
    return engine.active_engine().get_pa(agent_id)


@mcp.tool()
def telos_audit(start_iso: str, end_iso: str) -> dict[str, Any]:
    """Return audit chain entries within a time window.

    Capped at 100 entries to keep MCP payloads bounded. For deeper queries,
    use the `telos://audit/{date}` resource per-day.

    Args:
        start_iso: ISO-8601 window start (e.g. "2026-04-25T00:00:00Z").
        end_iso: ISO-8601 window end (must be later than start).

    Returns:
        Dict with keys: entries (list, max 100), count, capped (bool),
        window {start, end}.
    """
    # Fetch one past the cap so `capped` reports evidence of truncation (a
    # 101st entry existed), not a count that merely landed on the cap.
    entries = engine.active_engine().audit_window(start_iso=start_iso, end_iso=end_iso, cap=101)
    capped = len(entries) > 100
    entries = entries[:100]
    return {
        "entries": entries,
        "count": len(entries),
        "capped": capped,
        "window": {"start": start_iso, "end": end_iso},
    }


@mcp.tool()
def telos_replay(receipt_id: str, alt_config_path: str) -> dict[str, Any]:
    """Queue a CCRS counterfactual replay against an alternate config.

    CCRS Mode C re-runs the lifecycle that produced `receipt_id` under a
    different governance configuration (alt thresholds, alt centroids,
    alt PA) and reports verdict deltas. Returns immediately with a job id;
    poll the result via `telos://replay/{job_id}` once available.

    Args:
        receipt_id: ID of the receipt to replay against.
        alt_config_path: Path to the alternate config (YAML) to apply.

    Returns:
        Dict with keys: job_id, receipt_id, alt_config_path, status,
        queued_at, estimated_runtime_seconds, result_uri, stub.
    """
    return engine.active_engine().queue_replay(receipt_id=receipt_id, alt_config_path=alt_config_path)


# =========================================================================
# Resources
# =========================================================================

@mcp.resource("telos://wiki/{path}")
def wiki_resource(path: str) -> str:
    """Read a TELOS governance wiki page by relative path.

    Examples: `telos://wiki/04-governance/architecture/steward-design-spec`
    """
    return engine.active_engine().read_wiki_page(path)


@mcp.resource("telos://centroids/{dimension}")
def centroids_resource(dimension: str) -> str:
    """Return the compiled centroid set for one governance dimension.

    Valid dimensions: purpose, scope, boundary, tool, chain, codebase_fidelity.
    Returns a JSON document describing the centroid set (count, embedding
    dim, checksum). Raw float32 arrays are not transported over MCP.
    """
    return json.dumps(engine.active_engine().read_centroids(dimension), indent=2)


@mcp.resource("telos://audit/{date}")
def audit_resource(date: str) -> str:
    """Return the audit-chain segment for a given YYYY-MM-DD date (UTC)."""
    return json.dumps(engine.active_engine().read_audit_segment(date), indent=2)


# =========================================================================
# Prompts
# =========================================================================

@mcp.prompt()
def governance_review(action: str) -> str:
    """User-invokable: have the model review a proposed action for governance fit."""
    return (
        "Review this proposed action for TELOS governance compliance. "
        "Call `telos_score` with the action and inspect the per-dimension "
        "scores. If the verdict is CLARIFY, surface which dimension is "
        "weakest and propose one concrete revision. If ESCALATE, explain "
        "which boundary or scope rule the action crosses.\n\n"
        f"Proposed action:\n{action}"
    )


@mcp.prompt()
def audit_walkthrough(start_date: str, end_date: str) -> str:
    """User-invokable: walk through the audit chain in a date window."""
    return (
        "Pull the audit-chain entries from "
        f"{start_date} to {end_date} using the `telos_audit` tool. "
        "For each ESCALATE or CLARIFY entry, summarize: what action was "
        "proposed, which agent proposed it, and what the outcome was. "
        "Verify the chain is contiguous (every entry's `previous_id` "
        "matches the prior entry's `id`). Flag any breaks."
    )


# =========================================================================
# Entrypoint
# =========================================================================

def main() -> None:
    """Console-script entrypoint. Runs the server over stdio (default)."""
    mcp.run()


if __name__ == "__main__":
    main()
