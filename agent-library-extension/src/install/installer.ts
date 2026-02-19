import * as path from 'path';
import * as vscode from 'vscode';
import { fetchItemContent } from '../github/githubClient';
import { IndexItem } from '../index/indexTypes';
import { promptConflict } from './conflict';
import { sha256Hex } from './hash';
import { mapItemToDestination } from './mapping';
import { resolveSafeDestination, assertSafeRelativeSourcePath } from './pathSafety';
import { readReceipt, writeReceipt } from './receipt';

async function exists(uri: vscode.Uri): Promise<boolean> {
  try {
    await vscode.workspace.fs.stat(uri);
    return true;
  } catch {
    return false;
  }
}

async function nextCopyName(dest: string): Promise<string> {
  const ext = path.extname(dest);
  const stem = dest.slice(0, -ext.length);
  let i = 1;
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) return dest;
  while (true) {
    const candidate = `${stem}.copy-${i}${ext}`;
    if (!(await exists(vscode.Uri.joinPath(ws.uri, candidate)))) return candidate;
    i += 1;
  }
}

export async function installItems(items: IndexItem[], repo: string, ref: string, maxItemBytes: number): Promise<void> {
  const ws = vscode.workspace.workspaceFolders?.[0];
  if (!ws) throw new Error('Open a workspace folder first.');

  const installed = [];
  for (const item of items) {
    assertSafeRelativeSourcePath(item.path);
    let dest = mapItemToDestination(item);
    resolveSafeDestination(ws.uri.fsPath, dest);

    const destUri = vscode.Uri.joinPath(ws.uri, dest);
    if (await exists(destUri)) {
      const choice = await promptConflict(dest);
      if (choice === 'skip') continue;
      if (choice === 'rename') dest = await nextCopyName(dest);
    }

    const bytes = await fetchItemContent(repo, ref, item.path, maxItemBytes);
    if (item.sha256) {
      const actual = sha256Hex(bytes);
      if (actual !== item.sha256) throw new Error(`Hash mismatch for ${item.id}.`);
    }

    const finalUri = vscode.Uri.joinPath(ws.uri, dest);
    const parent = vscode.Uri.joinPath(finalUri, '..');
    await vscode.workspace.fs.createDirectory(parent);
    const tmp = vscode.Uri.joinPath(ws.uri, `${dest}.tmp-${Date.now()}`);
    await vscode.workspace.fs.writeFile(tmp, bytes);
    await vscode.workspace.fs.rename(tmp, finalUri, { overwrite: true });

    installed.push({ id: item.id, kind: item.kind, version: item.version, sourcePath: item.path, destPath: dest, sha256: item.sha256 });
  }

  const old = (await readReceipt()) ?? { schemaVersion: '1.0' as const, sourceRepo: repo, ref, updatedAt: '', items: [] };
  const merged = [...old.items.filter((x) => !installed.find((n) => n.destPath === x.destPath)), ...installed];
  await writeReceipt({ schemaVersion: '1.0', sourceRepo: repo, ref, updatedAt: new Date().toISOString(), items: merged });
}
