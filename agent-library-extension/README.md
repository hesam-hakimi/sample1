# Agent Library Importer

VS Code extension that imports Copilot customization artifacts from a shared GitHub repo into `.github/**` in the current workspace.

## Run / Debug
1. `npm install`
2. `npm run compile`
3. Press `F5` in VS Code to launch Extension Development Host.

## Configuration
- `agentLibrary.sourceRepo`: default `YOUR_ORG/GitHub-agents`
- `agentLibrary.ref`: default `main`
- `agentLibrary.indexPath`: default `index.json`

## Commands
- Configure Source Repo
- Refresh Library
- Search
- Preview Item
- Install Selected
- Open Receipt

## Index generation
Use a GitHub Action in your shared library repo to generate `index.json` from `.github/agents`, `.github/prompts`, `.github/instructions`, and optional `.github/copilot-instructions.md`.
