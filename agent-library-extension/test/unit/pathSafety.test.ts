import { strict as assert } from 'assert';
import { assertSafeRelativeSourcePath, resolveSafeDestination } from '../../src/install/pathSafety';

describe('pathSafety', () => {
  it('rejects traversal and absolute source paths', () => {
    assert.throws(() => assertSafeRelativeSourcePath('../x.md'));
    assert.throws(() => assertSafeRelativeSourcePath('/abs.md'));
  });

  it('prevents escaping .github', () => {
    assert.throws(() => resolveSafeDestination('/repo', '../x'));
    assert.throws(() => resolveSafeDestination('/repo', 'src/a.ts'));
    assert.equal(resolveSafeDestination('/repo', '.github/agents/a.agent.md'), '/repo/.github/agents/a.agent.md');
  });
});
