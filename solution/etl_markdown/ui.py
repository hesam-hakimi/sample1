Fix ModuleNotFoundError: No module named 'app' when running app/main.py directly.

Do:
1) Update README.md run instructions to use:
   cd <repo-root>
   python -m app.main
2) Add a repo-root main.py entrypoint that calls app.main.main(), so users can also run `python main.py`.
3) Add/update VS Code .vscode/launch.json to run the module app.main with cwd = workspaceFolder.
4) Ensure app/__init__.py exists (do not remove).
5) Add/adjust a small pytest test that imports app.main successfully (no Azure/SQL calls).

Return the exact file changes with full contents for any new/modified files.
