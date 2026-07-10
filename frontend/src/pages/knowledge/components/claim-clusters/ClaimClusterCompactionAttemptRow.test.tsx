import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ClaimClusterCompactionAttemptRow } from './ClaimClusterCompactionAttemptRow';

describe('ClaimClusterCompactionAttemptRow', () => {
  it('renders retry tokens and user-safe validation text without placeholder dash', () => {
    const markup = renderToStaticMarkup(
      <ClaimClusterCompactionAttemptRow
        attempt={{
          key: 'attempt-1',
          workItemId: 'work-1',
          batchRef: 'batch-1',
          groupRef: 'cluster-1',
          attemptNumber: 1,
          status: 'retryable_failed',
          statusLabel: 'ответ не принят, будет повторная попытка',
          toneClassName: '',
          modelName: 'qwen/qwen3-32b',
          provider: 'groq',
          tokenCount: 3723,
          durationMs: null,
          startedAt: null,
          completedAt: null,
          errorMessage: 'LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE',
          artifacts: [],
        }}
      />,
    );

    expect(markup).toContain('ответ не принят, будет повторная попытка');
    expect(markup).toContain('groq · qwen/qwen3-32b · 3\u00a0723 токенов');
    expect(markup).not.toContain('· —');
    expect(markup).not.toContain('LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE');
    expect(markup).toContain('В ответе появилась латиница');
    expect(markup.match(/В ответе появилась латиница/g)).toHaveLength(1);
  });

  it('renders completed compaction artifacts with questions, exclusions and triples', () => {
    const markup = renderToStaticMarkup(
      <ClaimClusterCompactionAttemptRow
        attempt={{
          key: 'attempt-2',
          workItemId: 'work-1',
          batchRef: 'batch-1',
          groupRef: 'cluster-1',
          attemptNumber: 2,
          status: 'completed',
          statusLabel: 'ответ принят',
          toneClassName: '',
          modelName: 'qwen/qwen3-32b',
          provider: 'groq',
          tokenCount: 3877,
          durationMs: null,
          startedAt: null,
          completedAt: null,
          errorMessage: null,
          artifacts: [
            {
              cluster_ref: 'cluster-1',
              node_ref: 'node-2',
              claim: 'Axole помогает подготовить базу знаний.',
              source_claim_refs: ['claim-1'],
              active: true,
              compacted_payload: {
                claim: 'Axole помогает подготовить базу знаний.',
                possible_questions: ['Как подготовить знания?'],
                exclusion_scope: 'Не описывает цены.',
                triples: [
                  {
                    subject: 'Axole',
                    predicate: 'помогает',
                    object: 'подготовить базу знаний',
                  },
                ],
              },
            },
          ],
        }}
      />,
    );

    expect(markup).toContain('Axole помогает подготовить базу знаний.');
    expect(markup).toContain('Возможные вопросы');
    expect(markup).toContain('Как подготовить знания?');
    expect(markup).toContain('Исключения');
    expect(markup).toContain('Не описывает цены.');
    expect(markup).toContain('Связанные факты');
    expect(markup).toContain('Axole · помогает · подготовить базу знаний');
    expect(markup).not.toContain('Подробных артефактов');
  });
});
