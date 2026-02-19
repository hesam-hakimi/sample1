# Security Notes

Implemented controls:
- Strict destination allowlist under `.github/**` only.
- Path traversal and absolute path rejection for source and destination paths.
- Workspace Trust support: install is blocked in untrusted workspaces.
- Optional SHA-256 verification for downloaded files.
- Size limits for index and item downloads.
- ETag-based index caching to reduce repeated network calls.
- No webviews; preview is text-only virtual documents.
