"""The six 0.1.2 tools on their existing fixtures, with the clock frozen: one collector for base and head.

`old_tools_golden.json` beside this file was written by this script from a `git archive` of telos-mcp
b53473a3d6a48ad8ab42b7c8d3d20d1eff631bd3 (0.1.2):

    cd <archive of b53473a> && python -B <this file> --write <path>/old_tools_golden.json

The tests run the same collector against the tree under test and compare bytes.

What is compared. `structured` (the dict each tool returned) is compared in every environment. `tools` (the listing a
client is given) and `text` (the text block) are rendered by the installed `mcp` and `pydantic`, so they are compared
only under the versions the file was made with (`made_with`); under other versions the file must be made again from
the base commit with the command above, and the test for them says so instead of passing.

Frozen clock. These output fields vary with time in 0.1.2 and are fixed to FROZEN here, at base and at head:
  telos_score   receipt.issued_at                (telos_receipt._now_iso, through build_action_receipt)
  telos_get_pa  compiled_at                      (telos_mcp.engine_stub._now_iso)
  telos_replay  queued_at                        (telos_mcp.engine_stub._now_iso)
(`telos_verify`, `telos_verify_native_receipts` and `telos_audit` have no time-dependent field: the audit
timestamps are computed from the window that is passed in.)
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLDEN = HERE / "old_tools_golden.json"
BASE_COMMIT = "b53473a3d6a48ad8ab42b7c8d3d20d1eff631bd3"
FROZEN = "2026-01-01T00:00:00+00:00"
OLD_TOOLS = ("telos_verify_native_receipts", "telos_score", "telos_verify", "telos_get_pa", "telos_audit",
             "telos_replay")
SYNTHETIC_ACTION = {"action_name": "synthetic_test_only", "action_params": {"path": "fixture.txt"},
                    "agent_id": "synthetic-agent"}


def freeze():
    """Fix the two clocks the six tools read. Returns the call that puts the real clocks back."""
    import telos_receipt
    from telos_mcp import engine_stub

    real = (telos_receipt._now_iso, engine_stub._now_iso)
    assert all(callable(clock) for clock in real)
    telos_receipt._now_iso = lambda: FROZEN
    engine_stub._now_iso = lambda: FROZEN

    def thaw():
        telos_receipt._now_iso, engine_stub._now_iso = real

    return thaw


def calls():
    """(label, tool name, arguments): the existing fixtures of the existing tests."""
    import telos_receipt

    native = json.loads((HERE / "native-request.json").read_text())
    receipt = telos_receipt.build_receipt("synthetic", {"v": 1}, "demo-agent")
    receipt["issued_at"] = FROZEN  # not covered by the integrity hash; fixed so the argument is the same bytes
    tampered = dict(receipt, payload={"v": 2})
    return [
        ("native: the synthetic request", "telos_verify_native_receipts", native),
        ("native: wrong pin", "telos_verify_native_receipts", dict(native, expected_sha256="0" * 64)),
        ("score: the synthetic action", "telos_score", SYNTHETIC_ACTION),
        ("score: empty params", "telos_score", dict(SYNTHETIC_ACTION, action_params={})),
        ("verify: JSON string", "telos_verify", {"receipt_json": json.dumps(receipt)}),
        ("verify: JSON object", "telos_verify", {"receipt_json": receipt}),
        ("verify: tampered payload", "telos_verify", {"receipt_json": json.dumps(tampered)}),
        ("verify: not JSON", "telos_verify", {"receipt_json": "not json"}),
        ("get_pa", "telos_get_pa", {"agent_id": "synthetic-agent"}),
        ("audit: one day", "telos_audit", {"start_iso": "2026-04-25T00:00:00Z", "end_iso": "2026-04-26T00:00:00Z"}),
        ("audit: empty window", "telos_audit", {"start_iso": "2026-04-26T00:00:00Z",
                                                "end_iso": "2026-04-25T00:00:00Z"}),
        ("replay", "telos_replay", {"receipt_id": "rcpt-synthetic", "alt_config_path": "alt.yaml"}),
    ]


def listed(tool):
    """What a client is told about one tool, as JSON."""
    return tool.model_dump(mode="json", by_alias=True, exclude_none=True)


def made_with():
    """The packages that render a tool listing and a text block: `tools` and `text` are theirs, `structured` is not."""
    from importlib.metadata import version

    return {name: version(name) for name in ("mcp", "pydantic")}


def render(value):
    return (json.dumps(value, indent=1, sort_keys=True, ensure_ascii=True) + "\n").encode("ascii")


async def collect(list_tools, call_tool):
    """{"tools": what is listed for the six, "calls": every answer}. `call_tool(name, arguments)` must give
    (text of the first content block, structured content)."""
    by_name = {tool.name: listed(tool) for tool in await list_tools()}
    out = {"base_commit": BASE_COMMIT, "frozen_clock": FROZEN, "made_with": made_with(),
           "tools": {name: by_name.get(name) for name in OLD_TOOLS}, "calls": []}
    for label, name, arguments in calls():
        text, structured = await call_tool(name, arguments)
        out["calls"].append({"label": label, "tool": name, "arguments": arguments, "text": text,
                             "structured": structured})
    return out


def collect_in_process():
    """The answers of the server module in this process (frozen clock), through `mcp.call_tool`."""
    from telos_mcp import server

    async def call_tool(name, arguments):
        content, structured = await server.mcp.call_tool(name, arguments)
        return content[0].text, structured

    thaw = freeze()
    try:
        return asyncio.run(collect(server.mcp.list_tools, call_tool))
    finally:
        thaw()


async def collect_session(session):
    """The same, asked of a connected client session (the server process must have called freeze())."""
    async def list_tools():
        return (await session.list_tools()).tools

    async def call_tool(name, arguments):
        result = await session.call_tool(name, arguments)
        if result.isError:  # reported as data, so that the comparison fails by assertion in the test
            return "TOOL ERROR: " + result.content[0].text, None
        return result.content[0].text, result.structuredContent

    return await collect(list_tools, call_tool)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--write":
        Path(sys.argv[2]).write_bytes(render(collect_in_process()))
    else:
        sys.stdout.buffer.write(render(collect_in_process()))
