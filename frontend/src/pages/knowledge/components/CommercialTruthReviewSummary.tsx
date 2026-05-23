import React from 'react';
import { Loader2 } from 'lucide-react';

import {
  type KnowledgeCommercialTruthReviewPolicy,
  type KnowledgeCommercialTruthReviewResponse,
} from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const COMMERCIAL_TRUTH_REVIEW_POLICIES: KnowledgeCommercialTruthReviewPolicy[] = [
  'manual_review',
  'higher_authority_wins',
  'newer_source_wins',
];

const commercialTruthPolicyLabel = (
  policy: KnowledgeCommercialTruthReviewPolicy,
): string => {
  if (policy === 'manual_review') return t('knowledge.commercialTruth.policy.manualReview');
  if (policy === 'higher_authority_wins') return t('knowledge.commercialTruth.policy.higherAuthorityWins');
  if (policy === 'newer_source_wins') return t('knowledge.commercialTruth.policy.newerSourceWins');
  return policy;
};

const commercialTruthResolutionStatusLabel = (status: string): string => {
  if (status === 'resolved_by_policy') return t('knowledge.commercialTruth.status.resolved');
  if (status === 'unresolved') return t('knowledge.commercialTruth.status.unresolved');
  return status;
};

const commercialTruthRuntimeEligibleText = (value: boolean): string => (
  value ? 'true' : 'false'
);

const priceFactValueKindLabel = (valueKind: string): string => {
  if (valueKind === 'exact') return t('knowledge.priceFacts.value.exact');
  if (valueKind === 'starting_from') return t('knowledge.priceFacts.value.startingFrom');
  if (valueKind === 'range') return t('knowledge.priceFacts.value.range');
  if (valueKind === 'on_request') return t('knowledge.priceFacts.value.onRequest');
  return valueKind;
};

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

