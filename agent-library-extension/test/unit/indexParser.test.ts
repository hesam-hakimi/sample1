import { strict as assert } from 'assert';
import { parseIndex } from '../../src/index/indexParser';

describe('indexParser', () => {
  it('rejects invalid schemaVersion', () => {
    assert.throws(() => parseIndex(JSON.stringify({ schemaVersion: '2.0', source: { repo: 'a/b', ref: 'main' }, items: [] }), 10000));
  });

  it('rejects oversized index', () => {
    assert.throws(() => parseIndex('x'.repeat(100), 10));
  });

  it('rejects missing required item fields', () => {
    const bad = { schemaVersion: '1.0', source: { repo: 'a/b', ref: 'main' }, items: [{ kind: 'agent' }] };
    assert.throws(() => parseIndex(JSON.stringify(bad), 10000));
  });
});
