import * as vscode from 'vscode';

const contentByUri = new Map<string, string>();

export class AgentLibContentProvider implements vscode.TextDocumentContentProvider {
  provideTextDocumentContent(uri: vscode.Uri): string {
    return contentByUri.get(uri.toString()) ?? '';
  }
}

export function createVirtualDoc(content: string, label: string): vscode.Uri {
  const uri = vscode.Uri.parse(`agentlib:/${encodeURIComponent(label)}`);
  contentByUri.set(uri.toString(), content);
  return uri;
}
