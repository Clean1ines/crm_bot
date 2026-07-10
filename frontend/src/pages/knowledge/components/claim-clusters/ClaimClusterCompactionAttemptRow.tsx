import {
  claimBuilderAttemptRowTone,
  claimBuilderAttemptStatusLabel,
  claimBuilderUserErrorLabel,
  formatClaimBuilderMilliseconds,
  formatClaimBuilderNumber,
} from '../claim-builder/claimBuilderLabels';
import type {
  ClaimClusterCompactionAttemptView,
  FinalCompactedFact,
} from './claimClusterTypes';

type CompactedTriple = NonNullable<
  NonNullable<FinalCompactedFact['compacted_payload']>['triples']
>[number];

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
  const hasArtifacts = attempt.artifacts.length > 0;

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

        </span>
      </summary>

      <div className="mt-2 space-y-2">
        {userErrorText && (
          <div className="text-xs text-amber-700 dark:text-amber-300">
            {userErrorText}
          </div>
        )}

        {hasArtifacts ? (
          <div className="space-y-1.5">
            {attempt.artifacts.map((artifact) => (
              <CompactionAttemptArtifact
                key={`${attempt.key}:${artifact.node_ref}`}
                artifact={artifact}
              />
            ))}
          </div>
        ) : !userErrorText ? (
          <div className="rounded border border-dashed border-[var(--border-subtle)] px-2 py-1.5 text-xs text-[var(--text-muted)]">
            Уплотнённых фактов в этой попытке нет.
          </div>
        ) : null}
      </div>
    </details>
  );
};

const CompactionAttemptArtifact = ({ artifact }: { artifact: FinalCompactedFact }) => {
  const payload = artifact.compacted_payload;
  const claim = payload?.claim?.trim() || artifact.claim;
  const possibleQuestions = payload?.possible_questions ?? [];
  const exclusionScope = payload?.exclusion_scope?.trim() ?? '';
  const triples = payload?.triples ?? [];

  return (
    <div className="rounded border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2 py-1.5 text-xs text-[var(--text-secondary)]">
      <div className="font-medium text-[var(--text-primary)]">{claim}</div>

      {possibleQuestions.length > 0 && (
        <div className="mt-2">
          <div className="font-medium text-[var(--text-primary)]">Возможные вопросы</div>
          <ul className="mt-1 list-disc pl-5">
            {possibleQuestions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        </div>
      )}

      {exclusionScope && (
        <div className="mt-2">
          <div className="font-medium text-[var(--text-primary)]">Исключения</div>
          <div className="mt-1 whitespace-pre-wrap">{exclusionScope}</div>
        </div>
      )}

      {triples.length > 0 && (
        <div className="mt-2">
          <div className="font-medium text-[var(--text-primary)]">Связанные факты</div>
          <ul className="mt-1 list-disc pl-5">
            {triples.map((triple: CompactedTriple, index: number) => (
              <li
                key={`${triple.subject ?? 'subject'}-${triple.predicate ?? 'predicate'}-${triple.object ?? 'object'}-${index}`}
              >
                {[triple.subject, triple.predicate, triple.object]
                  .filter((value): value is string => Boolean(value && value.trim()))
                  .join(' · ')}
                {(triple.qualifiers ?? []).length > 0
                  ? ` (${(triple.qualifiers ?? []).join(', ')})`
                  : ''}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
