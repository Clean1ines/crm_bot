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
        }}
      />,
    );

    expect(markup).toContain('ответ не принят, будет повторная попытка');
    expect(markup).toContain('groq · qwen/qwen3-32b · 3\u00a0723 токенов');
    expect(markup).not.toContain('· —');
    expect(markup).not.toContain('LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE');
    expect(markup).toContain('В ответе появилась латиница');
  });
});
