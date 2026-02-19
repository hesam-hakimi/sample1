export type IndexItemKind = 'agent' | 'prompt' | 'instruction' | 'alwaysOnInstruction';

export type IndexItem = {
  kind: IndexItemKind;
  id: string;
  name: string;
  description?: string;
  version?: string;
  tags?: string[];
  teamTags?: string[];
  path: string;
  sizeBytes?: number;
  sha256?: string;
};

export type IndexFile = {
  schemaVersion: '1.0';
  generatedAt: string;
  source: { repo: string; ref: string };
  items: IndexItem[];
};
