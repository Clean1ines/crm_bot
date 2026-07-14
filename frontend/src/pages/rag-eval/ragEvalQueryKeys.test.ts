import { describe, expect, it } from 'vitest';

import { ragEvalQueryKeys } from './ragEvalQueryKeys';

describe('ragEvalQueryKeys', () => {
  it('keeps run detail queries under one stable project/run hierarchy', () => {
    expect(ragEvalQueryKeys.latest('project-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
      'latest',
    ]);
    expect(ragEvalQueryKeys.questions('project-1', 'run-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
      'runs',
      'run-1',
      'questions',
    ]);
    expect(ragEvalQueryKeys.promotionCandidates('project-1', 'run-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
      'runs',
      'run-1',
      'promotion-candidates',
    ]);
    expect(ragEvalQueryKeys.embeddingRevisions('project-1', 'run-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
      'runs',
      'run-1',
      'embedding-revisions',
    ]);
    expect(ragEvalQueryKeys.embeddingRevision('project-1', 'revision-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
      'embedding-revisions',
      'revision-1',
    ]);
  });

  it('provides a project prefix suitable for event-driven invalidation', () => {
    expect(ragEvalQueryKeys.project('project-1')).toEqual([
      'workbench-rag-eval',
      'project-1',
    ]);
  });
});
