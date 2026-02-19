import * as vscode from 'vscode';
import { IndexItem } from '../index/indexTypes';
import { KindGroup, LibraryLeaf } from './treeItems';

export class LibraryProvider implements vscode.TreeDataProvider<vscode.TreeItem> {
  private items: IndexItem[] = [];
  private readonly emitter = new vscode.EventEmitter<void>();
  readonly onDidChangeTreeData = this.emitter.event;

  setItems(items: IndexItem[]): void {
    this.items = items;
    this.emitter.fire();
  }

  getTreeItem(element: vscode.TreeItem): vscode.TreeItem {
    return element;
  }

  getChildren(element?: vscode.TreeItem): vscode.ProviderResult<vscode.TreeItem[]> {
    if (!element) {
      const byKind = new Map<string, IndexItem[]>();
      for (const i of this.items) byKind.set(i.kind, [...(byKind.get(i.kind) ?? []), i]);
      const labels: Record<string, string> = {
        agent: 'Agents', prompt: 'Prompts', instruction: 'Instructions', alwaysOnInstruction: 'Repo Instructions'
      };
      return [...byKind.entries()].map(([k, children]) => new KindGroup(labels[k] ?? k, children));
    }
    if (element instanceof KindGroup) return element.children.map((x) => new LibraryLeaf(x));
    return [];
  }
}
