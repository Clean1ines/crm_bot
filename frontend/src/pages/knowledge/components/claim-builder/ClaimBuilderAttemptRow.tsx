import {
  claimBuilderAttemptRowTone,
  claimBuilderAttemptStatusLabel,
  claimBuilderUserErrorLabel,
  formatClaimBuilderMilliseconds,
  formatClaimBuilderNumber,
} from './claimBuilderLabels';
import { ClaimBuilderDraftClaimArtifact } from './ClaimBuilderDraftClaimArtifact';
import type { ClaimBuilderAttemptView } from './claimBuilderTypes';

type ClaimBuilderAttemptRowProps = {
  attempt: ClaimBuilderAttemptView;
};

export const ClaimBuilderAttemptRow = ({ attempt }: ClaimBuilderAttemptRowProps) => {
  const tokenText =
    attempt.totalTokens > 0
      ? `${formatClaimBuilderNumber(attempt.totalTokens)} токенов`
      : 'токены пока не записаны';

  const modelText = [
    attempt.provider,
    attempt.modelRef,
  ]
    .filter((value): value is string => Boolean(value && value.trim()))
    .join(' · ');

  return (
    <details className={`rounded-lg border px-2.5 py-2 ${claimBuilderAttemptRowTone(attempt.status)}`}>
      <summary className="cursor-pointer list-none">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="min-w-0">
            <span className="font-medium text-[var(--text-primary)]">
              {claimBuilderAttemptStatusLabel(attempt.status)}
            </span>
            <span className="ml-2 text-xs text-[var(--text-muted)]">
              {modelText || 'модель не указана'} · {tokenText} ·{' '}
              {formatClaimBuilderMilliseconds(attempt.durationMs)}
            </span>
          </span>

          {attempt.errorKind && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
              {claimBuilderUserErrorLabel(attempt.errorKind)}
            </span>
          )}
        </span>
      </summary>

      <div className="mt-2 space-y-2">
        {attempt.errorMessageUser && (
          <div className="text-xs text-amber-700 dark:text-amber-300">
            {attempt.errorMessageUser}
          </div>
        )}

        {attempt.artifacts.length > 0 ? (
          <div className="space-y-1.5">
            {attempt.artifacts.map((artifact) => (
              <ClaimBuilderDraftClaimArtifact
                key={artifact.observationRef}
                artifact={artifact}
              />
            ))}
          </div>
        ) : (
          <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
            Извлечённых фактов в этой попытке нет.
          </div>
        )}
      </div>
    </details>
  );
};
