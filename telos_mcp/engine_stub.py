"""Stubbed TELOS engine calls for telos-mcp.

These functions return realistic-shaped placeholder data so MCP clients can
exercise the full protocol surface (tools, resources, prompts) without an
installed governance engine. Every stub carries a TODO marker showing where
the real `telos_gov` call replaces it.

Receipts use the shared `telos-receipt` contract: when the scorer scores an
action it mints an UNSIGNED integrity-hash receipt (a key-free SHA-256 over the
canonical payload; `signature: null`, `signing_status:
"unsigned_integrity_hash"`). It is the exact envelope the telos-trust-surface
serves and verifies, so a receipt minted here verifies there unchanged.

Going live is two internal flips, no schema break:
  - Engine: stub -> real. Add `telos-gov` as a hard dependency and route
    score/verify/get_pa/audit/replay through the real engine (the dispatcher
    in engine.py already gates this on TELOS_MCP_ENGINE=real). The receipt
    payload becomes real verdicts/scores instead of synthetic ones.
  - Signer: null -> real. A real signature fills the receipt's `signature`
    field and `signing_status` flips. Every field already exists.

Stub determinism: every return value is constructed deterministically from
the inputs so test snapshots stay stable across runs. No hidden randomness.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import telos_receipt

# Labels the engine that produced a receipt payload. Honest about stub state:
# the scores are synthetic and the receipt is unsigned until the engine + signer
# are wired (see module docstring).
STUB_ENGINE = "telos-mcp v0.1 stub (governance engine not wired; unsigned integrity-hash)"


# -- Verdict + dimension constants -----------------------------------------

VERDICTS = ("EXECUTE", "CLARIFY", "ESCALATE")
DIMENSIONS = ("purpose", "scope", "boundary", "tool", "chain", "codebase_fidelity")


def _digest(payload: Any) -> str:
    """Stable SHA-256 digest used for deterministic stub IDs."""
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# -- Tool: telos_score -----------------------------------------------------

def score_action(action_name: str, action_params: dict[str, Any], agent_id: str) -> dict[str, Any]:
    """Score a proposed action against the active Purpose Anchor.

    Mints an unsigned integrity-hash receipt (shared telos-receipt contract)
    committing to the governance result. The receipt verifies on the
    telos-trust-surface unchanged.

    TODO: replace the synthetic scoring below with `telos_gov.score_action(...)`.
    Keep `build_action_receipt(...)` as the receipt mint point; only the verdict
    and scores change from synthetic to real, and the signer fills `signature`.
    """
    digest = _digest({"action": action_name, "params": action_params, "agent": agent_id})
    # Synthetic, illustrative scores (NOT real calibration) derived from the
    # digest for stub stability. The floor/span constants are arbitrary fixture
    # values; they are not the engine's calibration.
    seed = int(digest[:8], 16)
    raw = [(seed >> (i * 5)) & 0xFF for i in range(len(DIMENSIONS))]
    scores = {dim: round(0.1234 + (raw[i] / 255.0) * 0.4321, 4) for i, dim in enumerate(DIMENSIONS)}
    composite = round(sum(scores.values()) / len(scores), 4)
    # Stub verdict is a deterministic FIXTURE rotation keyed off the digest,
    # chosen structurally independent of the scores. The real engine's method for
    # mapping a score to a verdict is deliberately NOT represented in this public
    # stub: no public threshold gates the verdict here.
    verdict = VERDICTS[int(digest[8:10], 16) % len(VERDICTS)]
    return {
        "verdict": verdict,
        "composite_score": composite,
        "scores": scores,
        "agent_id": agent_id,
        "action_name": action_name,
        "receipt": telos_receipt.build_action_receipt(
            action_name=action_name,
            action_params=action_params,
            agent_id=agent_id,
            verdict=verdict,
            composite_score=composite,
            scores=scores,
            pa_id=f"pa::{agent_id}::v1",
            engine=STUB_ENGINE,
        ),
        "stub": True,
        "engine": STUB_ENGINE,
    }


# -- Tool: telos_verify ----------------------------------------------------

def verify_receipt(receipt_json: str | dict[str, Any]) -> dict[str, Any]:
    """Verify an unsigned integrity-hash receipt offline.

    Delegates to the shared `telos-receipt` contract -- the SAME verifier the
    telos-trust-surface runs -- so MCP-side verify and surface-side verify give
    identical answers for the same receipt. Recomputes the integrity hash over
    the receipt payload; it is key-free and is not a signature check.

    TODO: when the signer is wired, add a real signature check ahead of this
    integrity-hash recompute (the recompute stays as the payload-integrity leg).
    """
    if isinstance(receipt_json, str):
        try:
            receipt = json.loads(receipt_json)
        except json.JSONDecodeError:
            # Not parseable -> not a dict; the canonical verifier returns a
            # controlled match:False ("receipt is not a JSON object").
            receipt = receipt_json
    else:
        receipt = receipt_json
    return telos_receipt.verify_receipt(receipt)


# -- Tool: telos_get_pa ----------------------------------------------------

def get_pa(agent_id: str) -> dict[str, Any]:
    """Return the active Purpose Anchor (PA) for an agent.

    TODO(v0.2): replace with `telos_gov.get_pa(agent_id)`. Real engine
    loads the agent's commissioned PA from the vault.
    """
    return {
        "agent_id": agent_id,
        "pa_id": f"pa::{agent_id}::v1",
        "purpose": "Demonstrate TELOS governance via MCP (stub PA).",
        "boundaries": [
            "no production system mutation",
            "no PII egress",
            "no execution of unsigned tool calls",
        ],
        "scope": ["telos-mcp scaffold", "MCP client integration"],
        "allowed_tools": ["telos_score", "telos_verify", "telos_get_pa", "telos_audit", "telos_replay"],
        "centroid_dimensions": list(DIMENSIONS),
        "compiled_at": _now_iso(),
        "stub": True,
    }


# -- Tool: telos_audit -----------------------------------------------------

def audit_window(start_iso: str, end_iso: str, cap: int = 100) -> list[dict[str, Any]]:
    """Return audit-chain entries within a time window (capped).

    TODO(v0.2): replace with `telos_gov.audit(start, end, limit=cap)` which
    streams from the engine's append-only audit store.
    """
    # Stub: emit three deterministic entries inside the requested window.
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        # Comparison stays inside the guard: mixed naive/aware inputs raise
        # TypeError here, which -- like an unparseable timestamp -- is bad
        # input the window gracefully treats as empty rather than propagating.
        if end <= start:
            return []
    except (ValueError, TypeError):
        return []
    span = (end - start) / 4
    entries: list[dict[str, Any]] = []
    for i in range(min(3, cap)):
        ts = (start + span * (i + 1)).isoformat(timespec="seconds")
        entries.append({
            "id": f"audit::{_digest({'ts': ts, 'i': i})[:16]}",
            "timestamp": ts,
            "verdict": VERDICTS[i % len(VERDICTS)],
            "agent_id": "stub-agent",
            "action_name": ["read_file", "post_message", "write_file"][i % 3],
            "previous_id": entries[-1]["id"] if entries else None,
            "tkey_fingerprint": "stub:0000000000000000",
        })
    return entries


# -- Tool: telos_replay ----------------------------------------------------

def queue_replay(receipt_id: str, alt_config_path: str) -> dict[str, Any]:
    """Queue a CCRS counterfactual replay job; return job id.

    TODO(v0.2): replace with `telos_gov.replay(receipt_id, alt_config_path)`
    which enqueues the job onto the CCRS Mode C runner.
    """
    job_id = f"ccrs::{_digest({'receipt': receipt_id, 'cfg': alt_config_path})[:20]}"
    return {
        "job_id": job_id,
        "receipt_id": receipt_id,
        "alt_config_path": alt_config_path,
        "status": "queued",
        "queued_at": _now_iso(),
        "estimated_runtime_seconds": 12,
        "result_uri": f"telos://replay/{job_id}",
        "stub": True,
    }


# -- Resource helpers ------------------------------------------------------

def read_wiki_page(path: str) -> str:
    """Resolve a TELOS wiki page by relative path.

    TODO(v0.2): wire to the governance corpus store and read the actual page
    content (with appropriate read-only access controls).
    """
    return (
        f"# TELOS Wiki Stub: {path}\n\n"
        "This is a placeholder wiki page returned by telos-mcp v0.1.\n"
        "v0.2 will read the canonical page from the TELOS vault.\n\n"
        f"Requested path: `{path}`\n"
        f"Resolved at: {_now_iso()}\n"
    )


def read_centroids(dimension: str) -> dict[str, Any]:
    """Return the compiled centroid set for a governance dimension.

    TODO(v0.2): wire to the engine's centroid store; centroids are numpy
    arrays compiled from the customer's wiki/docs corpus.
    """
    if dimension not in DIMENSIONS:
        return {"error": f"unknown dimension: {dimension}", "valid_dimensions": list(DIMENSIONS)}
    return {
        "dimension": dimension,
        "n_centroids": 42,
        "embedding_dim": 17,
        "compiled_from": "stub-corpus",
        "compiled_at": _now_iso(),
        "checksum": _digest({"dim": dimension})[:32],
        "note": "stub: real centroids are float32 arrays loaded from disk",
    }


def read_audit_segment(date_str: str) -> list[dict[str, Any]]:
    """Return the audit chain segment for a given YYYY-MM-DD."""
    try:
        day = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
    except ValueError:
        return []
    return audit_window(
        start_iso=day.isoformat(timespec="seconds"),
        end_iso=(day + timedelta(days=1)).isoformat(timespec="seconds"),
        cap=100,
    )
