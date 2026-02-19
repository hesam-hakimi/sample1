import * as vscode from 'vscode';

const channel = vscode.window.createOutputChannel('Agent Library');

export function log(message: string): void {
  channel.appendLine(`[${new Date().toISOString()}] ${message}`);
}
