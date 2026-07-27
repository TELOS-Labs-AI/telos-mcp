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
| `telos_score(action_name, action_params, agent_id)` | Score a proposed action against the active Purpose Anchor. Returns verdict (`EXECUTE` / `CLARIFY` / `ESCALATE`) plus per-dimension scores across `purpose`, `scope`, `boundary`, `tool`, `chain`, `codebase_fidelity`, plus an unsigned integrity-hash receipt envelope. |
| `telos_verify(receipt_json)` | Verify an unsigned integrity-hash receipt offline (key-free; not a signature check). Returns `{match, recomputed_integrity_hash, signing_status, reason, ...}`. |
| `telos_get_pa(agent_id)` | Return the active Purpose Anchor: purpose, hard boundaries, declared scope, allowed tools, centroid dimensions. |
| `telos_audit(start_iso, end_iso)` | Return audit-chain entries within a time window (capped at 100). |
| `telos_replay(receipt_id, alt_config_path)` | Queue a CCRS counterfactual replay against an alternate config; returns a `job_id`. |

### Resources (LLM-readable)

| URI template | Returns |
|--------------|---------|
| `telos://wiki/{path}` | A TELOS governance wiki page by relative path. |
| `telos://centroids/{dimension}` | Compiled centroid metadata for one of `purpose`, `scope`, `boundary`, `tool`, `chain`, `codebase_fidelity`. |
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

Restart Claude Desktop. The five `telos_*` tools should appear in the
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

You should see a stub PA back containing `"stub": true` and the six
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

# Or use the MCP Inspector for interactive exploration:
mcp dev telos_mcp/server.py
```

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
