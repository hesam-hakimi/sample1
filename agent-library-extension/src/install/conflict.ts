import * as vscode from 'vscode';

export type ConflictResolution = 'overwrite' | 'rename' | 'skip';

export async function promptConflict(path: string): Promise<ConflictResolution> {
  const choice = await vscode.window.showWarningMessage(
    `File exists: ${path}`,
    { modal: true },
    'Overwrite',
    'Rename',
    'Skip'
  );
  if (choice === 'Overwrite') return 'overwrite';
  if (choice === 'Rename') return 'rename';
  return 'skip';
}
