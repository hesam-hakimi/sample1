import { isValidRepo } from '../config';

export function validateRepoAgainstAllowlist(repo: string, allowedRepos: string[]): void {
  if (!isValidRepo(repo)) throw new Error('Invalid repo format. Use OWNER/REPO.');
  if (allowedRepos.length > 0 && !allowedRepos.includes(repo)) {
    throw new Error(`Repo ${repo} is not in agentLibrary.allowedRepos.`);
  }
}
