import { authedJsonRequest } from '../core/http';

export type KnowledgeEntryStatus = 'draft' | 'grounded' | 'enriched' | 'embedded' | 'published' | 'needs_review' | 'hidden' | 'archived' | 'rejected' | 'merged';
export type KnowledgeEntryVisibility = 'runtime' | 'owner_only' | 'internal' | 'hidden';

export interface KnowledgeCurationIssue {
  type: string;
  severity: string;
  message: string;
  details: Record<string, unknown>;
}

export interface KnowledgeCurationEntry {
  id: string;
  project_id: string;
  document_id: string;
  stable_key: string;
  entry_kind: string;
  title: string;
  answer: string;
  status: KnowledgeEntryStatus;
  visibility: KnowledgeEntryVisibility;
  version: number;
  enrichment: Record<string, unknown>;
  source_refs: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  has_retrieval_surface: boolean;
  has_embedding: boolean;
  runtime_eligible: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  issues: KnowledgeCurationIssue[];
}

export interface KnowledgeCurationSummary {
  document_id: string;
  document_name: string;
  document_status: string;
  processing_stage: string;
  total_entries: number;
  published_runtime_entries: number;
  needs_review_entries: number;
  hidden_entries: number;
  rejected_entries: number;
  merged_entries: number;
  duplicate_group_count: number;
  entries_without_source_refs: number;
  entries_missing_retrieval_surface: number;
  suspicious_entries: number;
  document_processing_active: boolean;
}

export interface KnowledgeCurationDuplicateGroup {
  group_id: string;
  reason: string;
  issue_type: string;
  entry_ids: string[];
  score: number;
  details: Record<string, unknown>;
}

export interface KnowledgeCurationPayload {
  ok: boolean;
  document: Record<string, unknown>;
  summary: KnowledgeCurationSummary;
  entries: KnowledgeCurationEntry[];
  duplicate_groups: KnowledgeCurationDuplicateGroup[];
}

export interface KnowledgeCurationStatusRequest {
  action: 'hide_entry' | 'reject_entry' | 'restore_entry' | 'publish_entry' | 'unpublish_entry';
  target_status?: KnowledgeEntryStatus | null;
  target_visibility?: KnowledgeEntryVisibility | null;
  expected_version?: number | null;
  reason?: string;
  rebuild_embedding?: boolean;
  rerun_eval?: boolean;
  idempotency_key?: string;
}

export interface KnowledgeEntryPatchRequest {
  title?: string | null;
  answer?: string | null;
  enrichment?: Record<string, unknown> | null;
  source_refs?: Array<Record<string, unknown>> | null;
  expected_version?: number | null;
  reason?: string;
  rebuild_embedding?: boolean;
  rerun_eval?: boolean;
  idempotency_key?: string;
}

export interface KnowledgeEntryMergeIncludeOptions {
  answers: boolean;
  questions: boolean;
  paraphrases: boolean;
  synonyms: boolean;
  typo_queries: boolean;
  colloquial_queries: boolean;
  tags: boolean;
  retrieval_guards: boolean;
  source_refs: boolean;
  metadata: boolean;
}

export interface KnowledgeEntryMergePreviewRequest {
  parent_entry_id: string;
  absorbed_entry_ids: string[];
  parent_expected_version?: number | null;
  absorbed_expected_versions: Record<string, number>;
  merge_instruction?: string;
  final_title?: string | null;
  final_answer?: string | null;
  include: KnowledgeEntryMergeIncludeOptions;
  exclude: {
    question_values: string[];
    synonym_values: string[];
    tag_values: string[];
    source_ref_keys: string[];
    metadata_keys: string[];
  };
  absorbed_status: 'merged';
  rebuild_embedding: boolean;
  rerun_eval: boolean;
  idempotency_key: string;
}

export interface KnowledgeEntryMergePreview {
  parent_entry_before: KnowledgeCurationEntry;
  absorbed_entries_before: KnowledgeCurationEntry[];
  proposed_entry_after: Record<string, unknown>;
  absorbed_entries_after: Array<Record<string, unknown>>;
  included_counts: Record<string, number>;
  excluded_counts: Record<string, number>;
  warnings: string[];
  blocking_errors: string[];
}

