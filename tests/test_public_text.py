"""Public text agrees with what the package does (M2, M4-M8 and the trust-surface references)."""

import asyncio
import json
import re
from pathlib import Path

from telos_mcp import server

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"


def _flat(text):
    return " ".join(text.split())


def _package_source():
    return "\n".join(p.read_text() for p in sorted((ROOT / "telos_mcp").glob("*.py")))


def test_every_declared_environment_variable_is_read_by_the_package():
    source = _package_source()
    assert "TELOS_MCP_ENGINE" in source  # valid neighbour: a variable the code does read
    manifest = json.loads((ROOT / "server.json").read_text())
    declared = {
        env["name"]
        for package in manifest["packages"]
        for env in package.get("environmentVariables", [])
    }
    declared |= set(re.findall(r'"(TELOS_[A-Z_]+)"\s*:', README.read_text()))
    unread = sorted(name for name in declared if name not in source)
    assert unread == [], f"declared but never read: {unread}"


def test_claude_code_manual_config_uses_a_file_claude_code_reads():
    text = README.read_text()
    assert "claude mcp add telos-governance -- telos-mcp" in text
    assert "~/.config/claude-code" not in text
    assert "`.mcp.json`" in text
    block = text.split("### Claude Code", 1)[1].split("### Cursor", 1)[0]
    snippet = block.split("```json", 1)[1].split("```", 1)[0]
    assert json.loads(snippet)["mcpServers"]["telos-governance"]["command"] == "telos-mcp"


def test_no_public_text_points_at_the_non_public_trust_surface():
    tools = asyncio.run(server.mcp.list_tools())
    assert any("telos_score" == t.name for t in tools)
    for tool in tools:
        assert "trust-surface" not in (tool.description or "")
        assert "trust surface" not in (tool.description or "")
    for text in (README.read_text(), _package_source()):
        assert "trust-surface" not in text
        assert "trust surface" not in text


def test_engine_is_described_as_private_with_no_install_promise():
    text = _flat(README.read_text())
    assert "engine is private" in text
    assert "hard dependency" not in text
    assert "telos-mcp[engine]" not in text
    assert "no schema break" not in text
    assert "no schema break" not in _flat(server.mcp.instructions or "")


def test_package_summary_says_the_engine_is_a_stub():
    pyproject = (ROOT / "pyproject.toml").read_text()
    summary = re.search(r'^description = "(.*)"$', pyproject, re.MULTILINE).group(1)
    assert "stub" in summary.lower()
    assert "synthetic" in summary.lower()


def test_wiki_resource_is_described_as_a_placeholder_without_internal_paths():
    templates = asyncio.run(server.mcp.list_resource_templates())
    description = next(t.description for t in templates if t.uriTemplate == "telos://wiki/{path}")
    assert "placeholder" in description.lower()
    assert "04-governance" not in description
    assert "steward" not in description.lower()
    assert "telos://wiki/example-page" in description
    contents = asyncio.run(server.mcp.read_resource("telos://wiki/example-page"))
    page = next(iter(contents)).content
    assert "placeholder" in page
    assert "vault" not in page
    assert "Placeholder" in README.read_text().split("telos://wiki/{path}", 1)[1].split("\n", 1)[0]


# Word-bounded so the public server name "telos-governance" does not match.
PRIVATE_ENGINE_NAME = re.compile(r"\btelos[_-]gov\b")


def test_no_public_text_names_the_private_engine_module():
    # engine_real.py is the one file allowed to name it: it holds the guarded
    # import. Its presence there is the valid neighbour that shows the scan reads
    # the package files it is pointed at.
    real = (ROOT / "telos_mcp" / "engine_real.py").read_text()
    assert PRIVATE_ENGINE_NAME.search(real)
    assert not PRIVATE_ENGINE_NAME.search("telos-governance")
    public = [README.read_text(), server.mcp.instructions or ""]
    public += [t.description or "" for t in asyncio.run(server.mcp.list_tools())]
    public += [p.read_text() for p in sorted((ROOT / "telos_mcp").glob("*.py")) if p.name != "engine_real.py"]
    assert len(public) > 4
    for text in public:
        assert not PRIVATE_ENGINE_NAME.search(text)


def test_stub_does_not_promise_signing_in_place():
    stub = _flat((ROOT / "telos_mcp" / "engine_stub.py").read_text())
    assert "private governance engine" in stub
    assert "signer fills" not in stub
    assert "separate contract version" in stub
