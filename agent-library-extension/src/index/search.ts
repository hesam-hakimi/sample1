import { IndexItem } from './indexTypes';

export type SearchQuery = {
  kind?: string;
  tags: string[];
  teamTags: string[];
  text: string[];
};

export function parseSearchQuery(input: string): SearchQuery {
  const tokens = input.trim().split(/\s+/).filter(Boolean);
  const query: SearchQuery = { tags: [], teamTags: [], text: [] };

  for (const token of tokens) {
    if (token.startsWith('kind:')) query.kind = token.slice(5);
    else if (token.startsWith('tag:')) query.tags.push(token.slice(4).toLowerCase());
    else if (token.startsWith('team:') || token.startsWith('teamTag:')) query.teamTags.push(token.split(':')[1].toLowerCase());
    else query.text.push(token.toLowerCase());
  }
  if (query.kind === 'always') query.kind = 'alwaysOnInstruction';
  return query;
}

export function searchItems(items: IndexItem[], queryText: string): IndexItem[] {
  const q = parseSearchQuery(queryText);
  return items.filter((item) => {
    if (q.kind && item.kind !== q.kind) return false;
    if (q.tags.length && !q.tags.every((t) => (item.tags ?? []).map((x) => x.toLowerCase()).includes(t))) return false;
    if (q.teamTags.length && !q.teamTags.every((t) => (item.teamTags ?? []).map((x) => x.toLowerCase()).includes(t))) return false;
    if (q.text.length) {
      const hay = `${item.name} ${item.id} ${item.description ?? ''}`.toLowerCase();
      if (!q.text.every((x) => hay.includes(x))) return false;
    }
    return true;
  });
}