export interface KnowledgeEntryMergePreviewResponse {
  ok: boolean;
  preview: KnowledgeEntryMergePreview;
}

export type KnowledgeEntryMergeApplyRequest = KnowledgeEntryMergePreviewRequest;

export interface KnowledgeEntryMergeApplyResponse {
  ok: boolean;
  partial: boolean;
  action_id: string;
  parent_entry_id: string;
  absorbed_entry_ids: string[];
  parent_version: number;
  embedding_rebuilt: boolean;
  rerun_eval_enqueued: boolean;
  error: string;
  preview?: KnowledgeEntryMergePreview | null;
  rerun_eval_job_id?: string;
}

export interface KnowledgeEntryVersion {
  id: string;
  entry_id: string;
  project_id: string;
  document_id: string | null;
  action_id: string | null;
  from_version: number;
  to_version: number;
  previous_snapshot: Record<string, unknown>;
  new_snapshot: Record<string, unknown>;
  created_at?: string | null;
}

export interface KnowledgeCurationAction {
  id: string;
  action_type: string;
  status: string;
  actor_user_id: string;
  target_entry_id: string;
  target_entry_ids: string[];
  reason: string;
  payload: Record<string, unknown>;
  result_payload: Record<string, unknown>;
  error: string;
  source_kind: string;
  idempotency_key: string;
  created_at?: string | null;
  applied_at?: string | null;
  updated_at?: string | null;
}

const basePath = (projectId: string, documentId: string) => `/api/projects/${projectId}/knowledge/${documentId}/curation`;

export const knowledgeCurationApi = {
  getDocumentCuration: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeCurationPayload>(basePath(projectId, documentId), { method: 'GET' }),

  setEntryStatus: (projectId: string, documentId: string, entryId: string, payload: KnowledgeCurationStatusRequest) =>
    authedJsonRequest<{ ok: boolean; entry: KnowledgeCurationEntry }, KnowledgeCurationStatusRequest>(`${basePath(projectId, documentId)}/entries/${entryId}/status`, { method: 'POST', body: payload }),

  patchEntry: (projectId: string, documentId: string, entryId: string, payload: KnowledgeEntryPatchRequest) =>
    authedJsonRequest<{ ok: boolean; entry: KnowledgeCurationEntry }, KnowledgeEntryPatchRequest>(`${basePath(projectId, documentId)}/entries/${entryId}`, { method: 'PATCH', body: payload }),

  rebuildEntryEmbedding: (projectId: string, documentId: string, entryId: string) =>
    authedJsonRequest<{ ok: boolean; entry_id: string }>(`${basePath(projectId, documentId)}/entries/${entryId}/embedding/rebuild`, { method: 'POST' }),

  previewMerge: (projectId: string, documentId: string, payload: KnowledgeEntryMergePreviewRequest) =>
    authedJsonRequest<KnowledgeEntryMergePreviewResponse, KnowledgeEntryMergePreviewRequest>(`${basePath(projectId, documentId)}/merge/preview`, { method: 'POST', body: payload }),

  applyMerge: (projectId: string, documentId: string, payload: KnowledgeEntryMergeApplyRequest) =>
    authedJsonRequest<KnowledgeEntryMergeApplyResponse, KnowledgeEntryMergeApplyRequest>(`${basePath(projectId, documentId)}/merge/apply`, { method: 'POST', body: payload }),

  listActions: (projectId: string, documentId: string) =>
    authedJsonRequest<{ ok: boolean; actions: KnowledgeCurationAction[] }>(`${basePath(projectId, documentId)}/actions`, { method: 'GET' }),

  listEntryVersions: (projectId: string, documentId: string, entryId: string) =>
    authedJsonRequest<{ ok: boolean; versions: KnowledgeEntryVersion[] }>(`${basePath(projectId, documentId)}/entries/${entryId}/versions`, { method: 'GET' }),

  restoreEntryVersion: (projectId: string, documentId: string, entryId: string, versionId: string, reason: string) =>
    authedJsonRequest<{ ok: boolean; entry: KnowledgeCurationEntry }, { reason: string }>(`${basePath(projectId, documentId)}/entries/${entryId}/versions/${versionId}/restore`, { method: 'POST', body: { reason } }),
};
