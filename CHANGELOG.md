# Changelog

## 0.2.0.dev0 (DRAFT: unreleased; the version number and every line of this entry are draft wording)

- DRAFT: add `telos_verify_kit_record(receipt_json, witness_json="", reading_json="")`: check a kit record (`receipt.json`, `witness.json`, `reading.json`, each passed as text) offline through `telos_receipt.record.check_record` and return its result unchanged. No path argument, no network, no engine call, nothing left on disk when the tool returns. One case: when the reader cannot remove its own temporary directory a returned refusal carries `"residual": true` and that directory may remain. If a process-control exception interrupts the call, cleanup is attempted but a directory may remain and no answer is returned.
- DRAFT: the result carries `witness_state` (`WITNESSED` or `NOT_WITNESSED`) and `pins: "default"`; `ok: true` means the reader ran, not that the record is authentic. The tool has no `pins` argument.
- DRAFT: an empty string for `witness_json` or `reading_json` means the file was not supplied; the tool cannot tell a missing file from an empty one. A zero-byte witness file and a zero-byte reading file cannot be represented through this tool: both arrive as not supplied. `telos_receipt.record.check_record` still accepts and distinguishes them when it is called with bytes.
- DRAFT: refusals are `{"ok": false, "reason": ...}`: `invalid_argument`, `input_too_large`, the other fixed reasons of `telos_receipt.record`, and `tool_unavailable` when `telos_receipt.record` cannot be imported (Python 3.10, or a `telos-receipt` without it). Over MCP, an argument that is not a JSON string is refused by the MCP framework before this tool runs (measured with `mcp` 1.26.0 only). Called directly as a Python function, the tool has these boundaries: an `Exception` from importing the reader or from the reader call becomes `tool_unavailable`; an argument that is not a string, or a string UTF-8 cannot carry, gets `invalid_argument`; a resource failure (for example a `MemoryError` while a string is encoded) is not caught and may escape; a call that does not bind to the signature fails before the tool runs; and process-control exceptions (`KeyboardInterrupt`, `SystemExit`) propagate.
- DRAFT: `telos_receipt.record` is imported inside the new tool only; the six existing tools and their outputs are unchanged, and the Python floor stays 3.10.
- DRAFT: depend on `telos-receipt[native]>=0.2.0.dev0,<0.3`.

## 0.1.2

- Add `telos_verify_native_receipts` for native-v2 byte integrity, without signature, score or content validation.
- Accept JSON objects as well as JSON strings in `telos_verify`.
- Depend on `telos-receipt[native]>=0.1.1,<0.2`; keep existing tools, tests and the development extra.
- Keep package, protocol and registry versions consistent.
