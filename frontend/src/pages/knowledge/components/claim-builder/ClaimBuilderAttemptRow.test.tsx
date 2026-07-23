import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ClaimBuilderAttemptRow } from './ClaimBuilderAttemptRow';

describe('ClaimBuilderAttemptRow', () => {
  it('renders retry validation errors as user text without placeholder dash', () => {
    const markup = renderToStaticMarkup(
      <ClaimBuilderAttemptRow
        attempt={{
          nodeRunId: 'attempt-1',
          sectionId: 'section-1',
          status: 'retryable_failed',
          provider: 'groq',
          modelRef: 'qwen/qwen3.6-27b',
          promptTokens: 3500,
          completionTokens: 223,
          totalTokens: 3723,
          errorKind: 'LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE',
          errorMessageUser: 'LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE',
          nextAttemptAt: null,
          userActionRequired: false,
          blockedReason: null,
          startedAt: null,
          completedAt: null,
          durationMs: null,
          artifacts: [],
        }}
      />,
    );

    expect(markup).toContain('ответ не принят, будет повторная попытка');
    expect(markup).toContain('groq · qwen/qwen3.6-27b · 3\u00a0723 токенов');
    expect(markup).not.toContain('· —');
    expect(markup).not.toContain('LATIN_TEXT_NOT_SUPPORTED_BY_EVIDENCE');
    expect(markup).toContain('В ответе появилась латиница');
  });
});
