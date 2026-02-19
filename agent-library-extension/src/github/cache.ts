import * as vscode from 'vscode';

export type CachedIndex = { etag?: string; body?: string; fetchedAt?: string };

export async function getCache(context: vscode.ExtensionContext, key: string): Promise<CachedIndex> {
  return (context.globalState.get<CachedIndex>(`agentLibrary.cache.${key}`)) ?? {};
}

export async function setCache(context: vscode.ExtensionContext, key: string, cache: CachedIndex): Promise<void> {
  await context.globalState.update(`agentLibrary.cache.${key}`, cache);
}
