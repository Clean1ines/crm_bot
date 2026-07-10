import {
  claimBuilderAttemptRowTone,
  claimBuilderAttemptStatusLabel,
  claimBuilderUserErrorLabel,
  formatClaimBuilderMilliseconds,
  formatClaimBuilderNumber,
} from '../claim-builder/claimBuilderLabels';
import type { ClaimClusterCompactionAttemptView } from './claimClusterTypes';

type ClaimClusterCompactionAttemptRowProps = {
  attempt: ClaimClusterCompactionAttemptView;
};

export const ClaimClusterCompactionAttemptRow = ({
  attempt,
}: ClaimClusterCompactionAttemptRowProps) => {
  const tokenText =
    attempt.tokenCount > 0
      ? `${formatClaimBuilderNumber(attempt.tokenCount)} токенов`
      : 'токены пока не записаны';

  const modelText = [
    attempt.provider,
    attempt.modelName,
  ]
    .filter((value): value is string => Boolean(value && value.trim()))
    .join(' · ');
  const durationText = formatClaimBuilderMilliseconds(attempt.durationMs);
  const metaText = [
    modelText || 'модель не указана',
    tokenText,
    durationText === '—' ? null : durationText,
  ]
    .filter((value): value is string => Boolean(value))
    .join(' · ');
  const userErrorText = attempt.errorMessage
    ? claimBuilderUserErrorLabel(attempt.errorMessage)
    : null;

  return (
    <details className={`rounded-lg border px-2.5 py-2 ${claimBuilderAttemptRowTone(attempt.status)}`}>
      <summary className="cursor-pointer list-none">
        <span className="flex flex-wrap items-center justify-between gap-2">
          <span className="min-w-0">
            <span className="font-medium text-[var(--text-primary)]">
              {claimBuilderAttemptStatusLabel(attempt.status)}
            </span>
            <span className="ml-2 text-xs text-[var(--text-muted)]">
              {metaText}
            </span>
          </span>

          {userErrorText && (
            <span className="rounded-full bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
              {userErrorText}
            </span>
          )}
        </span>
      </summary>

      <div className="mt-2 space-y-2">
        {userErrorText ? (
          <div className="text-xs text-amber-700 dark:text-amber-300">
            {userErrorText}
          </div>
        ) : (
          <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
            Подробных артефактов этой попытки пока нет в live-событии.
          </div>
        )}
      </div>
    </details>
  );
};
