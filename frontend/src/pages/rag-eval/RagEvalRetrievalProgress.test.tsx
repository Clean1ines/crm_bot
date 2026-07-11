import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import type { WorkbenchRagEvalRunSummary } from '@shared/api/modules/ragEval';
import { RagEvalRetrievalProgress } from './RagEvalRetrievalProgress';

const run = (overrides: Partial<WorkbenchRagEvalRunSummary> = {}): WorkbenchRagEvalRunSummary => ({
  run_id: 'run-1',
  project_id: 'project-1',
  status: 'running',
  current_phase: 'retrieval_evaluation',
  total_entries: 2,
  total_questions: 20,
  completed_questions: 8,
  top1_hits: 0,
  top3_hits: 0,
  top5_hits: 0,
  misses: 0,
  created_at: '2026-07-11T00:00:00Z',
  ...overrides,
});

describe('RagEvalRetrievalProgress', () => {
  it('renders persisted retrieval phase, progress, and backend-owned classifications', () => {
    const html = renderToStaticMarkup(
      <RagEvalRetrievalProgress
        run={run({
          retrieval_progress: {
            completed: 8,
            total: 20,
            classification_counts: {
              pass_strong: 3,
              pass_weak: 2,
              confusion: 1,
              miss: 1,
              existing_alias_retrieval_failure: 1,
            },
          },
        })}
      />,
    );

    expect(html).toContain('Оценка retrieval');
    expect(html).toContain('8 / 20');
    expect(html).toContain('PASS_STRONG');
    expect(html).toContain('>3<');
    expect(html).toContain('EXISTING_ALIAS_RETRIEVAL_FAILURE');
  });

  it('uses persisted summary totals without inferring classification counters', () => {
    const html = renderToStaticMarkup(<RagEvalRetrievalProgress run={run()} />);

    expect(html).toContain('8 / 20');
    expect(html).toContain('Классификация ещё не сохранена backend');
  });
});
