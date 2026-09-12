"""Installed dependency, real protocol identity, and documented startup contract."""

import asyncio
import os
import shlex
import subprocess
import sys
from importlib.metadata import requires, version
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from packaging.requirements import Requirement

from telos_mcp import __version__


def test_declared_sdk_floor_when_running_floor_environment():
    requirement = next(
        Requirement(r) for r in requires("telos-mcp") if Requirement(r).name == "mcp"
    )
    assert not requirement.specifier.contains("2.0.0")
    floor = next(s.version for s in requirement.specifier if s.operator == ">=")
    assert requirement.specifier.contains(version("mcp"))
    if os.environ.get("TELOS_MCP_TEST_FLOOR") == "1":
        assert version("mcp") == floor


def test_real_stdio_initialize_reports_package_identity():
    async def handshake():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "telos_mcp.server"],
            env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONPATH": ""},
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            result = await session.initialize()
            assert result.serverInfo.name == "telos-governance"
            assert result.serverInfo.version == __version__ == version("telos-mcp") == "0.1.1"
            tools = await session.list_tools()
            assert len(tools.tools) == 5

    asyncio.run(asyncio.wait_for(handshake(), timeout=20))


def test_documented_development_startup_exits_cleanly():
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    command, = [line for line in readme.splitlines() if line.endswith(" < /dev/null")]
    args = shlex.split(command.removesuffix(" < /dev/null"))
    assert args == ["python", "-m", "telos_mcp.server"]
    result = subprocess.run(
        [sys.executable, *args[1:]], stdin=subprocess.DEVNULL,
        capture_output=True, text=True, timeout=20, check=False,
        env={**os.environ, "TELOS_MCP_ENGINE": "stub", "PYTHONPATH": ""},
    )
    assert result.returncode == 0, result.stderr
