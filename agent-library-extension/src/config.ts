import * as vscode from 'vscode';

export const DEFAULTS = {
  sourceRepo: 'YOUR_ORG/GitHub-agents',
  ref: 'main',
  indexPath: 'index.json'
};

export type ExtensionConfig = {
  sourceRepo: string;
  ref: string;
  indexPath: string;
  allowedRepos: string[];
  maxConcurrentDownloads: number;
  maxIndexBytes: number;
  maxItemBytes: number;
};

export function getConfig(): ExtensionConfig {
  const cfg = vscode.workspace.getConfiguration('agentLibrary');
  return {
    sourceRepo: cfg.get('sourceRepo', DEFAULTS.sourceRepo),
    ref: cfg.get('ref', DEFAULTS.ref),
    indexPath: cfg.get('indexPath', DEFAULTS.indexPath),
    allowedRepos: cfg.get<string[]>('allowedRepos', []),
    maxConcurrentDownloads: cfg.get('network.maxConcurrentDownloads', 4),
    maxIndexBytes: cfg.get('security.maxIndexBytes', 2_000_000),
    maxItemBytes: cfg.get('security.maxItemBytes', 1_000_000)
  };
}

export function isValidRepo(repo: string): boolean {
  return /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repo);
}
