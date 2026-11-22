"""Public text agrees with what the package does (M2, M4-M8 and the trust-surface references)."""

import ast
import asyncio
import json
import re
from pathlib import Path

import pytest

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


def test_pa_row_describes_a_fixed_synthetic_purpose_anchor():
    _c, pa = asyncio.run(server.mcp.call_tool("telos_get_pa", {"agent_id": "a"}))
    assert pa["stub"] is True and pa["pa_id"] == "pa::a::v1"
    row = _row("| `telos_get_pa(")
    assert "the active Purpose Anchor" not in row
    assert "fixed synthetic Purpose Anchor" in row


def _score_tool_description():
    tools = asyncio.run(server.mcp.list_tools())
    return next(t.description for t in tools if t.name == "telos_score")


_PA_SCORING_CLAIM = re.compile(r"against [^.|]{0,40}Purpose Anchor", re.IGNORECASE)


def test_score_text_does_not_claim_purpose_anchor_scoring():
    # Valid text beside the invalid pattern: the PA row may name a Purpose
    # Anchor; the score row and tool description may not claim to score
    # against one.
    assert "fixed synthetic Purpose Anchor" in _row("| `telos_get_pa(")
    for text in (_row("| `telos_score("), _flat(_score_tool_description())):
        assert not _PA_SCORING_CLAIM.search(text), text
        assert "action name, parameters and agent ID" in text
        assert "no Purpose Anchor is consulted" in text
        assert "`pa::<agent_id>::v1`" in text


def test_scores_do_not_depend_on_the_purpose_anchor_lookup(monkeypatch):
    from telos_mcp import engine_stub

    args = {"action_name": "write_file", "action_params": {"path": "x"}, "agent_id": "a"}
    _c, before = asyncio.run(server.mcp.call_tool("telos_score", args))

    def _no_pa(agent_id):
        raise AssertionError("Purpose Anchor lookup called during scoring")

    monkeypatch.setattr(engine_stub, "get_pa", _no_pa)
    _c, after = asyncio.run(server.mcp.call_tool("telos_score", args))
    with pytest.raises(Exception, match="Purpose Anchor lookup called"):
        asyncio.run(server.mcp.call_tool("telos_get_pa", {"agent_id": "a"}))
    for key in ("verdict", "composite_score", "scores", "stub"):
        assert after[key] == before[key]
    assert after["receipt"]["payload"]["pa_id"] == "pa::a::v1"


def test_centroids_row_describes_fixture_metadata():
    contents = asyncio.run(server.mcp.read_resource("telos://centroids/purpose"))
    doc = json.loads(next(iter(contents)).content)
    assert doc["compiled_from"] == "stub-corpus"
    row = _row("| `telos://centroids/{dimension}`")
    assert "Compiled centroid metadata" not in row
    assert "fixture" in row.lower()
    assert "no compiled centroids are served" in row


_ACTIVE_PA_CLAIM = re.compile(
    r"\bactive (Purpose Anchor|PA)\b|\bused to score\b|(?<!synthetic )\bPurpose Anchor inspection\b"
    r"|\bcomplian(ce|t)\b|\bgovernance fit\b|\brules? (the action )?cross|\bcross(es)? [^.]{0,30}\brules?\b"
    r"|(?<!no )(?<!any )\bcompiled centroid set\b",
    re.IGNORECASE)


