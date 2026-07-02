import React from 'react';
import type { WorkbenchClaimClusterClaimLiveState } from '@shared/api/modules/knowledge';

type ClaimClusterClaimRowProps = {
  claim: WorkbenchClaimClusterClaimLiveState;
};

export const ClaimClusterClaimRow: React.FC<ClaimClusterClaimRowProps> = ({
  claim,
}) => (
  <details key={claim.observation_ref} className="rounded bg-[var(--surface-elevated)] p-2">
    <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
      {claim.claim}
    </summary>
    <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
      <div>
        <div className="font-medium text-[var(--text-primary)]">Возможные вопросы</div>
        {claim.possible_questions.length > 0 ? (
          <ul className="mt-1 list-disc pl-5">
            {claim.possible_questions.map((question) => (
              <li key={question}>{question}</li>
            ))}
          </ul>
        ) : (
          <div className="mt-1 text-[var(--text-muted)]">—</div>
        )}
      </div>
      <div>
        <div className="font-medium text-[var(--text-primary)]">Исключения</div>
        {claim.exclusion_scope.length > 0 ? (
          <ul className="mt-1 list-disc pl-5">
            {claim.exclusion_scope.map((exclusion) => (
              <li key={exclusion}>{exclusion}</li>
            ))}
          </ul>
        ) : (
          <div className="mt-1 text-[var(--text-muted)]">—</div>
        )}
      </div>
    </div>
  </details>
);
