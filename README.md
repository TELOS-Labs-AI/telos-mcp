# telos-mcp

**Model Context Protocol server for TELOS AI Labs governance.**

Exposes TELOS governance primitives -- action scoring, unsigned
integrity-hash receipt verification, synthetic Purpose Anchor inspection, audit-chain
queries, and counterfactual replay -- as MCP tools, resources, and prompts. Any
MCP-compatible client (Claude Desktop, Claude Code, Cursor, Cline, etc.)
can call them as native tools.

> **0.1.x status: stub engine.** The TELOS governance engine is private and is
> not part of this package. This release ships the full protocol surface backed
> by a **stub** engine, so clients can exercise every tool, resource, and prompt
> end-to-end. Scores, audit entries and replay results are synthetic, and those
> results say so (`stub: true`); wiki pages are a plain Markdown placeholder that
> says it is one. Receipts are **unsigned
> integrity-hash** receipts (`signature: null`,
> `signing_status: "unsigned_integrity_hash"`) built with
> [telos-receipt](https://github.com/TELOS-Labs-AI/telos-receipt): a key-free
> SHA-256 over the receipt payload, not a digital signature. They check offline
> with [telos-verify](https://github.com/TELOS-Labs-AI/telos-verify), which
> defines signed receipts as separate contract versions.

---

## What this server exposes

### Tools (LLM-callable)

| Tool | Purpose |
|------|---------|
| `telos_score(action_name, action_params, agent_id)` | Return synthetic scores for a proposed action, derived from the action name, parameters and agent ID (stub; no Purpose Anchor is consulted). The receipt carries a synthetic PA identifier (`pa::<agent_id>::v1`) and the result carries `stub: true`. Returns a synthetic verdict (`EXECUTE` / `CLARIFY` / `ESCALATE`) plus per-dimension scores across `purpose`, `scope`, `boundary`, `tool`, `chain`, plus an unsigned integrity-hash receipt envelope. |
| `telos_verify_native_receipts(receipts_base64, expected_sha256, start_previous)` | Compare supplied native-v2 receipt bytes, native hashes and predecessor links. No signature, score or content validation. |
| `telos_verify(receipt_json)` | Accept a JSON string or object and verify an unsigned integrity-hash receipt offline (key-free; not a signature check). Returns `{match, recomputed_integrity_hash, signing_status, reason, ...}`. |
| `telos_get_pa(agent_id)` | Return a fixed synthetic Purpose Anchor (stub; the result carries `stub: true`): purpose, hard boundaries, declared scope, allowed tools, centroid dimensions. |
| `telos_audit(start_iso, end_iso)` | Return audit-chain entries within a time window (capped at 100). Stub: synthetic entries flagged `stub: true`. |
| `telos_replay(receipt_id, alt_config_path)` | Request a counterfactual replay against an alternate config. Stub: nothing is queued; returns a `job_id` with `status: "stub_not_queued"`. |

### Resources (LLM-readable)

| URI template | Returns |
|--------------|---------|
| `telos://wiki/{path}` | Placeholder page for any single-segment name, e.g. `telos://wiki/example-page` (stub; no wiki content is served). |
| `telos://centroids/{dimension}` | Fixture centroid metadata (synthetic counts and checksum, `compiled_from: "stub-corpus"`; no compiled centroids are served) for one of `purpose`, `scope`, `boundary`, `tool`, `chain`. |
| `telos://audit/{date}` | The audit-chain segment for a given `YYYY-MM-DD` (UTC). Stub: synthetic entries flagged `stub: true`. |

### Prompts (user-invokable templates)

| Prompt | Purpose |
|--------|---------|
| `governance_review(action)` | A synthetic walkthrough: the model calls `telos_score` and reports the stub verdict and scores, without inferring any rule (the stub evaluates none). |
| `audit_walkthrough(start_date, end_date)` | Walk through the audit chain in a date window. |

---

## Install

```bash
pip install telos-mcp
```

The governance engine is private and is not distributed, so there is no engine
extra to install; the stub is the only engine in this package.

The package installs a `telos-mcp` console script that starts the server
over stdio. You can also invoke it via `python -m telos_mcp.server`.

Requires Python 3.10+.

---

## Client configuration

Each client below assumes `telos-mcp` is installed in a Python environment
on `PATH`. If you prefer not to install globally, use `uvx telos-mcp` or
substitute the absolute path to the `telos-mcp` script in the snippets.

### Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`
(macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows). Add
the `telos-governance` entry under `mcpServers`:

```json
{
  "mcpServers": {
    "telos-governance": {
      "command": "telos-mcp",
      "args": []
    }
  }
}
```

Restart Claude Desktop. The six `telos_*` tools should appear in the
MCP tool tray.

### Claude Code

Use the `claude mcp add` CLI:

```bash
claude mcp add telos-governance -- telos-mcp
```

Add `--scope user` to make it available in every project, or `--scope project`
to share it through the repository. The project scope writes a `.mcp.json` file
at the project root, which you can also create by hand:

```json
{
  "mcpServers": {
    "telos-governance": {
      "command": "telos-mcp",
      "args": []
    }
  }
}
```

### Cursor

Edit `~/.cursor/mcp.json` (global) or `.cursor/mcp.json` (per-project):

```json
{
  "mcpServers": {
    "telos-governance": {
      "command": "telos-mcp",
      "args": []
    }
  }
}
```

### Cline (VS Code extension)

Open Cline -> MCP Servers -> Edit Configuration. Add:

```json
{
  "mcpServers": {
    "telos-governance": {
      "command": "telos-mcp",
      "args": [],
      "transportType": "stdio"
    }
  }
}
```

### Verifying the install

From any client, ask:

> Use the `telos_get_pa` tool with `agent_id="test"` and show the
> Purpose Anchor.

You should see a stub PA back containing `"stub": true` and the five
canonical centroid dimensions.

---

## Development

```bash
git clone https://github.com/TELOS-Labs-AI/telos-mcp
cd telos-mcp
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Run the server over stdio (what MCP clients spawn):
python -m telos_mcp.server

# Non-interactive startup smoke check (closes stdin; exits successfully):
python -m telos_mcp.server < /dev/null

# Run protocol and governance contract tests:
python -m pytest tests

# Install and test the declared minimum MCP SDK in a disposable environment:
python tools/check_mcp_floor.py
```

The stdio server waits for an MCP client when stdin is open. The startup smoke
check above tests clean startup and EOF shutdown; the test suite also performs
a real client initialization handshake. The development extra supplies the
test and lint tools; interactive Inspector tooling is not included.

---

## Roadmap

- **0.1.x (this release)** -- protocol surface complete, stub engine,
  registry-submission-ready manifest.
- **Later** -- streaming audit subscriptions, per-tenant PA selection, optional
  HTTP transport. No release date or engine dependency is promised here.

---

## License

Apache-2.0. See [`LICENSE`](LICENSE).

## Links

- TELOS AI Labs: https://telos-labs.ai
- Source: https://github.com/TELOS-Labs-AI/telos-mcp
- Issues: https://github.com/TELOS-Labs-AI/telos-mcp/issues
- Receipt SDK: https://github.com/TELOS-Labs-AI/telos-receipt
- Offline verifier: https://github.com/TELOS-Labs-AI/telos-verify

## Native receipt verification scope

Version 0.1.2 adds `telos_verify_native_receipts` through
`telos-receipt[native]>=0.1.1,<0.2`. Supply base64-encoded native-v2 JSONL bytes,
their SHA-256 pin and a predecessor hash (each hash is 64 lowercase hex characters).
The tool runs offline and bypasses engine dispatch; it does not read receipt files
or discover local data. Inputs are capped at 1 MiB, 32 rows and 64 KiB per row.

`PASS` means the supplied bytes match the pin and their canonical input, verdict,
receipt and predecessor comparisons succeeded. Tampering returns `FAIL`;
malformed inputs or missing native dependencies return `UNAVAILABLE`, never
`PASS`. MCP rejects null or non-object/non-string values at its typed boundary.

Receipts are unsigned unless a signature is checked. These verification tools do
not check signatures or validate scores or content. They do not establish
identity, custody, trusted genesis or complete workflow coverage.
`signature_verified` is always false; native proofs are reported as
`PROOF_PRESENT_UNVERIFIED`. Stub scoring remains synthetic.
See the dependency's `NOTICE` for native verifier MIT attribution.
