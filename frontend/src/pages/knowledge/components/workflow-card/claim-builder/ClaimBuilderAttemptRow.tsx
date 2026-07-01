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
    <div className={`rounded-xl border p-3 ${claimBuilderAttemptRowTone(attempt.status)}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="text-sm font-medium text-[var(--text-primary)]">
            {claimBuilderAttemptStatusLabel(attempt.status)}
          </div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">
            {modelText || 'модель не указана'} · {tokenText} ·{' '}
            {formatClaimBuilderMilliseconds(attempt.durationMs)}
          </div>
        </div>

        {attempt.errorKind && (
          <span className="rounded-full bg-amber-500/10 px-2 py-1 text-xs text-amber-700 dark:text-amber-300">
            {claimBuilderUserErrorLabel(attempt.errorKind)}
          </span>
        )}
      </div>

      {attempt.errorMessageUser && (
        <p className="mt-2 text-xs text-amber-700 dark:text-amber-300">
          {attempt.errorMessageUser}
        </p>
      )}

      {attempt.artifacts.length > 0 && (
        <div className="mt-3 space-y-2">
          {attempt.artifacts.map((artifact) => (
            <ClaimBuilderDraftClaimArtifact
              key={artifact.observationRef}
              artifact={artifact}
            />
          ))}
        </div>
      )}
    </div>
  );
};
