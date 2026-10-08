"""Real stdio regression for object/string verification and native requests."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from telos_receipt import build_receipt


def server_parameters():
    root = Path(__file__).resolve().parents[1]
    return StdioServerParameters(
        command=sys.executable,
        args=["-B", "-m", "telos_mcp.server"],
        cwd=str(root),
        env={
            **os.environ,
            "TELOS_MCP_ENGINE": "stub",
            "PYTHONPATH": os.pathsep.join((str(root), os.environ.get("PYTHONPATH", ""))),
        },
    )


def test_child_imports_tree_under_test_from_foreign_cwd(tmp_path):
    params = server_parameters()
    result = subprocess.run(
        [params.command, "-c", "import telos_mcp.server; print(telos_mcp.server.__file__)"],
        cwd=params.cwd or tmp_path,
        env=params.env,
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    assert Path(result.stdout.strip()).resolve() == (
        Path(__file__).resolve().parents[1] / "telos_mcp/server.py"
    )


def test_object_and_string_inputs_and_native_controls_over_stdio():
    async def exercise():
        value = build_receipt("synthetic", {"v": 1}, "demo-agent")
        native = json.loads((Path(__file__).parent / "native-request.json").read_text())
        params = server_parameters()
        async with (
            stdio_client(params, errlog=sys.stderr) as streams,
            ClientSession(*streams) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            text = await session.call_tool("telos_verify", {"receipt_json": json.dumps(value)})
            assert not text.isError
            assert json.loads(text.content[0].text)["match"] is True
            obj = await session.call_tool("telos_verify", {"receipt_json": value})
            assert not obj.isError, "documented object must reach the verifier"
            assert json.loads(obj.content[0].text) == json.loads(text.content[0].text)
            for bad in (None, []):
                refused = await session.call_tool("telos_verify", {"receipt_json": bad})
                assert refused.isError
            schema = next(t.inputSchema for t in tools.tools if t.name == "telos_verify")
            assert {t["type"] for t in schema["properties"]["receipt_json"]["anyOf"]} == {
                "string",
                "object",
            }
            ok = await session.call_tool("telos_verify_native_receipts", native)
            assert not ok.isError
            assert json.loads(ok.content[0].text)["status"] == "PASS"
            for bad in (None, []):
                refused = await session.call_tool(
                    "telos_verify_native_receipts", {**native, "receipts_base64": bad}
                )
                assert refused.isError

    asyncio.run(asyncio.wait_for(exercise(), timeout=20))
