import * as path from 'path';

export function assertSafeRelativeSourcePath(repoPath: string): void {
  if (path.posix.isAbsolute(repoPath)) throw new Error('Source path must be relative.');
  const normalized = path.posix.normalize(repoPath);
  if (normalized.startsWith('..') || normalized.includes('/../')) throw new Error('Source path traversal blocked.');
}

export function resolveSafeDestination(workspaceRoot: string, destRelative: string): string {
  if (path.isAbsolute(destRelative)) throw new Error('Destination must be relative.');
  const normalized = path.posix.normalize(destRelative);
  if (normalized.includes('..')) throw new Error('Destination traversal blocked.');

  const githubRoot = path.resolve(workspaceRoot, '.github');
  const abs = path.resolve(workspaceRoot, normalized);
  if (!(abs === githubRoot || abs.startsWith(githubRoot + path.sep))) {
    throw new Error('Destination must stay under .github/.');
  }
  return abs;
}
