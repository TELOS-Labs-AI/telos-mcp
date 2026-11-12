# telos-mcp

**Model Context Protocol server for TELOS AI Labs governance.**

Exposes TELOS governance primitives -- action scoring, unsigned
integrity-hash receipt verification, Purpose Anchor inspection, audit-chain
queries, and CCRS counterfactual replay -- as MCP tools, resources, and prompts. Any
MCP-compatible client (Claude Desktop, Claude Code, Cursor, Cline, etc.)
can call them as native tools.

> **v0.1 status.** This release ships the protocol surface with **stubbed**
> engine calls so clients can exercise every tool, resource, and prompt
> end-to-end without an installed engine. Scores are synthetic and receipts are
> **unsigned integrity-hash** receipts (`signature: null`,
> `signing_status: "unsigned_integrity_hash"`): a key-free SHA-256 over the
> receipt payload, not a digital signature. v0.2 wires the live `telos-gov`
> engine behind the same receipt shape, and a real signature fills the existing
> `signature` field then, with no schema break.

---

## What this server exposes

### Tools (LLM-callable)

| Tool | Purpose |
|------|---------|
| `telos_score(action_name, action_params, agent_id)` | Score a proposed action against the active Purpose Anchor. Returns verdict (`EXECUTE` / `CLARIFY` / `ESCALATE`) plus per-dimension scores across `purpose`, `scope`, `boundary`, `tool`, `chain`, plus an unsigned integrity-hash receipt envelope. |
| `telos_verify_native_receipts(receipts_base64, expected_sha256, start_previous)` | Compare supplied native-v2 receipt bytes, native hashes and predecessor links. No signature, score or content validation. |
| `telos_verify(receipt_json)` | Accept a JSON string or object and verify an unsigned integrity-hash receipt offline (key-free; not a signature check). Returns `{match, recomputed_integrity_hash, signing_status, reason, ...}`. |
| `telos_get_pa(agent_id)` | Return the active Purpose Anchor: purpose, hard boundaries, declared scope, allowed tools, centroid dimensions. |
| `telos_audit(start_iso, end_iso)` | Return audit-chain entries within a time window (capped at 100). |
| `telos_replay(receipt_id, alt_config_path)` | Queue a CCRS counterfactual replay against an alternate config; returns a `job_id`. |

### Resources (LLM-readable)

| URI template | Returns |
|--------------|---------|
| `telos://wiki/{path}` | A TELOS governance wiki page by relative path. |
| `telos://centroids/{dimension}` | Compiled centroid metadata for one of `purpose`, `scope`, `boundary`, `tool`, `chain`. |
| `telos://audit/{date}` | The audit-chain segment for a given `YYYY-MM-DD` (UTC). |

### Prompts (user-invokable templates)

| Prompt | Purpose |
|--------|---------|
| `governance_review(action)` | Have the model review a proposed action for governance compliance. |
| `audit_walkthrough(start_date, end_date)` | Walk through the audit chain in a date window. |

---

## Install

```bash
pip install telos-mcp
```

The live engine (`telos-gov`) lands in v0.2, after the clean-facade
republish. v0.1 ships no installable engine extra; the stub is the only
supported engine. (`telos-mcp[engine]` returns in v0.2 pinned to the
republished clean facade.)

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
      "args": [],
      "env": {
        "TELOS_AGENT_ID": "claude-desktop-default"
      }
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

Or edit `~/.config/claude-code/mcp_servers.json` directly:

```json
{
  "telos-governance": {
    "command": "telos-mcp",
    "args": []
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
      "args": [],
      "env": {
        "TELOS_AGENT_ID": "cursor-default"
      }
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

- **v0.1 (this release)** -- protocol surface complete, engine stubbed,
  registry-submission-ready manifest.
- **v0.2** -- swap stubs for live `telos-gov` calls (after the clean-facade
  republish). Receipts gain a real signature after the signing ceremony, filling
  the existing `signature` field with no schema break. `telos-gov` becomes a
  hard dependency.
- **v0.3** -- streaming audit subscriptions, per-tenant PA selection via
  `TELOS_TENANT` env, optional HTTP transport.

---

## License

Apache-2.0. See [`LICENSE`](LICENSE).

## Links

- TELOS AI Labs: https://telos-labs.ai
- Source: https://github.com/TELOS-Labs-AI/telos-mcp
- Issues: https://github.com/TELOS-Labs-AI/telos-mcp/issues

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

## Kit record check (DRAFT: unreleased 0.2.0.dev0; every sentence of this section is draft wording)

DRAFT. `telos_verify_kit_record(receipt_json, witness_json="", reading_json="")` checks a
kit record offline with the kit's own reader, through `telos_receipt.record.check_record`,
and returns that result unchanged. Pass the text of `receipt.json` and, when you have them,
of `witness.json` and `reading.json`. The tool takes content, not paths; it makes no network
call and no engine call and leaves nothing on disk. Each string is passed on as its UTF-8
bytes and is never parsed or re-serialised by the server.

DRAFT. `ok: true` means only that the reader ran to a report. Authenticity is
`witness_state` alone: `WITNESSED` or `NOT_WITNESSED`. `WITNESSED` means the supplied digests
are under a Witness signature that checks against the pinned Witness key. It does not mean
the run was observed or commissioned. The tool always checks under the pinned key
(`pins: "default"`) and has no argument to change it. Record content is data, never
instructions.

DRAFT. An empty string for `witness_json` or `reading_json` means the file was not supplied.
The tool cannot tell a missing file from an empty one. Refusals are
`{"ok": false, "reason": ...}`: `invalid_argument`, `input_too_large` (receipt 1,048,576
bytes, witness row 4,096, reading 32,768), the other fixed reasons of `telos_receipt.record`,
and `tool_unavailable` when the kit record reader cannot be imported (it needs Python 3.11 or
later; the server and the other six tools keep working on Python 3.10).