def _package_docstrings():
    pkg = Path(server.__file__).parent
    for path in sorted(pkg.glob("*.py")):
        tree = ast.parse(path.read_text())
        nodes = [tree] + [n for n in ast.walk(tree) if isinstance(
            n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        for node in nodes:
            doc = ast.get_docstring(node)
            if doc:
                yield f"{path.name}:{getattr(node, 'name', '<module>')}", _flat(doc)


def _schema_text(node, path=""):
    """Every "title" and "description" string at any depth of a JSON schema."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("title", "description") and isinstance(value, str):
                yield f"{path}/{key}", value
            else:
                yield from _schema_text(value, f"{path}/{key}")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _schema_text(value, f"{path}/{i}")


def _client_visible_text():
    tools = asyncio.run(server.mcp.list_tools())
    yield "instructions", _flat(server.mcp.instructions)
    for tool in tools:
        yield f"tool:{tool.name}", _flat(tool.description or "")
        for path, text in _schema_text(tool.inputSchema):
            yield f"tool:{tool.name}:schema{path}", _flat(text)
    for prompt in asyncio.run(server.mcp.list_prompts()):
        yield f"prompt:{prompt.name}", _flat(prompt.description or "")
        args = {a.name: "write_file" for a in (prompt.arguments or [])}
        rendered = asyncio.run(server.mcp.get_prompt(prompt.name, args))
        text = " ".join(m.content.text for m in rendered.messages)
        yield f"prompt:{prompt.name}:rendered", _flat(text)
    for template in asyncio.run(server.mcp.list_resource_templates()):
        yield f"resource:{template.uriTemplate}", _flat(template.description or "")


def test_no_docstring_or_tool_description_claims_a_real_purpose_anchor():
    sites = _all_sites()
    # Valid control beside the scan: the scan sees the stub's score and PA docs.
    names = {name for name, _text in sites}
    assert "engine_stub.py:score_action" in names and "tool:telos_get_pa" in names
    assert "prompt:governance_review:rendered" in names
    assert "tool:telos_score:schema/properties/action_name/title" in names
    assert "resource:telos://centroids/{dimension}" in names
    assert _claim_hits(sites) == []


def _all_sites():
    return [*_package_docstrings(), *_client_visible_text(), ("README.md", _flat(README.read_text()))]


def _claim_hits(sites):
    # Sites are (name, text) pairs in a list, never a dict keyed by name, so two
    # sites that share a name are both scanned and neither can hide the other.
    return [(name, m.group(0)) for name, text in sites
            for m in [_PA_SCORING_CLAIM.search(text) or _ACTIVE_PA_CLAIM.search(text)] if m]


def _only(sites, name):
    texts = [text for site, text in sites if site == name]
    assert len(texts) == 1, (name, len(texts))
    return texts[0]


_INJECTED = "Checks governance compliance"


def _inject(schema, where):
    if where == "direct-parameter":
        schema["properties"]["action_name"]["description"] = _INJECTED
    elif where == "root":
        schema["description"] = _INJECTED
    elif where == "defs":
        schema.setdefault("$defs", {})["Extra"] = {"type": "object", "title": _INJECTED}
    elif where == "items":
        schema["properties"]["extra"] = {"type": "array", "items": {"type": "string", "description": _INJECTED}}
    elif where == "anyOf":
        schema["properties"]["extra"] = {"anyOf": [{"type": "null"}, {"type": "string", "description": _INJECTED}]}
    elif where == "nested-properties":
        schema["properties"]["extra"] = {
            "type": "object", "properties": {"inner": {"type": "string", "title": _INJECTED}}}


@pytest.mark.parametrize(
    "where", ["direct-parameter", "root", "defs", "items", "anyOf", "nested-properties"])
def test_scan_catches_a_claim_anywhere_in_a_tool_input_schema(monkeypatch, where):
    real = asyncio.run(server.mcp.list_tools())
    # The clean schemas, scanned beside the injected one, produce no hits.
    assert _claim_hits(_all_sites()) == []
    dirty = [t.model_copy(deep=True) for t in real]
    target = next(t for t in dirty if t.name == "telos_score")
    _inject(target.inputSchema, where)

    async def _tools():
        return dirty

    monkeypatch.setattr(server.mcp, "list_tools", _tools)
    hits = _claim_hits(_all_sites())
    assert len(hits) == 1, hits
    (name, match), = hits
    assert name.startswith("tool:telos_score:") and match == "compliance"


def test_pa_text_says_the_purpose_anchor_is_fixed_and_synthetic():
    sites = [*_package_docstrings(), *_client_visible_text()]
    for name in ("instructions", "tool:telos_get_pa", "engine_stub.py:get_pa"):
        assert "fixed synthetic Purpose Anchor" in _only(sites, name), name
    for name in ("tool:telos_score", "engine_stub.py:score_action"):
        assert "no Purpose Anchor is consulted" in _only(sites, name), name


def test_capability_lists_name_a_synthetic_purpose_anchor():
    readme = _flat(README.read_text())
    package_doc = _flat(ast.get_docstring(ast.parse((ROOT / "telos_mcp" / "__init__.py").read_text())))
    for text in (readme, package_doc):
        assert "synthetic Purpose Anchor inspection" in text


def test_client_surfaces_say_verdicts_and_the_review_prompt_are_synthetic():
    sites = list(_client_visible_text())
    review = _only(sites, "prompt:governance_review:rendered")
    assert "synthetic walkthrough" in review
    assert "evaluates no rule" in review
    assert "synthetic walkthrough" in _only(sites, "prompt:governance_review")
    assert "synthetic verdict" in _only(sites, "tool:telos_score")
    assert "synthetic scores and verdicts" in _only(sites, "instructions")
    assert "Fixture centroid metadata" in _only(sites, "resource:telos://centroids/{dimension}")
    assert "stub: true" in _only(sites, "resource:telos://audit/{date}")
    row = _row("| `governance_review(")
    assert "synthetic walkthrough" in row and not _ACTIVE_PA_CLAIM.search(row)
    assert "synthetic verdict" in _row("| `telos_score(")


@pytest.mark.parametrize("claim_in", ["nested-property", "slash-named-property", "both"])
def test_scan_keeps_a_claim_when_two_schema_paths_spell_the_same(monkeypatch, claim_in):
    real = asyncio.run(server.mcp.list_tools())
    assert _claim_hits(_all_sites()) == []
    dirty = [t.model_copy(deep=True) for t in real]
    target = next(t for t in dirty if t.name == "telos_score")
    nested_title = _INJECTED if claim_in in ("nested-property", "both") else "Inner"
    slash_title = _INJECTED if claim_in in ("slash-named-property", "both") else "Inner"
    # A property literally named "settings/properties/inner" has the same joined
    # path as the nested settings.inner. The claim comes first in one case and
    # second in the other, so neither order may hide it; with both, both count.
    if claim_in != "slash-named-property":
        target.inputSchema["properties"]["settings"] = {
            "type": "object", "properties": {"inner": {"type": "string", "title": nested_title}}}
        target.inputSchema["properties"]["settings/properties/inner"] = {"type": "string", "title": slash_title}
    else:
        target.inputSchema["properties"]["settings/properties/inner"] = {"type": "string", "title": slash_title}
        target.inputSchema["properties"]["settings"] = {
            "type": "object", "properties": {"inner": {"type": "string", "title": nested_title}}}

    async def _tools():
        return dirty

    monkeypatch.setattr(server.mcp, "list_tools", _tools)
    hits = _claim_hits(_all_sites())
    assert len(hits) == (2 if claim_in == "both" else 1), hits


def test_only_refuses_a_site_name_that_appears_twice():
    sites = [("a", "one"), ("b", "two"), ("b", "three")]
    assert _only(sites, "a") == "one"
    with pytest.raises(AssertionError):
        _only(sites, "b")
