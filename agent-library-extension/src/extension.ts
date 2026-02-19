import * as vscode from 'vscode';
import { getConfig, isValidRepo } from './config';
import { fetchIndex } from './github/githubClient';
import { validateRepoAgainstAllowlist } from './github/validators';
import { parseIndex } from './index/indexParser';
import { IndexItem } from './index/indexTypes';
import { searchItems } from './index/search';
import { installItems } from './install/installer';
import { AgentLibContentProvider, createVirtualDoc } from './install/preview';
import { readReceipt, RECEIPT_PATH } from './install/receipt';
import { InstalledProvider } from './views/installedView';
import { LibraryProvider } from './views/libraryView';
import { log } from './util/logger';
import { toMessage } from './util/errors';

let currentItems: IndexItem[] = [];

export async function activate(context: vscode.ExtensionContext): Promise<void> {
  const libraryProvider = new LibraryProvider();
  const installedProvider = new InstalledProvider();
  context.subscriptions.push(vscode.window.registerTreeDataProvider('agentLibrary.libraryView', libraryProvider));
  context.subscriptions.push(vscode.window.registerTreeDataProvider('agentLibrary.installedView', installedProvider));
  context.subscriptions.push(vscode.workspace.registerTextDocumentContentProvider('agentlib', new AgentLibContentProvider()));

  const refresh = async () => {
    try {
      const cfg = getConfig();
      validateRepoAgainstAllowlist(cfg.sourceRepo, cfg.allowedRepos);
      const key = `${cfg.sourceRepo}|${cfg.ref}|${cfg.indexPath}`;
      const body = await fetchIndex({
        context,
        key,
        repo: cfg.sourceRepo,
        ref: cfg.ref,
        indexPath: cfg.indexPath,
        maxBytes: cfg.maxIndexBytes
      });
      const index = parseIndex(body, cfg.maxIndexBytes);
      currentItems = index.items;
      libraryProvider.setItems(currentItems);
      installedProvider.refresh();
      log(`Loaded index with ${currentItems.length} items.`);
    } catch (err) {
      vscode.window.showErrorMessage(`Agent Library refresh failed: ${toMessage(err)}`);
    }
  };

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.refreshIndex', refresh));

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.configureSource', async () => {
    const repo = await vscode.window.showInputBox({ prompt: 'Source repo (OWNER/REPO)', value: getConfig().sourceRepo });
    if (!repo) return;
    if (!isValidRepo(repo)) return vscode.window.showErrorMessage('Invalid repo format. Use OWNER/REPO.');
    const ref = await vscode.window.showInputBox({ prompt: 'Git ref', value: getConfig().ref });
    if (!ref) return;
    await vscode.workspace.getConfiguration('agentLibrary').update('sourceRepo', repo, vscode.ConfigurationTarget.Global);
    await vscode.workspace.getConfiguration('agentLibrary').update('ref', ref, vscode.ConfigurationTarget.Global);
    await refresh();
  }));

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.search', async () => {
    const query = await vscode.window.showInputBox({ prompt: 'Search: kind:agent tag:spark team:amcb text' });
    if (query === undefined) return;
    const hits = searchItems(currentItems, query);
    const picked = await vscode.window.showQuickPick(hits.map((i) => ({ label: i.name, description: i.kind, detail: i.path, item: i })), { canPickMany: true });
    if (picked?.length) {
      await vscode.commands.executeCommand('agentLibrary.installItems', picked.map((p) => p.item));
    }
  }));

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.previewItem', async (item?: IndexItem) => {
    const target = item ?? currentItems[0];
    if (!target) return;
    const cfg = getConfig();
    const bytes = await (await import('./github/githubClient')).fetchItemContent(cfg.sourceRepo, cfg.ref, target.path, cfg.maxItemBytes);
    const content = Buffer.from(bytes).toString('utf8');
    const virtual = createVirtualDoc(content, target.name);
    await vscode.commands.executeCommand('vscode.open', virtual);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.installItems', async (arg?: IndexItem[]) => {
    if (!vscode.workspace.isTrusted) {
      return vscode.window.showWarningMessage('Trust this workspace to install files.');
    }
    const cfg = getConfig();
    const items = Array.isArray(arg) && arg.length ? arg : currentItems;
    if (!items.length) return vscode.window.showInformationMessage('No items selected.');
    await installItems(items, cfg.sourceRepo, cfg.ref, cfg.maxItemBytes);
    installedProvider.refresh();
    vscode.window.showInformationMessage(`Installed ${items.length} item(s).`);
  }));

  context.subscriptions.push(vscode.commands.registerCommand('agentLibrary.openReceipt', async () => {
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return;
    const receipt = await readReceipt();
    if (!receipt) return vscode.window.showInformationMessage('No receipt file found.');
    await vscode.commands.executeCommand('vscode.open', vscode.Uri.joinPath(ws.uri, RECEIPT_PATH));
  }));

  await refresh();
}

export function deactivate(): void {}
