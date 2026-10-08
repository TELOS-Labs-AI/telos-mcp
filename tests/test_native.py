"""Native MCP tool controls use the same synthetic bytes as the SDK."""
import asyncio
import base64
import builtins
import hashlib
import json
from pathlib import Path

import pytest
from telos_mcp import server


def request():
    return json.loads((Path(__file__).parent / "native-request.json").read_text())


def invoke(value):
    api = getattr(server, "telos_verify_native_receipts", None)
    assert callable(api), "native MCP tool is missing"
    return api(**value)


def test_native_tool_checks_repaired_pin_tamper():
    value = request()
    assert invoke(value)["status"] == "PASS"
    row = json.loads(base64.b64decode(value["receipts_base64"]))
    row["args"] = {"tampered": True}
    row["receipt_hash"] = hashlib.sha256(json.dumps(
        {k: v for k, v in row.items() if k != "receipt_hash"},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    raw = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode()
    bad = {**value, "receipts_base64": base64.b64encode(raw).decode(),
           "expected_sha256": hashlib.sha256(raw).hexdigest()}
    result = invoke(bad)
    assert result["status"] == "FAIL"
    assert "CANONICAL_INPUT_HASH_MISMATCH" in result["problems"]


@pytest.mark.parametrize("bad", [None, [], "text"])
def test_native_tool_refuses_mixed_nonobject_rows(bad):
    value = request()
    assert invoke(value)["status"] == "PASS"
    raw = base64.b64decode(value["receipts_base64"]) + json.dumps(bad).encode() + b"\n"
    result = invoke({**value, "receipts_base64": base64.b64encode(raw).decode(),
                     "expected_sha256": hashlib.sha256(raw).hexdigest()})
    assert result["status"] == "UNAVAILABLE"
    assert "UNSUPPORTED_SCHEMA" in result["problems"]


def test_native_tool_missing_crypto_never_passes(monkeypatch):
    assert invoke(request())["status"] == "PASS"
    original = builtins.__import__

    def without_crypto(name, *args, **kwargs):
        if name == "cryptography" or name.startswith("cryptography."):
            raise ModuleNotFoundError("synthetic missing optional dependency", name="cryptography")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_crypto)
    result = invoke(request())
    assert result["status"] == "UNAVAILABLE"
    assert "NATIVE_DEPENDENCY_UNAVAILABLE" in result["problems"]


def test_registered_native_tool_returns_integrity_report():
    assert invoke(request())["status"] == "PASS"
    content, structured = asyncio.run(server.mcp.call_tool("telos_verify_native_receipts", request()))
    assert json.loads(content[0].text)["status"] == structured["status"] == "PASS"
    assert structured["signature_verified"] is False
