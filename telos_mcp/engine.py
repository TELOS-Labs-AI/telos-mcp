"""Engine dispatcher for telos-mcp (v0.2 scaffold).

Selects which engine backs the MCP tool surface, behind a feature flag:

    TELOS_MCP_ENGINE = stub   (default, and the value when unset)  -> engine_stub
    TELOS_MCP_ENGINE = real                                        -> engine_real

Flag OFF (stub) is byte-identical to v0.1: `active_engine()` returns the
`engine_stub` module object itself, so every call is literally the same function
v0.1 called. No indirection changes the output.

Flag ON (real) loads the real-engine adapter lazily. The adapter guarded-imports
the governance engine; if the engine is not installed, this FAILS CLOSED with a
clear, catchable `EngineUnavailable` rather than crashing on import or silently
falling back to the stub. Public install and the test suite never touch the real
engine because the import is lazy and only happens when the flag is explicitly
set to `real`.

This is a scaffold: the `real` path is wired but dormant. It does NOT become the
default and does NOT add a hard dependency. See engine_real.py for the seam.
"""

from __future__ import annotations

import os
from types import ModuleType

ENGINE_ENV = "TELOS_MCP_ENGINE"
_STUB_VALUES = {"", "stub", "off", "0", "false", "no"}
_REAL_VALUES = {"real", "on", "1", "true", "yes"}


class EngineConfigError(RuntimeError):
    """The TELOS_MCP_ENGINE flag held an unrecognized value."""


class EngineUnavailable(RuntimeError):
    """The real engine was requested but is not installed/wired (fail closed)."""


def engine_mode() -> str:
    """Return the normalized flag value: 'stub' or 'real'."""
    raw = os.environ.get(ENGINE_ENV, "").strip().lower()
    if raw in _STUB_VALUES:
        return "stub"
    if raw in _REAL_VALUES:
        return "real"
    raise EngineConfigError(
        f"unrecognized {ENGINE_ENV}={raw!r}; expected one of "
        f"{sorted(_STUB_VALUES | _REAL_VALUES)}"
    )


def active_engine() -> ModuleType:
    """Return the engine module providing the v0.1 call surface.

    Stub mode returns the `engine_stub` module object unchanged (byte-identical
    to v0.1). Real mode loads and returns the real adapter, or fails closed.
    """
    if engine_mode() == "stub":
        from telos_mcp import engine_stub  # local import keeps the module graph flat
        return engine_stub
    from telos_mcp import engine_real
    return engine_real.load()
