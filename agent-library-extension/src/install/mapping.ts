import * as path from 'path';
import { IndexItem } from '../index/indexTypes';

function baseNameFor(itemPath: string): string {
  return path.posix.basename(itemPath);
}

export function mapItemToDestination(item: IndexItem): string {
  const file = baseNameFor(item.path);
  switch (item.kind) {
    case 'agent':
      if (!file.endsWith('.agent.md')) throw new Error('Invalid agent extension.');
      return `.github/agents/${file}`;
    case 'prompt':
      if (!file.endsWith('.prompt.md')) throw new Error('Invalid prompt extension.');
      return `.github/prompts/${file}`;
    case 'instruction':
      if (!file.endsWith('.instructions.md')) throw new Error('Invalid instruction extension.');
      return `.github/instructions/${file}`;
    case 'alwaysOnInstruction':
      if (!item.path.endsWith('copilot-instructions.md')) throw new Error('Invalid alwaysOnInstruction path.');
      return '.github/copilot-instructions.md';
    default:
      throw new Error('Unsupported kind');
  }
}
