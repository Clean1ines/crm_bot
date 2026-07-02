import React from 'react';
import type { WorkbenchClaimClusterClaimLiveState } from '@shared/api/modules/knowledge';

import { embeddingStatusLabel, nodeActivityLabel } from '../workflow-card/workflowCardLabels';

type ClaimClusterClaimRowProps = {
  claim: WorkbenchClaimClusterClaimLiveState;
  formatNumber: (value: number) => string;
};

export const ClaimClusterClaimRow: React.FC<ClaimClusterClaimRowProps> = ({
  claim,
  formatNumber,
}) => (
  <details key={claim.observation_ref} className="rounded bg-[var(--surface-elevated)] p-2">
    <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
      {claim.claim}
    </summary>
    <div className="mt-2 space-y-2 text-[var(--text-secondary)]">
      <div>
        <span className="font-medium text-[var(--text-primary)]">Гранулярность:</span>{' '}
        {claim.granularity}
      </div>
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
      <div>
        <div className="font-medium text-[var(--text-primary)]">Источник</div>
        <div>{claim.source_unit_ref}</div>
        <div className="text-[var(--text-muted)]">документ: {claim.source_document_ref}</div>
      </div>
      <div>
        <div className="font-medium text-[var(--text-primary)]">Embedding</div>
        <div>
          {claim.embedding_model_id || 'модель не указана'}
          {claim.embedding_dimensions
            ? ` · ${formatNumber(claim.embedding_dimensions)} изм.`
            : ''}
          {' · '}
          {embeddingStatusLabel(claim.embedding_status)}
        </div>
        {claim.embedding_ref && (
          <div className="font-mono text-[11px] text-[var(--text-muted)]">
            {claim.embedding_ref}
          </div>
        )}
      </div>
      <div>
        <div className="font-medium text-[var(--text-primary)]">Узел compaction</div>
        <div>
          {claim.node_kind || 'тип не указан'} · {nodeActivityLabel(claim)} ·{' '}
          {claim.node_status}
        </div>
        {claim.node_ref && (
          <div className="font-mono text-[11px] text-[var(--text-muted)]">
            {claim.node_ref}
          </div>
        )}
      </div>
    </div>
  </details>
);
