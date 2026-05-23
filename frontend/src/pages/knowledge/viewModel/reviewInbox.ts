import type { TranslationKey } from '../../../shared/i18n/types';

export type KnowledgeReviewTaskSeverity =
  | 'critical'
  | 'warning'
  | 'info'
  | 'ready';

export type KnowledgeReviewTaskActionKind =
  | 'open_commerce'
  | 'open_drafts'
  | 'open_documents'
  | 'upload_document';

export type KnowledgeReviewTask = {
  id: string;
  severity: KnowledgeReviewTaskSeverity;
  titleKey: TranslationKey;
  descriptionKey: TranslationKey;
  count?: number;
  action: {
    kind: KnowledgeReviewTaskActionKind;
    labelKey: TranslationKey;
    documentId?: string;
  };
};

type KnowledgeReviewInboxDocumentInput = {
  id: string;
  status: string;
  error?: string | null;
};

type KnowledgeReviewInboxCommercialTruthInput = {
  unresolved_conflict_count: number;
  conflict_count: number;
};

type BuildKnowledgeReviewInboxInput = {
  documents: KnowledgeReviewInboxDocumentInput[];
  hasProcessingDocuments: boolean;
  totalDrafts: number;
  firstDraftDocumentId: string | null;
  projectCommercialTruth?: KnowledgeReviewInboxCommercialTruthInput;
};

const FAILED_STATUSES = new Set(['failed', 'error']);

const isFailedDocument = (document: KnowledgeReviewInboxDocumentInput): boolean => {
  const normalizedStatus = document.status.trim().toLowerCase();
  return FAILED_STATUSES.has(normalizedStatus) || Boolean(document.error);
};

export function buildKnowledgeReviewInbox(input: BuildKnowledgeReviewInboxInput): KnowledgeReviewTask[] {
  const tasks: KnowledgeReviewTask[] = [];

  const unresolvedCommercialConflictCount = input.projectCommercialTruth?.unresolved_conflict_count ?? 0;
  if (unresolvedCommercialConflictCount > 0) {
    tasks.push({
      id: 'commercial_conflicts',
      severity: 'critical',
      titleKey: 'knowledge.reviewInbox.task.commercialConflicts.title',
      descriptionKey: 'knowledge.reviewInbox.task.commercialConflicts.description',
      count: unresolvedCommercialConflictCount,
      action: {
        kind: 'open_commerce',
        labelKey: 'knowledge.reviewInbox.action.openCommerce',
      },
    });
  }

  const failedDocumentCount = input.documents.filter(isFailedDocument).length;
  if (failedDocumentCount > 0) {
    tasks.push({
      id: 'failed_documents',
      severity: 'critical',
      titleKey: 'knowledge.reviewInbox.task.failedDocuments.title',
      descriptionKey: 'knowledge.reviewInbox.task.failedDocuments.description',
      count: failedDocumentCount,
      action: {
        kind: 'open_documents',
        labelKey: 'knowledge.reviewInbox.action.openDocuments',
      },
    });
  }

  if (input.hasProcessingDocuments) {
    tasks.push({
      id: 'processing_documents',
      severity: 'info',
      titleKey: 'knowledge.reviewInbox.task.processingDocuments.title',
      descriptionKey: 'knowledge.reviewInbox.task.processingDocuments.description',
      action: {
        kind: 'open_documents',
        labelKey: 'knowledge.reviewInbox.action.openDocuments',
      },
    });
  }

  if (input.totalDrafts > 0 && input.firstDraftDocumentId !== null) {
    tasks.push({
      id: 'answer_drafts',
      severity: 'warning',
      titleKey: 'knowledge.reviewInbox.task.answerDrafts.title',
      descriptionKey: 'knowledge.reviewInbox.task.answerDrafts.description',
      count: input.totalDrafts,
      action: {
        kind: 'open_drafts',
        labelKey: 'knowledge.reviewInbox.action.openDrafts',
        documentId: input.firstDraftDocumentId,
      },
    });
  }

  if (input.documents.length === 0) {
    tasks.push({
      id: 'empty_knowledge',
      severity: 'info',
      titleKey: 'knowledge.reviewInbox.task.emptyKnowledge.title',
      descriptionKey: 'knowledge.reviewInbox.task.emptyKnowledge.description',
      action: {
        kind: 'upload_document',
        labelKey: 'knowledge.reviewInbox.action.uploadDocument',
      },
    });
  }

  if (tasks.length === 0) {
    tasks.push({
      id: 'ready',
      severity: 'ready',
      titleKey: 'knowledge.reviewInbox.task.ready.title',
      descriptionKey: 'knowledge.reviewInbox.task.ready.description',
      action: {
        kind: 'open_documents',
        labelKey: 'knowledge.reviewInbox.action.openDocuments',
      },
    });
  }

  return tasks;
}