export const CommercialTruthReviewSummary: React.FC<{
  response: KnowledgeCommercialTruthReviewResponse | undefined;
  isLoading: boolean;
  policy: KnowledgeCommercialTruthReviewPolicy;
  onPolicyChange: (policy: KnowledgeCommercialTruthReviewPolicy) => void;
}> = ({ response, isLoading, policy, onPolicyChange }) => {
  if (isLoading && !response) {
    return (
      <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{t('knowledge.commercialTruth.loading')}</span>
        </div>
      </div>
    );
  }

  if (!response) return null;

  const previewConflicts = response.conflicts.slice(0, 2);
  const surfacePreviewCount = response.surface_fact_ids.length;
  const surfacePreviewFacts = response.surface_facts.slice(0, 3);

  return (
    <div className="mb-4 rounded-xl border border-[var(--accent-primary)]/20 bg-[var(--surface-secondary)] p-3 text-xs">
      <div className="mb-2 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-semibold text-[var(--text-primary)]">
            {t('knowledge.commercialTruth.title')}
          </div>
          <div className="mt-0.5 leading-relaxed text-[var(--text-muted)]">
            {t('knowledge.commercialTruth.subtitle')}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-[10px] font-medium uppercase tracking-wide text-[var(--text-muted)]">
            {t('knowledge.commercialTruth.policy.label')}
          </span>
          <div className="flex flex-wrap gap-1">
            {COMMERCIAL_TRUTH_REVIEW_POLICIES.map((candidate) => (
              <button
                key={candidate}
                type="button"
                onClick={() => onPolicyChange(candidate)}
                className={`rounded-full px-2 py-0.5 text-[10px] font-medium transition ${
                  candidate === policy
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--surface-elevated)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                }`}
              >
                {commercialTruthPolicyLabel(candidate)}
              </button>
            ))}
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="w-fit rounded-full bg-[var(--surface-elevated)] px-2 py-0.5 font-medium text-[var(--text-primary)]">
            {t('knowledge.commercialTruth.conflicts')}: {formatNumber(response.conflict_count)}
          </span>
          <span className="w-fit rounded-full bg-[var(--surface-elevated)] px-2 py-0.5 font-medium text-[var(--text-primary)]">
            {t('knowledge.commercialTruth.unresolvedConflicts')}: {formatNumber(response.unresolved_conflict_count)}
          </span>
          <span className="w-fit rounded-full bg-[var(--surface-elevated)] px-2 py-0.5 font-medium text-[var(--text-primary)]">
            {t('knowledge.commercialTruth.surfacePreview')}: {formatNumber(surfacePreviewCount)}
          </span>
        </div>
      </div>

      {surfacePreviewFacts.length > 0 && (
        <div className="mb-2 rounded-lg bg-[var(--surface-elevated)] px-3 py-2">
          <div className="font-medium text-[var(--text-primary)]">
            {t('knowledge.commercialTruth.surfacePreview')}
          </div>
          <div className="mt-1 space-y-1">
            {surfacePreviewFacts.map((fact) => (
              <div
                key={fact.fact_id}
                className="rounded-md bg-[var(--control-bg)] px-2 py-1 text-[10px] text-[var(--text-muted)]"
              >
                <span className="font-medium text-[var(--text-primary)]">{fact.item_name}</span>
                {' · '}
                <span className="font-semibold text-[var(--text-primary)]">
                  {fact.value_text || priceFactValueKindLabel(fact.value_kind)}
                </span>
                {' · '}
                {fact.source_title && (
                  <>
                    {' · '}
                    <span title={fact.source_title}>{fact.source_title}</span>
                  </>
                )}
                {fact.source_observed_at && (
                  <>
                    {' · '}
                    <span>{fact.source_observed_at.slice(0, 10)}</span>
                  </>
                )}
                {' · '}
                {t('knowledge.commercialTruth.fields.sourceKind')}: {fact.source_kind}
                {fact.source_quote && (
                  <>
                    {' · '}
                    <span title={fact.source_quote}>{fact.source_quote}</span>
                  </>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {response.fact_count === 0 ? (
        <div className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2 text-[var(--text-muted)]">
          {t('knowledge.commercialTruth.empty')}
        </div>
      ) : previewConflicts.length === 0 ? (
        <div className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2 text-[var(--text-muted)]">
          {t('knowledge.commercialTruth.noConflicts')}
        </div>
      ) : (
        <div className="space-y-2">
          {previewConflicts.map((conflict) => (
            <div
              key={conflict.identity_key}
              className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2"
            >
              <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="truncate font-medium text-[var(--text-primary)]" title={conflict.identity_key}>
                    {t('knowledge.commercialTruth.fields.identity')}: {conflict.identity_key}
                  </div>
                  <div className="mt-0.5 text-[var(--text-muted)]">
                    {t('knowledge.commercialTruth.fields.reason')}: {conflict.reason}
                  </div>
                </div>
                <span className="w-fit rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                  {commercialTruthResolutionStatusLabel(conflict.resolution_status)}
                </span>
              </div>

              <div className="mt-2 space-y-1">
                {conflict.options.slice(0, 3).map((option) => (
                  <div
                    key={option.fact_id}
                    className="rounded-md bg-[var(--control-bg)] px-2 py-1 text-[10px] text-[var(--text-muted)]"
                  >
                    <span className="font-medium text-[var(--text-primary)]">{option.item_name}</span>
                    {' · '}
                    <span className="font-semibold text-[var(--text-primary)]">
                      {option.value_text || priceFactValueKindLabel(option.value_kind)}
                    </span>
                    {' · '}
                    {option.source_title && (
                      <>
                        {' · '}
                        <span title={option.source_title}>{option.source_title}</span>
                      </>
                    )}
                    {option.source_observed_at && (
                      <>
                        {' · '}
                        <span>{option.source_observed_at.slice(0, 10)}</span>
                      </>
                    )}
                    {' · '}
                    {t('knowledge.commercialTruth.fields.sourceKind')}: {option.source_kind}
                    {' · '}
                    {t('knowledge.commercialTruth.fields.sourceAuthority')}: {option.source_authority}
                    {' · '}
                    {t('knowledge.commercialTruth.fields.runtimeEligible')}: {commercialTruthRuntimeEligibleText(option.is_runtime_eligible)}
                    {option.source_quote && (
                      <>
                        {' · '}
                        <span title={option.source_quote}>{option.source_quote}</span>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
