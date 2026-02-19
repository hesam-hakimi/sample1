# Architecture

- `github/`: remote URL building, conditional fetch, lightweight cache, repo allowlist validation.
- `index/`: index schema types, validation parser, token-based search parser and filter.
- `install/`: mapping rules, path safety checks, conflict prompts, sha256 verification, receipt persistence.
- `views/`: Library and Installed tree providers.
- `extension.ts`: activation, command wiring, workspace trust checks, startup refresh.

Data flow:
1. Extension fetches `index.json` via raw GitHub URL and ETag cache.
2. Parsed items power Library tree and Search quick pick.
3. Selected items are fetched individually, validated, optionally hash-verified, then written atomically under `.github/**`.
4. Receipt file `.github/.agent-library-installed.json` tracks installed items.
