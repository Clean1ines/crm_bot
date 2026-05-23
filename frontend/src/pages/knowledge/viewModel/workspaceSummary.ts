export type KnowledgeWorkspaceStatus =
  | 'empty'
  | 'processing'
  | 'needs_review'
  | 'ready'
  | 'error';

export type KnowledgeWorkspaceCounterTone =
  | 'neutral'
  | 'success'
  | 'warning'
  | 'danger';

export type KnowledgeWorkspacePrimaryActionKind =
  | 'upload_document'
  | 'open_drafts'
  | 'review_commercial_truth'
  | 'review_documents';

import { type TranslationKey } from '@shared/i18n';

export type KnowledgeWorkspaceSummaryVm = {
  status: KnowledgeWorkspaceStatus;
  headlineKey: TranslationKey;
  descriptionKey: TranslationKey;
  counters: Array<{
    id: string;
    labelKey: TranslationKey;
    value: string;
    tone: KnowledgeWorkspaceCounterTone;
  }>;
  primaryAction: {
    kind: KnowledgeWorkspacePrimaryActionKind;
    labelKey: TranslationKey;
  };
};

export function buildKnowledgeWorkspaceSummary(input: {
  documents: Array<{
    id: string;
    status: string;
    error?: string | null;
  }>;
  hasProcessingDocuments: boolean;
  totalDrafts: number;
  runtimeEntryCount?: number;
  projectCommercialTruth?: {
    unresolved_conflict_count: number;
    conflict_count: number;
    surface_fact_ids: string[];
  };
}): KnowledgeWorkspaceSummaryVm {
  const status = (() => {
    if (input.documents.length === 0) return 'empty' as const;
    if (input.documents.some((d) => d.status === 'error' || Boolean(d.error && d.error.trim()))) return 'error' as const;
    if (input.hasProcessingDocuments) return 'processing' as const;
    if ((input.projectCommercialTruth?.unresolved_conflict_count ?? 0) > 0) return 'needs_review' as const;
    if (input.totalDrafts > 0) return 'needs_review' as const;
    return 'ready' as const;
  })();

  const primaryActionKind: KnowledgeWorkspacePrimaryActionKind = (() => {
    if (status === 'empty') return 'upload_document';
    if (status === 'error' || status === 'processing') return 'review_documents';
    if ((input.projectCommercialTruth?.unresolved_conflict_count ?? 0) > 0) return 'review_commercial_truth';
    if (input.totalDrafts > 0) return 'open_drafts';
    return 'review_documents';
  })();

  const counters: KnowledgeWorkspaceSummaryVm['counters'] = [
    {
      id: 'documents',
      labelKey: 'knowledge.workspaceSummary.counter.documents',
      value: String(input.documents.length),
      tone: input.documents.length > 0 ? 'success' : 'neutral',
    },
    {
      id: 'processing',
      labelKey: 'knowledge.workspaceSummary.counter.processing',
      value: String(input.hasProcessingDocuments ? input.documents.filter((d) => d.status === 'processing').length : 0),
      tone: input.hasProcessingDocuments ? 'warning' : 'neutral',
    },
  ];

  if (input.totalDrafts > 0) {
    counters.push({ id: 'drafts', labelKey: 'knowledge.workspaceSummary.counter.drafts', value: String(input.totalDrafts), tone: 'warning' });
  }
  if (input.projectCommercialTruth) {
    counters.push({ id: 'commercial_conflicts', labelKey: 'knowledge.workspaceSummary.counter.commercialConflicts', value: String(input.projectCommercialTruth.unresolved_conflict_count), tone: input.projectCommercialTruth.unresolved_conflict_count > 0 ? 'danger' : 'success' });
  }
  if (typeof input.runtimeEntryCount === 'number') {
    counters.push({ id: 'runtime_entries', labelKey: 'knowledge.workspaceSummary.counter.runtimeEntries', value: String(input.runtimeEntryCount), tone: 'neutral' });
  }

  const titleKeyByStatus: Record<KnowledgeWorkspaceStatus, TranslationKey> = {
    empty: 'knowledge.workspaceSummary.title.empty',
    processing: 'knowledge.workspaceSummary.title.processing',
    needs_review: 'knowledge.workspaceSummary.title.needsReview',
    ready: 'knowledge.workspaceSummary.title.ready',
    error: 'knowledge.workspaceSummary.title.error',
  };

  const descriptionKeyByStatus: Record<KnowledgeWorkspaceStatus, TranslationKey> = {
    empty: 'knowledge.workspaceSummary.description.empty',
    processing: 'knowledge.workspaceSummary.description.processing',
    needs_review: 'knowledge.workspaceSummary.description.needsReview',
    ready: 'knowledge.workspaceSummary.description.ready',
    error: 'knowledge.workspaceSummary.description.error',
  };

  const actionLabelByKind: Record<KnowledgeWorkspacePrimaryActionKind, TranslationKey> = {
    upload_document: 'knowledge.workspaceSummary.action.uploadDocument',
    open_drafts: 'knowledge.workspaceSummary.action.openDrafts',
    review_commercial_truth: 'knowledge.workspaceSummary.action.reviewCommercialTruth',
    review_documents: 'knowledge.workspaceSummary.action.reviewDocuments',
  };

  return {
    status,
    headlineKey: titleKeyByStatus[status],
    descriptionKey: descriptionKeyByStatus[status],
    counters,
    primaryAction: {
      kind: primaryActionKind,
      labelKey: actionLabelByKind[primaryActionKind],
    },
  };
}

