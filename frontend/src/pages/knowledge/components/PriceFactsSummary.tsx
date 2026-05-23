import React from 'react';
import { Loader2 } from 'lucide-react';

import { type KnowledgePriceFact, type KnowledgePriceFactsResponse } from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const priceFactStatusLabel = (status: string): string => {
  if (status === 'needs_review') return t('knowledge.priceFacts.status.needsReview');
  if (status === 'published') return t('knowledge.priceFacts.status.published');
  if (status === 'rejected') return t('knowledge.priceFacts.status.rejected');
  if (status === 'draft') return t('knowledge.priceFacts.status.draft');
  if (status === 'superseded') return t('knowledge.priceFacts.status.superseded');
  return status;
};

const priceFactValueKindLabel = (valueKind: string): string => {
  if (valueKind === 'exact') return t('knowledge.priceFacts.value.exact');
  if (valueKind === 'starting_from') return t('knowledge.priceFacts.value.startingFrom');
  if (valueKind === 'range') return t('knowledge.priceFacts.value.range');
  if (valueKind === 'on_request') return t('knowledge.priceFacts.value.onRequest');
  return valueKind;
};

const priceMoneyText = (amount: { amount: string; currency: string }): string => (
  `${amount.amount} ${amount.currency}`
);

const priceFactValueText = (fact: KnowledgePriceFact): string => {
  if (fact.amount) return priceMoneyText(fact.amount);
  if (fact.price_range) {
    return `${priceMoneyText(fact.price_range.min_amount)} – ${priceMoneyText(fact.price_range.max_amount)}`;
  }
  if (fact.price_text.trim()) return fact.price_text;
  return priceFactValueKindLabel(fact.value_kind);
};

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

export const PriceFactsSummary: React.FC<{
  response: KnowledgePriceFactsResponse | undefined;
  isLoading: boolean;
  onPublishFact: (fact: KnowledgePriceFact) => void;
  onRejectFact: (fact: KnowledgePriceFact) => void;
  mutatingFactId: string | null;
}> = ({ response, isLoading, onPublishFact, onRejectFact, mutatingFactId }) => {
  if (isLoading && !response) {
    return (
      <div className="mb-4 rounded-xl bg-[var(--surface-secondary)] p-3 text-xs text-[var(--text-muted)]">
        <div className="flex items-center gap-2">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          <span>{t('knowledge.priceFacts.loading')}</span>
        </div>
      </div>
    );
  }

  if (!response || response.facts.length === 0) return null;

  const previewFacts = response.facts.slice(0, 3);
  const needsReviewCount = response.facts.filter((fact) => fact.status === 'needs_review').length;

  return (
    <div className="mb-4 rounded-xl border border-[var(--accent-primary)]/20 bg-[var(--accent-primary)]/5 p-3 text-xs">
      <div className="mb-2 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-semibold text-[var(--text-primary)]">
            {t('knowledge.priceFacts.title')}
          </div>
          <div className="mt-0.5 leading-relaxed text-[var(--text-muted)]">
            {t('knowledge.priceFacts.subtitle')}
          </div>
        </div>
        {needsReviewCount > 0 && (
          <span className="w-fit rounded-full bg-[var(--accent-primary)]/10 px-2 py-0.5 font-medium text-[var(--accent-primary)]">
            {t('knowledge.priceFacts.status.needsReview')}: {formatNumber(needsReviewCount)}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {previewFacts.map((fact) => {
          const firstSourceRef = fact.source_refs[0];
          const isReviewFact = fact.status === 'needs_review';
          const isMutatingFact = mutatingFactId === fact.id;
          return (
            <div
              key={fact.id}
              className="rounded-lg bg-[var(--surface-elevated)] px-3 py-2"
            >
              <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <div className="truncate font-medium text-[var(--text-primary)]" title={fact.item_name}>
                    {fact.item_name}
                  </div>
                  <div className="mt-0.5 text-[var(--text-muted)]">
                    {priceFactValueKindLabel(fact.value_kind)} · {t('knowledge.priceFacts.fields.unit')}: {fact.unit || '—'}
                  </div>
                </div>
                <div className="font-semibold text-[var(--text-primary)]">
                  {priceFactValueText(fact)}
                </div>
              </div>

              <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                  {priceFactStatusLabel(fact.status)}
                </span>
                <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                  {t('knowledge.priceFacts.fields.confidence')}: {fact.confidence}
                </span>
                {Object.keys(fact.variant).length > 0 && (
                  <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                    {t('knowledge.priceFacts.fields.variant')}: {Object.entries(fact.variant).map(([key, value]) => `${key}=${value}`).join(', ')}
                  </span>
                )}
                {firstSourceRef?.quote && (
                  <span className="max-w-full truncate rounded-full bg-[var(--control-bg)] px-2 py-0.5" title={firstSourceRef.quote}>
                    {t('knowledge.priceFacts.fields.source')}: {firstSourceRef.quote}
                  </span>
                )}
              </div>

              {isReviewFact && (
                <div className="mt-2 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onPublishFact(fact)}
                    disabled={isMutatingFact}
                    className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-[10px] font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-wait disabled:opacity-60"
                  >
                    {isMutatingFact ? t('common.states.loading') : t('knowledge.priceFacts.actions.publish')}
                  </button>
                  <button
                    type="button"
                    onClick={() => onRejectFact(fact)}
                    disabled={isMutatingFact}
                    className="rounded-full bg-[var(--accent-danger-bg)] px-2 py-1 text-[10px] font-medium text-[var(--accent-danger-text)] transition-colors hover:opacity-80 disabled:cursor-wait disabled:opacity-60"
                  >
                    {isMutatingFact ? t('common.states.loading') : t('knowledge.priceFacts.actions.reject')}
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
