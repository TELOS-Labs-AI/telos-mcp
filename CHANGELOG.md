# Changelog

## Unreleased

- `telos_replay` returns `status: "stub_not_queued"` and no longer returns a `result_uri` that no resource serves, a runtime estimate or `queued_at`.
- `telos_audit` results, their entries and `telos://audit/{date}` entries carry `stub: true`; the `audit_walkthrough` prompt says stub entries are synthetic.
- README: Claude Code manual config uses `.mcp.json` with `mcpServers` (the old `~/.config/claude-code/mcp_servers.json` path is not read by Claude Code); the unused `TELOS_AGENT_ID` variable is removed from the configs and `server.json`; the engine is described as private, with no install or schema promise; the wiki resource is described as a placeholder; links to telos-receipt and telos-verify.
- Tool descriptions and docstrings no longer cite a non-public "trust surface".

## 0.1.2

- Add `telos_verify_native_receipts` for native-v2 byte integrity, without signature, score or content validation.
- Accept JSON objects as well as JSON strings in `telos_verify`.
- Depend on `telos-receipt[native]>=0.1.1,<0.2`; keep existing tools, tests and the development extra.
- Keep package, protocol and registry versions consistent.
