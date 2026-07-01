import type { ClaimBuilderDraftClaimArtifactView } from './claimBuilderTypes';

type ClaimBuilderDraftClaimArtifactProps = {
  artifact: ClaimBuilderDraftClaimArtifactView;
};

export const ClaimBuilderDraftClaimArtifact = ({
  artifact,
}: ClaimBuilderDraftClaimArtifactProps) => (
  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-3">
    <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
      Факт
    </div>
    <p className="mt-1 text-sm text-[var(--text-primary)]">{artifact.claim}</p>

    {artifact.possibleQuestions.length > 0 && (
      <div className="mt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
          Вопросы
        </div>
        <ul className="mt-1 list-disc space-y-1 pl-4 text-xs text-[var(--text-secondary)]">
          {artifact.possibleQuestions.map((question, index) => (
            <li key={`${artifact.observationRef}-question-${index}`}>{question}</li>
          ))}
        </ul>
      </div>
    )}

    {artifact.exclusionScope.trim().length > 0 && (
      <div className="mt-3">
        <div className="text-xs font-medium uppercase tracking-wide text-[var(--text-muted)]">
          Не является темой факта
        </div>
        <p className="mt-1 whitespace-pre-wrap text-xs text-[var(--text-secondary)]">
          {artifact.exclusionScope}
        </p>
      </div>
    )}
  </div>
);
