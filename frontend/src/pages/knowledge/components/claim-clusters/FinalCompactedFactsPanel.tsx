import React from 'react';
import type { WorkbenchCompactedClaimPreviewLiveState } from '@shared/api/modules/knowledge';

import type { FinalCompactedFact } from './claimClusterTypes';

type FinalCompactedFactsPanelProps = {
  facts: FinalCompactedFact[];
  formatNumber: (value: number) => string;
};

type CompactedPayloadTriple = NonNullable<
  NonNullable<WorkbenchCompactedClaimPreviewLiveState['compacted_payload']>['triples']
>[number];

const EnrichedCompactedArtifact = ({
  compactedClaim,
}: {
  compactedClaim: WorkbenchCompactedClaimPreviewLiveState;
}) => {
  const artifact = compactedClaim.compacted_payload;
  const triples = artifact?.triples ?? [];
  const possibleQuestions: string[] = artifact?.possible_questions ?? [];
  const exclusionScope = artifact?.exclusion_scope?.trim() ?? '';
  const evidenceBlock = artifact?.evidence_block?.trim() ?? '';

  return (
    <details className="mt-2 rounded bg-[var(--control-bg)] p-2" open>
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Enriched artifact
      </summary>
      <div className="mt-2 space-y-3 text-[var(--text-secondary)]">
        <div>
          <div className="font-medium text-[var(--text-primary)]">Утверждение</div>
          <div>{artifact?.claim || compactedClaim.claim}</div>
        </div>

        <div className="grid gap-1 text-[var(--text-muted)] [grid-template-columns:repeat(auto-fit,minmax(150px,1fr))]">
          <div>Тип: {artifact?.claim_kind || compactedClaim.claim_kind || '—'}</div>
          <div>Гранулярность: {artifact?.granularity || compactedClaim.granularity || '—'}</div>
          <div>Решение: {artifact?.merge_decision || compactedClaim.merge_decision || '—'}</div>
        </div>

        {possibleQuestions.length > 0 && (
          <div>
            <div className="font-medium text-[var(--text-primary)]">
              Возможные вопросы
            </div>
            <ul className="mt-1 list-disc pl-5">
              {possibleQuestions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          </div>
        )}

        {exclusionScope && (
          <div>
            <div className="font-medium text-[var(--text-primary)]">Исключения</div>
            <pre className="mt-1 whitespace-pre-wrap rounded bg-[var(--surface-elevated)] p-2 text-[var(--text-secondary)]">
              {exclusionScope}
            </pre>
          </div>
        )}

        {triples.length > 0 && (
          <div>
            <div className="font-medium text-[var(--text-primary)]">Тройки</div>
            <ul className="mt-1 list-disc pl-5">
              {triples.map((triple: CompactedPayloadTriple, index: number) => (
                <li key={`${triple.subject ?? 's'}-${triple.predicate ?? 'p'}-${triple.object ?? 'o'}-${index}`}>
                  {triple.subject || '—'} · {triple.predicate || '—'} · {triple.object || '—'}
                  {(triple.qualifiers ?? []).length > 0
                    ? ` (${(triple.qualifiers ?? []).join(', ')})`
                    : ''}
                </li>
              ))}
            </ul>
          </div>
        )}

        {evidenceBlock && (
          <div>
            <div className="font-medium text-[var(--text-primary)]">Доказательство</div>
            <blockquote className="mt-1 whitespace-pre-wrap rounded border-l-2 border-[var(--accent-primary)] bg-[var(--surface-elevated)] p-2">
              {evidenceBlock}
            </blockquote>
          </div>
        )}
      </div>
    </details>
  );
};

export const FinalCompactedFactsPanel: React.FC<FinalCompactedFactsPanelProps> = ({
  facts,
  formatNumber,
}) => {
  if (facts.length === 0) return null;

  return (
    <section className="mt-3 rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
      <div className="font-medium text-[var(--text-primary)]">
        Итоговые факты: {formatNumber(facts.length)}
      </div>
      <div className="mt-2 max-h-64 space-y-2 overflow-y-auto pr-1">
        {facts.map((fact, index) => (
          <div
            key={`${fact.cluster_ref}:${fact.node_ref}`}
            className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2"
          >
            <div className="text-[var(--text-primary)]">
              <span className="mr-2 text-emerald-700 dark:text-emerald-300">
                {formatNumber(index + 1)}.
              </span>
              {fact.claim}
            </div>
            <div className="mt-1 text-[11px] text-[var(--text-muted)]">
              {fact.source_claim_refs.length > 1
                ? `Объединено из ${formatNumber(fact.source_claim_refs.length)} фактов`
                : 'Сохранён как отдельный факт'}
            </div>
            <EnrichedCompactedArtifact compactedClaim={fact} />
          </div>
        ))}
      </div>
    </section>
  );
};
