import * as vscode from 'vscode';
import { KindGroup } from './treeItems';
import { readReceipt } from '../install/receipt';

class InstalledLeaf extends vscode.TreeItem {
  constructor(label: string, filePath: string) {
    super(label, vscode.TreeItemCollapsibleState.None);
    this.command = { command: 'vscode.open', title: 'Open', arguments: [vscode.Uri.file(filePath)] };
  }
}

export class InstalledProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  refresh(): void {
    this.emitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem { return element; }

  async getChildren(element?: vscode.TreeItem): Promise<vscode.TreeItem[]> {
    const ws = vscode.workspace.workspaceFolders?.[0];
    if (!ws) return [];
    const receipt = await readReceipt();
    if (!receipt) return [];
    if (!element) {
      const grouped = new Map<string, typeof receipt.items>();
      for (const i of receipt.items) grouped.set(i.kind, [...(grouped.get(i.kind) ?? []), i]);
      return [...grouped.entries()].map(([k, items]) => new KindGroup(k, items as any));
    }
    if (element instanceof KindGroup) {
      return element.children.map((x: any) => new InstalledLeaf(x.id, vscode.Uri.joinPath(ws.uri, x.destPath).fsPath));
    }
    return [];
  }
}
