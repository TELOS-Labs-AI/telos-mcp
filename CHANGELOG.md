# Changelog

## 0.1.2

- Add `telos_verify_native_receipts` for native-v2 byte integrity, without signature, score or content validation.
- Accept JSON objects as well as JSON strings in `telos_verify`.
- Depend on `telos-receipt[native]>=0.1.1,<0.2`; keep existing tools, tests and the development extra.
- Keep package, protocol and registry versions consistent.
