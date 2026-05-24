import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { BookOpen } from 'lucide-react';
import { useParams } from 'react-router-dom';

import {
  knowledgeApi,
  type KnowledgeUsageBreakdown,
  type KnowledgeUsageResponse,
} from '@shared/api/modules/knowledge';
import { t } from '@shared/i18n';

const formatNumber = (value: number): string => new Intl.NumberFormat('ru-RU').format(value);

const formatUsd = (value: number): string => new Intl.NumberFormat('ru-RU', {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
}).format(value);

const LLM_USAGE_TYPE = 'llm';

const USER_ANSWER_USAGE_SOURCES = new Set([
  'client_response',
  'user_response',
  'agent_response',
  'conversation_answer',
]);

const KNOWLEDGE_UPLOAD_USAGE_SOURCES = new Set([
  'knowledge_preprocessing',
  'knowledge_upload',
]);

const RAG_EVAL_USAGE_SOURCES = new Set([
  'rag_eval',
  'rag_eval_dataset',
  'rag_eval_judge',
  'rag_search',
]);

const llmUsageBreakdown = (
  breakdown: KnowledgeUsageBreakdown[],
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => item.usage_type === LLM_USAGE_TYPE)
);

const usageBySources = (
  breakdown: KnowledgeUsageBreakdown[],
  sources: Set<string>,
): KnowledgeUsageBreakdown[] => (
  breakdown.filter((item) => sources.has(item.source))
);

const sumUsageTokens = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.tokens_total, 0)
);

const sumUsageCost = (breakdown: KnowledgeUsageBreakdown[]): number => (
  breakdown.reduce((acc, item) => acc + item.estimated_cost_usd, 0)
);

const usageModelRows = (breakdown: KnowledgeUsageBreakdown[]): string[] => {
  const events = breakdown.reduce((acc, item) => acc + item.events_count, 0);
  return events > 0 ? [t('knowledge.metrics.operations', { count: formatNumber(events) })] : [];
};

const UsageScenarioCard: React.FC<{
  title: string;
  description: string;
  breakdown: KnowledgeUsageBreakdown[];
  emptyText: string;
}> = ({ title, description, breakdown, emptyText }) => {
  const tokens = sumUsageTokens(breakdown);
  const modelRows = usageModelRows(breakdown);

  return (
    <div className="rounded-xl bg-[var(--surface-secondary)] p-4">
      <div className="text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
        {title}
      </div>
      <div className="mt-2 text-2xl font-semibold text-[var(--text-primary)]">
        {formatNumber(tokens)}
      </div>
      <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
        {description}
      </p>
      <div className="mt-3 space-y-1 text-xs text-[var(--text-muted)]">
        {modelRows.length > 0 ? (
          modelRows.map((row) => <div key={row}>{row}</div>)
        ) : (
          <div>{emptyText}</div>
        )}
      </div>
    </div>
  );
};

const UsageSummaryCard: React.FC<{ usage: KnowledgeUsageResponse }> = ({ usage }) => {
  const llmBreakdown = llmUsageBreakdown(usage.breakdown);
  const answerBreakdown = usageBySources(llmBreakdown, USER_ANSWER_USAGE_SOURCES);
  const uploadBreakdown = usageBySources(llmBreakdown, KNOWLEDGE_UPLOAD_USAGE_SOURCES);
  const ragEvalBreakdown = usageBySources(llmBreakdown, RAG_EVAL_USAGE_SOURCES);
  const totalTokens = sumUsageTokens(llmBreakdown);
  const totalCost = sumUsageCost(llmBreakdown);

  return (
    <section className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-sm sm:p-5 lg:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]">
          <BookOpen className="h-5 w-5" />
        </div>
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            {t('knowledge.usage.title')}
          </h2>
          <p className="mt-1 text-sm text-[var(--text-muted)]">
            {t('knowledge.usage.description')}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
        <UsageScenarioCard
          title={t('knowledge.usage.totalTitle')}
          description={t('knowledge.usage.totalDescription', { cost: formatUsd(totalCost) })}
          breakdown={llmBreakdown}
          emptyText={t('knowledge.usage.totalEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.clientAnswersTitle')}
          description={t('knowledge.usage.clientAnswersDescription')}
          breakdown={answerBreakdown}
          emptyText={t('knowledge.usage.clientAnswersEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.knowledgeProcessingTitle')}
          description={t('knowledge.usage.knowledgeProcessingDescription')}
          breakdown={uploadBreakdown}
          emptyText={t('knowledge.usage.knowledgeProcessingEmpty')}
        />
        <UsageScenarioCard
          title={t('knowledge.usage.qualityChecksTitle')}
          description={t('knowledge.usage.qualityChecksDescription')}
          breakdown={ragEvalBreakdown}
          emptyText={t('knowledge.usage.qualityChecksEmpty')}
        />
      </div>

      <div className="mt-4 text-sm text-[var(--text-muted)]">
        {t('knowledge.usage.monthlyVolume', { total: formatNumber(totalTokens) })}
      </div>
    </section>
  );
};

export const KnowledgeStatsPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();

  const usageQuery = useQuery({
    queryKey: ['knowledge-usage', projectId],
    queryFn: async () => {
      if (!projectId) throw new Error('projectId is required');
      const { data } = await knowledgeApi.usage(projectId);
      return data;
    },
    enabled: Boolean(projectId),
    retry: false,
  });

  const usage = usageQuery.data;

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-4 sm:p-6 lg:p-8">
      <div>
        <h1 className="text-2xl font-semibold leading-tight text-[var(--text-primary)] sm:text-3xl">
          {t('knowledge.statistics.pageTitle')}
        </h1>
        <p className="mt-2 text-sm text-[var(--text-muted)]">
          {t('knowledge.statistics.pageDescription')}
        </p>
      </div>

      {usage && usage.counter_enabled ? (
        <UsageSummaryCard usage={usage} />
      ) : (
        <section className="rounded-2xl bg-[var(--surface-elevated)] p-5 text-sm text-[var(--text-muted)] shadow-sm">
          {usageQuery.isLoading ? t('knowledge.statistics.loading') : t('knowledge.statistics.empty')}
        </section>
      )}
    </div>
  );
};
