import * as vscode from 'vscode';

export type ReceiptItem = {
  id: string;
  kind: string;
  version?: string;
  sourcePath: string;
  destPath: string;
  sha256?: string;
};

export type Receipt = {
  schemaVersion: '1.0';
  sourceRepo: string;
  ref: string;
  updatedAt: string;
  items: ReceiptItem[];
};

export const RECEIPT_PATH = '.github/.agent-library-installed.json';

export async function readReceipt(): Promise<Receipt | undefined> {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return undefined;
  const uri = vscode.Uri.joinPath(ws.uri, RECEIPT_PATH);
  try {
    const raw = await vscode.workspace.fs.readFile(uri);
    return JSON.parse(Buffer.from(raw).toString('utf8')) as Receipt;
  } catch {
    return undefined;
  }
}

export async function writeReceipt(receipt: Receipt): Promise<void> {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) throw new Error('Open a workspace folder first.');
  await vscode.workspace.fs.createDirectory(vscode.Uri.joinPath(ws.uri, '.github'));
  const uri = vscode.Uri.joinPath(ws.uri, RECEIPT_PATH);
  await vscode.workspace.fs.writeFile(uri, Buffer.from(JSON.stringify(receipt, null, 2), 'utf8'));
}
