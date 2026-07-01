import type { ClaimBuilderDraftClaimArtifactView } from './claimBuilderTypes';

type ClaimBuilderDraftClaimArtifactProps = {
  artifact: ClaimBuilderDraftClaimArtifactView;
};

export const ClaimBuilderDraftClaimArtifact = ({
  artifact,
}: ClaimBuilderDraftClaimArtifactProps) => (
  <details className="rounded border border-[var(--border-subtle)] bg-[var(--surface-elevated)] px-2.5 py-2">
    <summary className="cursor-pointer list-none">
      <span className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <span className="min-w-0">
          <span className="font-medium text-[var(--text-primary)]">Факт</span>
          <span className="ml-2 text-xs text-[var(--text-muted)]">
            #{artifact.claimIndex + 1}
          </span>
        </span>
        <span className="min-w-0 truncate text-xs text-[var(--text-secondary)]">
          {artifact.claim}
        </span>
      </span>
    </summary>

    <div className="mt-2 space-y-3 text-xs text-[var(--text-secondary)]">
      <div>
        <div className="font-medium uppercase tracking-wide text-[var(--text-muted)]">
          Утверждение
        </div>
        <p className="mt-1 text-sm text-[var(--text-primary)]">{artifact.claim}</p>
      </div>

      {artifact.possibleQuestions.length > 0 && (
        <div>
          <div className="font-medium uppercase tracking-wide text-[var(--text-muted)]">
            Вопросы
          </div>
          <ul className="mt-1 list-disc space-y-1 pl-4">
            {artifact.possibleQuestions.map((question, index) => (
              <li key={`${artifact.observationRef}-question-${index}`}>{question}</li>
            ))}
          </ul>
        </div>
      )}

      {artifact.exclusionScope.trim().length > 0 && (
        <div>
          <div className="font-medium uppercase tracking-wide text-[var(--text-muted)]">
            Не является темой факта
          </div>
          <p className="mt-1 whitespace-pre-wrap">{artifact.exclusionScope}</p>
        </div>
      )}

      <div className="grid gap-1 text-[var(--text-muted)] [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
        <div>Granularity: {artifact.granularity || '—'}</div>
        <div>Provider: {artifact.provider || '—'}</div>
        <div>Model: {artifact.modelRef || '—'}</div>
        <div>Validation: {artifact.validationDecision || '—'}</div>
      </div>
    </div>
  </details>
);
