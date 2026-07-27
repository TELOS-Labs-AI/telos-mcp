"""Real-engine adapter for telos-mcp (v0.2 scaffold; DORMANT).

This module is the seam where the live TELOS governance engine plugs in. It is
present so the dispatch path exists and is tested, but it is dormant: it adds no
hard dependency and is only reached when `TELOS_MCP_ENGINE=real` is set
explicitly.

Importing this module does NOT import the governance engine. The guarded import
happens inside `load()`, so `from telos_mcp import engine_real` always succeeds,
public install stays clean, and the test suite passes with no engine installed.

Dependency note: the live governance engine binds in v0.2 via the public,
engine-agnostic call surface. Until then `load()` fails closed and no engine
dependency is imported or pinned.
"""

from __future__ import annotations

from types import ModuleType


def load() -> ModuleType:
    """Load the real engine adapter, or fail closed.

    Returns a module-like object exposing the same call surface as
    `engine_stub` (score_action, verify_receipt, get_pa, audit_window,
    queue_replay, read_wiki_page, read_centroids, read_audit_segment).

    Raises:
        EngineUnavailable: the real engine is not installed/wired. This is the
        expected state in the scaffold; the dispatcher surfaces it cleanly so
        callers never see a hard ImportError or a silent stub fallback.
    """
    from telos_mcp.engine import EngineUnavailable

    try:
        # Guarded import of the real engine. Absent in the scaffold; present
        # only once the clean-facade engine is installed and explicitly opted in.
        import telos_gov  # type: ignore  # noqa: F401
    except ImportError as exc:
        raise EngineUnavailable(
            "real engine requested (TELOS_MCP_ENGINE=real) but the governance "
            "engine is not installed/wired. The v0.2 scaffold is dormant; the "
            "real engine binds after the clean-facade republish. Unset "
            "TELOS_MCP_ENGINE to use the stub."
        ) from exc

    # Reached only when a real engine is installed. The binding below is left as
    # the documented swap point so the scaffold neither imports private symbols
    # nor claims behavior it does not yet have.
    raise EngineUnavailable(
        "governance engine present but the real adapter binding is not enabled "
        "in this scaffold build; binding lands with the clean-facade engine."
    )
