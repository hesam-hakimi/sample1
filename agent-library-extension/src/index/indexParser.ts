import { IndexFile, IndexItem } from './indexTypes';

function isStringArray(v: unknown): v is string[] {
  return Array.isArray(v) && v.every((x) => typeof x === 'string');
}

export function parseIndex(text: string, maxBytes: number): IndexFile {
  if (Buffer.byteLength(text, 'utf8') > maxBytes) throw new Error('Index too large.');
  const parsed = JSON.parse(text) as Partial<IndexFile>;
  if (parsed.schemaVersion !== '1.0') throw new Error('Unsupported schemaVersion.');
  if (!parsed.source?.repo || !parsed.source?.ref) throw new Error('Missing source metadata.');
  if (!Array.isArray(parsed.items)) throw new Error('Invalid items array.');

  parsed.items.forEach(validateItem);
  return parsed as IndexFile;
}

function validateItem(item: Partial<IndexItem>): void {
  const kinds = ['agent', 'prompt', 'instruction', 'alwaysOnInstruction'];
  if (!item.kind || !kinds.includes(item.kind)) throw new Error('Invalid item kind.');
  if (!item.id || !item.name || !item.path) throw new Error('Item missing required fields.');
  if (item.tags && !isStringArray(item.tags)) throw new Error('Invalid tags field.');
  if (item.teamTags && !isStringArray(item.teamTags)) throw new Error('Invalid teamTags field.');
}
