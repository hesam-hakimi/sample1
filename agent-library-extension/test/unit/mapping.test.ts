import { strict as assert } from 'assert';
import { mapItemToDestination } from '../../src/install/mapping';

describe('mapping', () => {
  it('maps each kind correctly', () => {
    assert.equal(mapItemToDestination({ kind: 'agent', id: '1', name: 'a', path: 'x/a.agent.md' }), '.github/agents/a.agent.md');
    assert.equal(mapItemToDestination({ kind: 'prompt', id: '1', name: 'a', path: 'x/a.prompt.md' }), '.github/prompts/a.prompt.md');
    assert.equal(mapItemToDestination({ kind: 'instruction', id: '1', name: 'a', path: 'x/a.instructions.md' }), '.github/instructions/a.instructions.md');
    assert.equal(mapItemToDestination({ kind: 'alwaysOnInstruction', id: '1', name: 'a', path: '.github/copilot-instructions.md' }), '.github/copilot-instructions.md');
  });

  it('rejects bad extensions', () => {
    assert.throws(() => mapItemToDestination({ kind: 'agent', id: '1', name: 'a', path: 'x/a.md' }));
  });
});
