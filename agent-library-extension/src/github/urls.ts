export function toRawUrl(repo: string, ref: string, relativePath: string): string {
  return `https://raw.githubusercontent.com/${repo}/${ref}/${relativePath.replace(/^\/+/, '')}`;
}
