"""telos-mcp: Model Context Protocol server for TELOS AI Labs governance.

Exposes TELOS governance primitives (scoring, receipt verification, Purpose
Anchor inspection, audit chain access, and CCRS counterfactual replay) over
the Model Context Protocol so any MCP-compatible client (Claude Desktop,
Claude Code, Cursor, Cline, etc.) can call them as native tools.

This package is a thin protocol adapter. The governance engine binds in v0.2
via a public, engine-agnostic call surface. v0.1 ships with stubbed engine
calls so the protocol surface can be exercised end-to-end without an installed
engine; v0.2 replaces the stubs with live calls.
"""

__version__ = "0.1.0"
__all__ = ["__version__"]
