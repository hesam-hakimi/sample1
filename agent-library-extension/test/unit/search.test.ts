import { strict as assert } from 'assert';
import { parseSearchQuery, searchItems } from '../../src/index/search';

const items = [
  { kind: 'agent', id: 'spark', name: 'Spark', description: 'databricks', tags: ['spark'], teamTags: ['amcb'], path: 'a.agent.md' },
  { kind: 'prompt', id: 'test', name: 'Testing', description: 'qa', tags: ['test'], teamTags: [], path: 'b.prompt.md' }
] as any;

describe('search', () => {
  it('parses kind and tags', () => {
    const q = parseSearchQuery('kind:agent tag:spark team:amcb data');
    assert.equal(q.kind, 'agent');
    assert.equal(q.tags[0], 'spark');
    assert.equal(q.teamTags[0], 'amcb');
  });

  it('filters items', () => {
    const res = searchItems(items, 'kind:agent tag:spark');
    assert.equal(res.length, 1);
    assert.equal(res[0].id, 'spark');
  });
});
