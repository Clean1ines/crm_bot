import { t } from '@shared/i18n';
import type { RagEvalResultSummary, RagEvalReviewQuestion } from '@shared/api/modules/ragEval';

export const questionStatusClass = (statusValue: RagEvalReviewQuestion['retrieval_status']): string => {
  if (statusValue === 'reliable') return 'bg-emerald-500/10 text-emerald-600';
  if (statusValue === 'weak') return 'bg-amber-500/10 text-amber-600';
  return 'bg-red-500/10 text-red-600';
};

export const questionStatusIcon = (statusValue: RagEvalReviewQuestion['retrieval_status']): string => {
  if (statusValue === 'reliable') return '✅';
  if (statusValue === 'weak') return '⚠️';
  return '❌';
};

export const resultStatusLabel = (result: RagEvalResultSummary): string => {
  if (result.top1_hit) return t('ragEval.results.status.pass');
  if (result.expected_entry_found) return t('ragEval.results.status.weak');
  if (result.wrong_entry_top1) return t('ragEval.results.status.dangerous');
  return t('ragEval.results.status.fail');
};

export const resultStatusClass = (result: RagEvalResultSummary): string => {
  if (result.top1_hit) return 'border-emerald-500/30 bg-emerald-500/5 text-emerald-600';
  if (result.expected_entry_found) return 'border-amber-500/30 bg-amber-500/5 text-amber-600';
  return 'border-red-500/30 bg-red-500/5 text-red-600';
};
