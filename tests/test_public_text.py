"""Public text agrees with what the package does (M2, M4-M8 and the trust-surface references)."""

import ast
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


def _environment_lookups():
    """Names the package passes to an actual environment lookup.

    Parsed from the syntax tree, so a name in a comment, docstring or unrelated
    string does not count: only os.environ.get(X), os.environ[X], os.getenv(X)
    and `X in os.environ`, with X a string literal or a module-level string
    constant.
    """
    names = set()
    for path in sorted((ROOT / "telos_mcp").glob("*.py")):
        tree = ast.parse(path.read_text())
        consts = {
            t.id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            for t in node.targets if isinstance(t, ast.Name)
        }

        def value(n, consts=consts):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                return n.value
            if isinstance(n, ast.Name):
                return consts.get(n.id)
            return None

        def is_environ(n):
            return isinstance(n, ast.Attribute) and n.attr == "environ"

        for node in ast.walk(tree):
            arg = None
            if isinstance(node, ast.Call) and node.args:
                f = node.func
                if isinstance(f, ast.Attribute) and (
                    (f.attr == "get" and is_environ(f.value)) or f.attr == "getenv"
                ):
                    arg = node.args[0]
            elif isinstance(node, ast.Subscript) and is_environ(node.value):
                arg = node.slice
            elif isinstance(node, ast.Compare) and any(is_environ(c) for c in node.comparators):
                arg = node.left
            if arg is not None and value(arg):
                names.add(value(arg))
    return names


def _declared_environment_variables():
    manifest = json.loads((ROOT / "server.json").read_text())
    declared = {
        env["name"]
        for package in manifest["packages"]
        for env in package.get("environmentVariables", [])
    }
    declared |= set(re.findall(r'"(TELOS_[A-Z_]+)"\s*:', README.read_text()))
    return declared


def test_every_declared_environment_variable_is_read_by_an_actual_lookup(monkeypatch):
    # Valid neighbour: the engine flag is a real lookup, and setting it changes
    # what the package does.
    assert "TELOS_MCP_ENGINE" in _environment_lookups()
    from telos_mcp import engine

    monkeypatch.setenv("TELOS_MCP_ENGINE", "stub")
    assert engine.engine_mode() == "stub"
    monkeypatch.setenv("TELOS_MCP_ENGINE", "real")
    assert engine.engine_mode() == "real"
    unread = sorted(_declared_environment_variables() - _environment_lookups())
    assert unread == [], f"declared but never looked up: {unread}"


def test_the_obsolete_agent_id_variable_is_absent_from_the_configs():
    assert "TELOS_AGENT_ID" not in _declared_environment_variables()
    assert "TELOS_AGENT_ID" not in (ROOT / "server.json").read_text()
    assert "TELOS_AGENT_ID" not in README.read_text()


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


def _row(start):
    return next(ln for ln in README.read_text().splitlines() if ln.startswith(start))


def test_status_note_flags_only_the_responses_that_carry_stub_true():
    # Behaviour: the wiki resource is plain Markdown with no stub flag; the
    # scored, audit and replay responses carry `stub: true`.
    contents = asyncio.run(server.mcp.read_resource("telos://wiki/example-page"))
    page = next(iter(contents)).content
    assert page.startswith("# ")
    assert '"stub"' not in page
    text = _flat(README.read_text())
    assert "replay results and wiki pages are synthetic placeholders, and results say so" not in text
    assert "wiki pages are a plain Markdown placeholder" in text


def test_score_and_pa_rows_describe_a_fixed_synthetic_purpose_anchor():
    _c, scored = asyncio.run(server.mcp.call_tool(
        "telos_score", {"action_name": "write_file", "action_params": {}, "agent_id": "a"}))
    _c, pa = asyncio.run(server.mcp.call_tool("telos_get_pa", {"agent_id": "a"}))
    assert scored["stub"] is True and pa["stub"] is True
    assert scored["receipt"]["payload"]["pa_id"] == pa["pa_id"] == "pa::a::v1"
    for row in (_row("| `telos_score("), _row("| `telos_get_pa(")):
        assert "the active Purpose Anchor" not in row
        assert "fixed synthetic Purpose Anchor" in row


def test_centroids_row_describes_fixture_metadata():
    contents = asyncio.run(server.mcp.read_resource("telos://centroids/purpose"))
    doc = json.loads(next(iter(contents)).content)
    assert doc["compiled_from"] == "stub-corpus"
    row = _row("| `telos://centroids/{dimension}`")
    assert "Compiled centroid metadata" not in row
    assert "fixture" in row.lower()
    assert "no compiled centroids are served" in row
