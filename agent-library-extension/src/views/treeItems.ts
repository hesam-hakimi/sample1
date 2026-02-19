import * as vscode from 'vscode';
import { IndexItem } from '../index/indexTypes';

export class LibraryLeaf extends vscode.TreeItem {
  constructor(public readonly item: IndexItem) {
    super(item.name, vscode.TreeItemCollapsibleState.None);
    this.description = item.version;
    this.tooltip = `${item.description ?? ''}\nTags: ${(item.tags ?? []).join(', ')}\nPath: ${item.path}`;
    this.contextValue = 'agentLibraryItem';
    this.command = { command: 'agentLibrary.previewItem', title: 'Preview Item', arguments: [item] };
  }
}

export class KindGroup extends vscode.TreeItem {
  constructor(public readonly kind: string, public readonly children: IndexItem[]) {
    super(kind, vscode.TreeItemCollapsibleState.Expanded);
  }
}
