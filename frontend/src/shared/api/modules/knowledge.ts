import { t } from '../../i18n';
import { API_BASE_URL } from '../core/config';
import { authedJsonRequest, authedMultipartRequest, createAuthHeaders } from '../core/http';

export type KnowledgePreprocessingMode = 'faq' | 'price_list';
export type KnowledgePreviewRetrievalMode = 'runtime_equivalent' | 'lexical_debug';

export type KnowledgePreprocessingModeOption = {
  value: KnowledgePreprocessingMode;
  label: string;
  description: string;
};

export const KNOWLEDGE_PREPROCESSING_MODE_OPTIONS: KnowledgePreprocessingModeOption[] = [
  {
    value: 'faq',
    label: t('knowledge.preprocessing.faq.label'),
    description: t('knowledge.preprocessing.faq.description'),
  },
  {
    value: 'price_list',
    label: t('knowledge.preprocessing.priceList.label'),
    description: t('knowledge.preprocessing.priceList.description'),
  },
];

export type KnowledgeSearchTrace = {
  matched_fields: string[];
  lexical_score: number;
  vector_score: number;
  exact_question_match: boolean;
  title_match: boolean;
  length_penalty: number;
  final_score: number;
  retrieval_surface_role: string;
  displayed_field: string;
  is_production_safe: boolean;
};

export type KnowledgePreviewResult = {
  id: string;
  content: string;
  answer: string;
  score: number;
  method: string;
  source: string | null;
  document_id: string | null;
  document_status: string | null;
  entry_kind?: string | null;
  title?: string | null;
  source_excerpt?: string | null;
  questions?: unknown;
  synonyms?: unknown;
  tags?: unknown;
  trace?: KnowledgeSearchTrace | null;
};

export type KnowledgePreviewResponse = {
  query: string;
  best_result: KnowledgePreviewResult | null;
  top_results: KnowledgePreviewResult[];
  is_empty: boolean;
  retrieval_mode: KnowledgePreviewRetrievalMode;
  method: string;
  trace: Record<string, unknown>;
};


export type KnowledgeProcessingStep = {
  id: string;
  label: string;
  status: string;
  current: number;
  total: number;
  message: string;
};

export type KnowledgeProcessingAction = {
  id: string;
  label: string;
  kind: string;
  enabled: boolean;
};

export type KnowledgeProcessingReport = {
  document_id: string;
  status: string;
  title: string;
  message: string;
  recoverable: boolean;
  steps: KnowledgeProcessingStep[];
  actions: KnowledgeProcessingAction[];
  metrics: Record<string, unknown>;
};

export type WorkbenchDocumentCardMessageSeverity =
  | 'info'
  | 'success'
  | 'warning'
  | 'error'
  | string;

export type WorkbenchDocumentCardActionTone =
  | 'primary'
  | 'secondary'
  | 'warning'
  | 'danger'
  | string;

export type WorkbenchDocumentCardUserMessage = {
  code: string;
  severity: WorkbenchDocumentCardMessageSeverity;
  i18n_key: string;
  default_message: string;
  debug_ref?: string | null;
};

export type WorkbenchDocumentCardErrorView = {
  reason_code: string;
  user_message: WorkbenchDocumentCardUserMessage;
  recoverable: boolean;
  retry_available: boolean;
  internal_error_ref?: string | null;
};

export type WorkbenchDocumentCardTimerView = {
  mode: 'running' | 'paused' | 'stopped' | 'completed' | 'published' | string;
  active_elapsed_seconds: number;
  wall_elapsed_seconds: number;
  current_active_started_at?: string | null;
  i18n_key: string;
  default_label: string;
};

export type WorkbenchDocumentCardUsageView = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  llm_call_count: number;
  i18n_key?: string;
};

export type WorkbenchDocumentCardSectionSummaryView = {
  total: number;
  processed: number;
  failed: number;
  pending: number;
};

export type WorkbenchDocumentCardRegistrySummaryView = {
  entry_count: number;
  final_snapshot_id?: string | null;
  retained: boolean;
};

export type WorkbenchDocumentCardSurfaceSummaryView = {
  draft_count: number;
  ready_count: number;
  published_count: number;
  rejected_count: number;
};

export type WorkbenchDocumentCardRuntimeSummaryView = {
  publication_id?: string | null;
  runtime_entry_count: number;
};

export type WorkbenchDocumentCardRecoveryView = {
  mode: 'none' | 'scheduled_auto_resume' | 'manual_only' | 'forbidden' | string;
  scheduled_at?: string | null;
  can_cancel_scheduled_resume: boolean;
  reason_code: string;
  i18n_key: string;
  default_message: string;
};

export type WorkbenchDocumentCardActionView = {
  action_id:
    | 'cancel_processing'
    | 'resume_processing'
    | 'cancel_scheduled_recovery'
    | 'delete_document'
    | 'open_workbench'
    | 'open_curation'
    | 'publish_ready'
    | 'open_published_surfaces'
    | 'reprocess_fresh'
    | string;
  visible: boolean;
  enabled: boolean;
  tone: WorkbenchDocumentCardActionTone;
  i18n_key: string;
  default_label: string;
  reason_code?: string | null;
  confirmation_i18n_key?: string | null;
  default_confirmation?: string | null;
};

export type WorkbenchDocumentCardView = {
  document_id: string;
  project_id: string;
  file_name: string;
  source_type: string;
  lifecycle_state: string;
  retention_state: string;
  transient_purged: boolean;
  resume_available: boolean;
  status_i18n_key: string;
  default_status_label: string;
  status_description_i18n_key: string;
  default_status_description: string;
  timer: WorkbenchDocumentCardTimerView;
  usage: WorkbenchDocumentCardUsageView;
  sections: WorkbenchDocumentCardSectionSummaryView;
  registry: WorkbenchDocumentCardRegistrySummaryView;
  surfaces: WorkbenchDocumentCardSurfaceSummaryView;
  runtime: WorkbenchDocumentCardRuntimeSummaryView;
  recovery: WorkbenchDocumentCardRecoveryView;
  actions: WorkbenchDocumentCardActionView[];
  messages: WorkbenchDocumentCardUserMessage[];
  error?: WorkbenchDocumentCardErrorView | null;
  metadata?: Record<string, unknown>;
};



export type WorkbenchWorkflowTimerLiveState = {
  mode: 'running' | 'paused' | 'stopped' | 'completed' | 'published' | string;
  active_elapsed_seconds: number;
  wall_elapsed_seconds: number;
  current_active_started_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  is_live: boolean;
};

export type WorkbenchWorkflowModelUsageLiveState = {
  model_provider?: string | null;
  model_name?: string | null;
  call_count: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  duration_ms_total: number;
};

export type WorkbenchWorkflowUsageLiveState = {
  total_prompt_tokens: number;
  total_completion_tokens: number;
  total_tokens: number;
  total_llm_calls: number;
  model_summaries: WorkbenchWorkflowModelUsageLiveState[];
};

export type WorkbenchWorkflowStageLiveState = {
  id: string;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused' | 'unknown' | string;
  current: number;
  total: number;
  message: string;
  started_at?: string | null;
  completed_at?: string | null;
};

export type WorkbenchWorkflowTimelineEntryLiveState = {
  timeline_entry_id: string;
  event_type: string;
  phase: string;
  severity: string;
  message: string;
  occurred_at: string;
  source_ref?: string | null;
  work_item_id?: string | null;
  attempt_id?: string | null;
};

export type WorkbenchRetryTimerLiveState = {
  retry_available_at?: string | null;
  seconds_until_retry?: number | null;
};

export type WorkbenchSectionQueueItemLiveState = {
  queue_item_id: string;
  section_id: string;
  section_index: number;
  section_key: string;
  status: string;
  attempt_count: number;
  lease_expires_at?: string | null;
  next_attempt_at?: string | null;
  claimed_by_worker_id?: string | null;
  error_kind?: string | null;
  retry_plan?: string | null;
  user_action_required: boolean;
  blocked_reason?: string | null;
  retry_timer: WorkbenchRetryTimerLiveState;
};

export type WorkbenchSectionLaneLiveState = {
  lane_index: number;
  lane_id: string;
  ready_count: number;
  leased_count: number;
  done_count: number;
  failed_count: number;
  waiting_count: number;
  total_attempt_count: number;
  max_attempt_count: number;
  items: WorkbenchSectionQueueItemLiveState[];
};

export type WorkbenchLlmAttemptLiveState = {
  node_run_id: string;
  section_id?: string | null;
  node_name: string;
  node_kind: string;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  model_provider?: string | null;
  model_name?: string | null;
  account_ref?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  remaining_minute_requests?: number | null;
  remaining_minute_tokens?: number | null;
  minute_reset_at?: string | null;
  remaining_daily_requests?: number | null;
  remaining_daily_tokens?: number | null;
  daily_reset_at?: string | null;
  error_kind?: string | null;
  error_message_user?: string | null;
  next_attempt_at?: string | null;
  retry_plan?: string | null;
  user_action_required: boolean;
  blocked_reason?: string | null;
};

export type WorkbenchCapacityWindowLiveState = {
  window_key: string;
  provider?: string | null;
  account_ref?: string | null;
  model_ref?: string | null;
  status: string;
  remaining_minute_requests?: number | null;
  remaining_minute_tokens?: number | null;
  minute_reset_at?: string | null;
  remaining_daily_requests?: number | null;
  remaining_daily_tokens?: number | null;
  daily_reset_at?: string | null;
  reset_at?: string | null;
  run_after?: string | null;
  observed_at?: string | null;
  last_outcome_class?: string | null;
  last_error_kind?: string | null;
  last_total_tokens?: number | null;
  linked_work_item_ids: string[];
  linked_dispatch_attempt_ids: string[];
};


export type WorkbenchClaimClusterClaimLiveState = {
  observation_ref: string;
  claim: string;
  possible_questions: string[];
  exclusion_scope: string[];
  granularity: string;
  source_document_ref: string;
  source_unit_ref: string;
  embedding_ref?: string | null;
  embedding_model_id?: string | null;
  embedding_dimensions?: number | null;
  embedding_status: string;
  node_ref?: string | null;
  node_kind?: string | null;
  node_active: boolean;
  node_status: string;
  member_rank: number;
  member_kind: string;
};

export type WorkbenchCompactedClaimPreviewLiveState = {
  node_ref: string;
  claim: string;
  claim_kind?: string | null;
  merge_decision?: string | null;
  source_claim_refs: string[];
  active: boolean;
};

export type WorkbenchClaimClusterLiveState = {
  group_ref: string;
  cluster_ref: string;
  status: string;
  member_count: number;
  candidate_edge_count: number;
  batch_count: number;
  node_count: number;
  active_node_count: number;
  active_compacted_node_count: number;
  comparison_count: number;
  pending_comparison_count: number;
  work_item_count: number;
  ready_work_item_count?: number;
  leased_work_item_count?: number;
  completed_work_item_count?: number;
  retryable_failed_work_item_count?: number;
  terminal_failed_work_item_count?: number;
  user_action_required_work_item_count?: number;
  members: WorkbenchClaimClusterClaimLiveState[];
  claims: WorkbenchClaimClusterClaimLiveState[];
  comparisons: WorkbenchClaimCompactionComparisonLiveState[];
  compacted_claims?: WorkbenchCompactedClaimPreviewLiveState[];
};

export type WorkbenchClaimCompactionComparisonLiveState = {
  comparison_ref: string;
  cluster_ref: string;
  left_node_ref: string;
  right_node_ref: string;
  status: string;
  result_node_ref?: string | null;
  round_index: number;
};

export type WorkbenchCurationLiveState = {
  available: boolean;
  reason_code: string;
  workflow_run_id?: string | null;
  workspace_ref?: string | null;
  workspace_status?: string | null;
  item_count: number;
  excluded_item_count: number;
};

export type WorkbenchWorkflowActionLiveState = {
  action_id:
    | 'pause_processing'
    | 'resume_processing'
    | 'cancel_processing'
    | 'open_curation'
    | string;
  visible: boolean;
  enabled: boolean;
  reason_code?: string | null;
};

export type WorkbenchWorkflowLiveState = {
  workflow_run_id?: string | null;
  source_document_ref?: string | null;
  workflow_status?: string | null;
  current_phase?: string | null;
  timer: WorkbenchWorkflowTimerLiveState;
  usage: WorkbenchWorkflowUsageLiveState;
  stages: WorkbenchWorkflowStageLiveState[];
  section_lanes: WorkbenchSectionLaneLiveState[];
  llm_attempts: WorkbenchLlmAttemptLiveState[];
  capacity_windows: WorkbenchCapacityWindowLiveState[];
  timeline: WorkbenchWorkflowTimelineEntryLiveState[];
  claim_clusters?: WorkbenchClaimClusterLiveState[];
  claim_compaction_comparisons?: WorkbenchClaimCompactionComparisonLiveState[];
  curation: WorkbenchCurationLiveState;
  actions: WorkbenchWorkflowActionLiveState[];
};

export type FrontendWorkflowEventEnvelope = {
  projection_event_id: string;
  source_event_id: string;
  source_sequence_number: number;
  projection_version: number;
  projection_type: string;
  event_type: string;
  operation_key: string | null;
  canonical_phase: string | null;
  workflow_run_id: string;
  project_id: string;
  document_id: string;
  payload: Record<string, unknown>;
  occurred_at: string;
  causation_command_id: string | null;
  correlation_id: string | null;
};

export type FrontendWorkflowEventsResponse = {
  workflow_run_id: string;
  after_source_sequence: number | null;
  after_cursor: string | null;
  next_cursor: string | null;
  events: FrontendWorkflowEventEnvelope[];
};

export type FrontendWorkflowEventsQuery = {
  after_cursor?: string | null;
  after_source_sequence?: number | null;
  limit?: number;
};

export type WorkbenchWorkflowLiveStateResponse = {
  document_id: string;
  project_id: string;
  file_name: string;
  document_status: string;
  current_processing_run_id?: string | null;
  workflow: WorkbenchWorkflowLiveState;
};

export type FrontendWorkflowEventStreamStop = () => void;

export type FrontendWorkflowEventStreamMessageHandler = (
  payload: FrontendWorkflowEventEnvelope,
) => void;

export type FrontendWorkflowEventStreamErrorHandler = (error: unknown) => void;

export type WorkflowLiveStateStreamStop = () => void;

export type WorkflowLiveStateStreamMessageHandler = (
  payload: WorkbenchWorkflowLiveStateResponse,
) => void;

export type WorkflowLiveStateStreamErrorHandler = (error: unknown) => void;

const parseSsePayloads = (buffer: string): { payloads: string[]; rest: string } => {
  const chunks = buffer.split("\n\n");
  const rest = chunks.pop() || "";
  const payloads = chunks
    .map((chunk) =>
      chunk
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice("data:".length).trimStart())
        .join("\n"),
    )
    .filter((payload) => payload.trim() !== "");

  return { payloads, rest };
};

const frontendWorkflowEventsQueryString = (
  query: FrontendWorkflowEventsQuery = {},
): string => {
  const params = new URLSearchParams();
  if (query.after_cursor && query.after_cursor.trim()) {
    params.set('after_cursor', query.after_cursor.trim());
  }
  if (typeof query.after_source_sequence === 'number') {
    params.set('after_source_sequence', String(query.after_source_sequence));
  }
  if (typeof query.limit === 'number') {
    params.set('limit', String(query.limit));
  }
  const queryString = params.toString();
  return queryString ? `?${queryString}` : '';
};

const streamFrontendWorkflowEvents = (
  projectId: string,
  documentId: string,
  workflowRunId: string,
  query: FrontendWorkflowEventsQuery | undefined,
  onMessage: FrontendWorkflowEventStreamMessageHandler,
  onError?: FrontendWorkflowEventStreamErrorHandler,
): FrontendWorkflowEventStreamStop => {
  const controller = new AbortController();
  const queryString = frontendWorkflowEventsQueryString(query);

  void (async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/projects/${projectId}/knowledge/source-documents/${encodeURIComponent(documentId)}/workflows/${encodeURIComponent(workflowRunId)}/frontend-events/stream${queryString}`,
        {
          method: 'GET',
          headers: createAuthHeaders(null),
          signal: controller.signal,
        },
      );

      if (!response.ok || !response.body) {
        throw new Error(`Frontend workflow event stream failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSsePayloads(buffer);
        buffer = parsed.rest;

        for (const payload of parsed.payloads) {
          onMessage(JSON.parse(payload) as FrontendWorkflowEventEnvelope);
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        onError?.(error);
      }
    }
  })();

  return () => controller.abort();
};

const streamWorkflowLiveState = (
  projectId: string,
  documentId: string,
  onMessage: WorkflowLiveStateStreamMessageHandler,
  onError?: WorkflowLiveStateStreamErrorHandler,
): WorkflowLiveStateStreamStop => {
  const controller = new AbortController();

  void (async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/projects/${projectId}/knowledge/${encodeURIComponent(documentId)}/workflow-live-state/events`,
        {
          method: "GET",
          headers: createAuthHeaders(null),
          signal: controller.signal,
        },
      );

      if (!response.ok || !response.body) {
        throw new Error(`Workflow live-state stream failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSsePayloads(buffer);
        buffer = parsed.rest;

        for (const payload of parsed.payloads) {
          onMessage(JSON.parse(payload) as WorkbenchWorkflowLiveStateResponse);
        }
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        onError?.(error);
      }
    }
  })();

  return () => controller.abort();
};



export type DraftClaimCurationEditablePayload = {
  key: string;
  claim: string;
  claim_kind: string;
  granularity: string;
  source_claim_refs: string[];
  triples: Record<string, unknown>[];
  merge_decision: string;
  possible_questions: string[];
  exclusion_scope: string;
  evidence_block: string;
};

export type DraftClaimCurationRawClaimProvenance = {
  raw_claim_ref: string;
  claim: string;
  granularity: string;
  possible_questions: string[];
  exclusion_scope: string;
  evidence_block: string;
  source_unit_ref?: string | null;
  source_unit_text?: string | null;
  heading_path?: string[] | null;
  created_at?: string | null;
};

export type DraftClaimCurationItemProvenance = {
  raw_claims?: DraftClaimCurationRawClaimProvenance[];
  source_units?: Record<string, unknown>[];
};

export type DraftClaimCurationItem = {
  item_ref: string;
  workspace_ref: string;
  workflow_run_id: string;
  group_ref: string;
  compacted_node_ref: string;
  source_claim_refs: string[];
  original_payload: DraftClaimCurationEditablePayload;
  editable_payload: DraftClaimCurationEditablePayload;
  excluded: boolean;
  exclusion_reason?: string | null;
  provenance?: DraftClaimCurationItemProvenance;
  audit?: Record<string, unknown>;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DraftClaimCurationPublicationResponse = {
  status: string;
  publication_id: string;
  workflow_run_id: string;
  project_id: string;
  source_document_ref: string;
  published_item_count: number;
  excluded_item_count: number;
  runtime_entry_count: number;
  embedding_count: number;
  deleted_draft_embedding_count: number;
  automatic_processing_elapsed_seconds?: number | null;
  published_at: string;
};


export type DraftClaimCurationWorkspaceResponse = {
  workspace: {
    workspace_ref: string;
    workflow_run_id: string;
    project_id: string;
    source_document_ref: string;
    status: string;
    created_at?: string | null;
    updated_at?: string | null;
  };
  progress?: Record<string, unknown> | null;
  items: DraftClaimCurationItem[];
};

export type DraftClaimCurationItemUpdatePayload = Partial<
  Pick<
    DraftClaimCurationEditablePayload,
    | 'key'
    | 'claim'
    | 'claim_kind'
    | 'granularity'
    | 'triples'
    | 'possible_questions'
    | 'exclusion_scope'
    | 'evidence_block'
  >
>;

export type DraftClaimObservationProvenance = {
  workflow_run_id?: string | null;
  stage_run_id?: string | null;
  work_item_id?: string | null;
  work_item_attempt_id?: string | null;
  llm_task_id?: string | null;
  llm_attempt_id?: string | null;
  prompt_id?: string | null;
  prompt_version?: string | null;
  claim_index?: number | null;
};

export type DraftClaimObservationReadItem = {
  observation_ref: string;
  source_unit_ref: string;
  claim: string;
  granularity: string;
  possible_questions: string[];
  exclusion_scope: string;
  evidence_block: string;
  provenance: DraftClaimObservationProvenance;
  created_at: string;
};

export type WorkflowScopedDraftClaimsResponse = {
  workflow_run_id: string;
  source_unit_ref: string | null;
  work_item_id: string | null;
  dispatch_attempt_id: string | null;
  count: number;
  limit: number;
  offset: number;
  items: DraftClaimObservationReadItem[];
};

export type WorkflowScopedDraftClaimsQuery = {
  source_unit_ref?: string;
  work_item_id?: string;
  dispatch_attempt_id?: string;
  limit?: number;
  offset?: number;
};


export type KnowledgeAnswerDraft = {
  id: string;
  title: string;
  answer: string;
  status: string;
  batch_id: string;
  batch_index: number | null;
  fragment_index: number | null;
  canonical_question: string;
  question_variants: string[];
  synonyms: string[];
  tags: string[];
  source_unit_indexes: number[];
  source_refs: Array<{
    quote: string;
    source_index?: number;
    source_unit_ref?: string;
    start_offset?: number;
    end_offset?: number;
    confidence?: number;
  }>;
  rejection_reason: string;
};

export type KnowledgeAnswerDraftsResponse = {
  document_id: string;
  drafts: KnowledgeAnswerDraft[];
  total_count: number;
};

export type KnowledgeSourceUnit = {
  id: string;
  source_index: number;
  title: string;
  content: string;
  page?: number;
  start_offset?: number;
  end_offset?: number;
  metadata: Record<string, unknown>;
  draft_count: number;
  draft_titles: string[];
  draft_ids: string[];
};

export type KnowledgeSourceUnitsResponse = {
  document_id: string;
  source_units: KnowledgeSourceUnit[];
  total_count: number;
};


export type KnowledgePriceValueKind =
  | 'exact'
  | 'starting_from'
  | 'range'
  | 'on_request'
  | string;

export type KnowledgePriceFactStatus =
  | 'draft'
  | 'needs_review'
  | 'published'
  | 'rejected'
  | 'superseded'
  | string;

export type KnowledgePriceMoney = {
  amount: string;
  currency: string;
};

export type KnowledgePriceRange = {
  min_amount: KnowledgePriceMoney;
  max_amount: KnowledgePriceMoney;
};

export type KnowledgePriceCondition = {
  text: string;
};

export type KnowledgePriceSourceRef = {
  price_document_id: string;
  source_unit_id: string;
  source_row_id?: string;
  quote: string;
};

export type KnowledgePriceFact = {
  id: string;
  project_id: string;
  price_document_id: string;
  item_name: string;
  value_kind: KnowledgePriceValueKind;
  status: KnowledgePriceFactStatus;
  unit: string;
  amount?: KnowledgePriceMoney;
  price_range?: KnowledgePriceRange;
  price_text: string;
  variant: Record<string, string>;
  aliases: string[];
  conditions: KnowledgePriceCondition[];
  source_refs: KnowledgePriceSourceRef[];
  confidence: string;
};

export type KnowledgePriceFactsResponse = {
  knowledge_document_id: string;
  price_document_id: string | null;
  facts: KnowledgePriceFact[];
  items: KnowledgePriceFact[];
  is_empty: boolean;
};


export type KnowledgePriceFactsMutationResponse = {
  knowledge_document_id: string;
  price_document_id: string;
  affected_count: number;
  facts: KnowledgePriceFact[];
  items: KnowledgePriceFact[];
};

export type KnowledgeCommercialTruthReviewPolicy =
  | 'manual_review'
  | 'higher_authority_wins'
  | 'newer_source_wins';

export type KnowledgeCommercialTruthFactReview = {
  fact_id: string;
  price_document_id: string;
  item_name: string;
  value_kind: string;
  status: string;
  unit: string;
  value_text: string;
  source_quote: string;
  source_id: string;
  source_title: string;
  source_observed_at: string;
  source_kind: string;
  source_authority: string;
  is_runtime_eligible: boolean;
};

export type KnowledgeCommercialTruthConflictReview = {
  identity_key: string;
  reason: string;
  resolution_status: string;
  resolution_reason: string;
  selected_fact_id: string | null;
  options: KnowledgeCommercialTruthFactReview[];
};

export type KnowledgeCommercialTruthReviewResponse = {
  policy: string;
  fact_count: number;
  conflict_count: number;
  resolved_conflict_count: number;
  unresolved_conflict_count: number;
  surface_fact_ids: string[];
  surface_facts: KnowledgeCommercialTruthFactReview[];
  facts: KnowledgeCommercialTruthFactReview[];
  conflicts: KnowledgeCommercialTruthConflictReview[];
};

export type KnowledgePriceFactsActionRequest = {
  fact_ids: string[];
  reason?: string;
};

export type KnowledgeImportQualityStatus = 'good' | 'needs_review' | 'unsafe' | string;

export type KnowledgeImportIssueSeverity = 'info' | 'warning' | 'error' | string;

export type KnowledgeImportIssue = {
  code: string;
  severity: KnowledgeImportIssueSeverity;
  message: string;
};

export type KnowledgeImportQualityReport = {
  document_id: string;
  status: KnowledgeImportQualityStatus;
  safe_to_compile: boolean;
  source_format: string;
  extracted_text_chars: number;
  source_units_count: number;
  empty_units_count: number;
  short_units_count: number;
  table_like_units_count: number;
  duplicated_headings_count: number;
  source_refs_ready: boolean;
  warnings: KnowledgeImportIssue[];
  recommended_action: string;
};

export type KnowledgeUsageBreakdown = {
  provider: string;
  model: string;
  usage_type: string;
  source: string;
  tokens_input: number;
  tokens_output: number;
  tokens_total: number;
  estimated_cost_usd: number;
  events_count: number;
};

export type KnowledgeUsageDaily = {
  day: string;
  tokens_total: number;
  estimated_cost_usd: number;
};

export type KnowledgeUsageResponse = {
  counter_enabled: boolean;
  monthly_budget_tokens: number;
  remaining_tokens: number;
  tokens_month_total: number;
  tokens_today_total: number;
  estimated_cost_month_usd: number;
  breakdown: KnowledgeUsageBreakdown[];
  daily: KnowledgeUsageDaily[];
};

export type KnowledgeDocumentDeleteResponse = {
  status: string;
  document_id: string;
};


export interface WorkbenchEvidenceTraceDocument {
  project_id: string;
  document_id: string;
  file_name: string;
  source_type?: string;
  file_size_bytes?: number;
  status?: string;
  current_processing_run_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  deleted_at?: string | null;
}

export interface WorkbenchEvidenceTraceFinding {
  claim_observation_id: string;
  section_id: string;
  action: string;
  status: string;
  target_fact_id?: string | null;
  claim_local_ref?: string | null;
  title?: string | null;
  claim?: string | null;
  claim_kind?: string;
  answer?: string | null;
  short_answer?: string | null;
  claim_delta?: string | null;
  variants: unknown[];
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_unit_indexes: unknown[];
  confidence?: number | null;
  reason?: string | null;
  granularity?: string | null;
  scope?: string | null;
  exclusion_scope?: string | null;
  triples?: unknown[];
  local_relations?: unknown[];
  node_run_id?: string | null;
  artifact_id?: string | null;
  created_at?: string | null;
}

export interface WorkbenchEvidenceTraceCanonicalFact {
  fact_id: string;
  fact_key: string;
  claim: string;
  question_variants: unknown[];
  claim_kind: string;
  answer: string;
  short_answer: string;
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_section_ids: unknown[];
  source_unit_indexes: unknown[];
  status: string;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceSurface {
  surface_id: string;
  fact_id?: string | null;
  title: string;
  claim: string;
  question_variants: unknown[];
  answer: string;
  short_answer: string;
  evidence_quotes: unknown[];
  source_refs: unknown[];
  source_section_ids: unknown[];
  claim_kind: string;
  status: string;
  curation_state: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceSourceUnit {
  unit_id: string;
  source_unit_id: string;
  section_id: string;
  section_key: string;
  section_index: number;
  title: string;
  status: string;
  source_refs: unknown[];
  source_unit_indexes: unknown[];
  metadata: Record<string, unknown>;
  text_excerpt: string;
  raw_text_excerpt: string;
  findings: WorkbenchEvidenceTraceFinding[];
  canonical_facts: WorkbenchEvidenceTraceCanonicalFact[];
  surfaces: WorkbenchEvidenceTraceSurface[];
  created_at?: string | null;
  updated_at?: string | null;
}

export interface WorkbenchEvidenceTraceResponse {
  document: WorkbenchEvidenceTraceDocument;
  source_units: WorkbenchEvidenceTraceSourceUnit[];
  items: WorkbenchEvidenceTraceSourceUnit[];
  findings: WorkbenchEvidenceTraceFinding[];
  canonical_facts: WorkbenchEvidenceTraceCanonicalFact[];
  surfaces: WorkbenchEvidenceTraceSurface[];
  coverage: Record<string, number>;
  gaps: Record<string, unknown>;
}

export type SurfaceEditRequest = {
  title?: string;
  answer?: string;
  short_answer?: string;
  question_variants?: string[];
  retrieval_scope?: string;
  exclusion_scope?: string;
};

export type SurfaceRejectRequest = {
  reason?: string;
};

export type SurfaceMergeFactsRequest = {
  source_fact_ids: string[];
  reason?: string;
};

export type SurfaceDeleteFactRequest = {
  reason?: string;
};

export type SurfacePublishSelectedRequest = {
  surface_ids: string[];
};

export type SurfaceCurationMutationResponse = {
  project_id: string;
  document_id: string;
  action: string;
  affected_count: number;
  item?: Record<string, unknown> | null;
  items?: Array<Record<string, unknown>>;
};


export type DraftClaimClusterBatchSummary = {
  batch_ref: string;
  group_ref: string;
  workflow_run_id: string;
  prompt_variant: string;
  model_id: string;
  estimated_input_tokens: number;
  batch_status: string;
  member_count: number;
  derived_work_item_id: string;
  created_at: string;
};

export type DraftClaimClusterGroupSummary = {
  group_ref: string;
  workflow_run_id: string;
  source_document_ref: string;
  embedding_model_id: string;
  group_algorithm: string;
  group_threshold: number;
  member_count: number;
  estimated_input_tokens: number;
  requires_split: boolean;
  created_at: string;
  batches: DraftClaimClusterBatchSummary[];
};

export type DraftClaimCompactionNodeSummary = {
  node_ref: string;
  workflow_run_id: string;
  group_ref: string;
  node_kind: string;
  active: boolean;
  source_claim_refs: string[];
  supersedes_node_refs: string[];
  source_claim_count?: number;
  supersedes_node_count?: number;
  estimated_input_tokens: number;
  compacted_key: string | null;
  compacted_claim: string | null;
  compacted_claim_kind: string | null;
  compacted_granularity: string | null;
  compacted_merge_decision: string | null;
  created_at: string;
  updated_at: string;
};


export type DraftClaimCompactionFrontierNodeSummary = DraftClaimCompactionNodeSummary & {
  frontier_state: string;
  source_claim_count: number;
  supersedes_node_count: number;
};

export type DraftClaimCompactionFrontierSummary = {
  workflow_run_id: string;
  group_ref: string | null;
  group_count: number;
  active_raw_count: number;
  active_compacted_count: number;
  inactive_node_count: number;
  superseded_node_count: number;
  total_node_count: number;
  group_done_count: number;
  all_groups_compacted: boolean;
};

export type DraftClaimCompactionSeparationSummary = {
  edge_count: number;
  origin_count: number;
  affected_active_node_count: number;
  sample_origin_pairs: string[][];
};

export type DraftClaimCompactionPendingWorkSummary = {
  pending_work_item_count: number;
  leased_or_running_count: number;
  waiting_for_capacity_count: number;
  next_work_scheduled_count: number;
};

export type DraftClaimCompactionPendingReductionWorkSummary = {
  workflow_run_id: string;
  group_ref: string;
  batch_ref: string | null;
  work_item_id: string;
  input_node_refs: string[];
  input_claim_refs: string[];
  work_item_status: string;
  dispatch_attempt_id: string | null;
  capacity_window_key: string | null;
  capacity_waiting: boolean;
  provider: string | null;
  account_ref: string | null;
  model_id: string | null;
  waiting_reason: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type WorkflowDraftClaimCompactionFrontierQuery = {
  group_ref?: string;
  include_inactive?: boolean;
  limit?: number;
  offset?: number;
};

export type WorkflowDraftClaimCompactionFrontierResponse = {
  workflow_run_id: string;
  group_ref: string | null;
  include_inactive: boolean;
  count: number;
  limit: number;
  offset: number;
  summary: DraftClaimCompactionFrontierSummary;
  separation_summary: DraftClaimCompactionSeparationSummary;
  pending_work_summary: DraftClaimCompactionPendingWorkSummary;
  pending_work_items: DraftClaimCompactionPendingReductionWorkSummary[];
  rows: DraftClaimCompactionFrontierNodeSummary[];
};

export type WorkflowDraftClaimCompactionNodesQuery = {
  group_ref?: string;
  node_ref?: string;
  active_only?: boolean;
  limit?: number;
  offset?: number;
};

export type WorkflowDraftClaimCompactionNodesResponse = {
  workflow_run_id: string;
  group_ref: string | null;
  node_ref: string | null;
  active_only: boolean;
  count: number;
  limit: number;
  offset: number;
  items: DraftClaimCompactionNodeSummary[];
};

export type WorkflowDraftClaimClustersQuery = {
  include_batches?: boolean;
  limit?: number;
  offset?: number;
};

export type WorkflowDraftClaimClustersResponse = {
  workflow_run_id: string;
  count: number;
  limit: number;
  offset: number;
  include_batches: boolean;
  groups: DraftClaimClusterGroupSummary[];
};

export type DraftClaimClusterGroupMemberSummary = {
  group_ref: string;
  observation_ref: string;
  embedding_ref: string;
  source_unit_ref: string;
  member_rank: number;
  member_kind: string;
  created_at: string;
};

export type DraftClaimClusterGroupMembersQuery = {
  limit?: number;
  offset?: number;
};

export type DraftClaimClusterGroupMembersResponse = {
  workflow_run_id: string;
  group_ref: string;
  count: number;
  limit: number;
  offset: number;
  items: DraftClaimClusterGroupMemberSummary[];
};

export const knowledgeApi = {
  list: (projectId: string) =>
    authedJsonRequest<{ documents?: Array<Record<string, unknown>>; items?: Array<Record<string, unknown>> }>(`/api/projects/${projectId}/knowledge`, {
      method: 'GET',
    }),

  clear: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge`, {
      method: 'DELETE',
    }),

  deleteDocument: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeDocumentDeleteResponse>(
      `/api/projects/${projectId}/knowledge/source-documents/${encodeURIComponent(documentId)}`,
      {
        method: 'DELETE',
      },
    ),

  cancel: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/source-documents/${encodeURIComponent(documentId)}/stop`, {
      method: 'POST',
    }),

  resumeProcessing: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/source-documents/${encodeURIComponent(documentId)}/restore`, {
      method: 'POST',
    }),

  confirmDegradedFallback: (projectId: string, workflowRunId: string) =>
    authedJsonRequest<{
      workflow_run_id: string;
      status: string;
      degraded_model_ref: string;
      appended_command_id: string;
    }>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/confirm-degraded-fallback`,
      {
        method: 'POST',
      },
    ),

  publishReady: (projectId: string, documentId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/knowledge/${documentId}/publish-ready`, {
      method: 'POST',
    }),

  openCurationWorkspace: (projectId: string, workflowRunId: string) =>
    authedJsonRequest<DraftClaimCurationWorkspaceResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace/open`,
      {
        method: 'POST',
      },
    ),

  publishCurationWorkspace: (projectId: string, workflowRunId: string) =>
    authedJsonRequest<DraftClaimCurationPublicationResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace/publish`,
      {
        method: 'POST',
      },
    ),

  readCurationWorkspace: (projectId: string, workflowRunId: string) =>
    authedJsonRequest<DraftClaimCurationWorkspaceResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace`,
      {
        method: 'GET',
      },
    ),

  getDraftClaimsByWorkflowScope: (
    projectId: string,
    workflowRunId: string,
    query: WorkflowScopedDraftClaimsQuery,
  ) => {
    const params = new URLSearchParams();
    if (query.source_unit_ref?.trim()) {
      params.set('source_unit_ref', query.source_unit_ref.trim());
    }
    if (query.work_item_id?.trim()) {
      params.set('work_item_id', query.work_item_id.trim());
    }
    if (query.dispatch_attempt_id?.trim()) {
      params.set('dispatch_attempt_id', query.dispatch_attempt_id.trim());
    }
    if (typeof query.limit === 'number') {
      params.set('limit', String(query.limit));
    }
    if (typeof query.offset === 'number') {
      params.set('offset', String(query.offset));
    }
    const queryString = params.toString();
    return authedJsonRequest<WorkflowScopedDraftClaimsResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/draft-claims${
        queryString ? `?${queryString}` : ''
      }`,
      {
        method: 'GET',
      },
    );
  },


  getDraftClaimCompactionFrontierByWorkflow: (
    projectId: string,
    workflowRunId: string,
    query: WorkflowDraftClaimCompactionFrontierQuery = {},
  ) => {
    const params = new URLSearchParams();
    if (typeof query.group_ref === 'string' && query.group_ref.length > 0) {
      params.set('group_ref', query.group_ref);
    }
    if (typeof query.include_inactive === 'boolean') {
      params.set('include_inactive', String(query.include_inactive));
    }
    if (typeof query.limit === 'number') {
      params.set('limit', String(query.limit));
    }
    if (typeof query.offset === 'number') {
      params.set('offset', String(query.offset));
    }
    const queryString = params.toString();
    return authedJsonRequest<WorkflowDraftClaimCompactionFrontierResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/draft-claim-compaction-frontier${
        queryString ? `?${queryString}` : ''
      }`,
      {
        method: 'GET',
      },
    );
  },

  getDraftClaimCompactionPendingWorkByWorkflow: (
    projectId: string,
    workflowRunId: string,
    query: Pick<WorkflowDraftClaimCompactionFrontierQuery, 'group_ref' | 'limit' | 'offset'> = {},
  ) =>
    knowledgeApi.getDraftClaimCompactionFrontierByWorkflow(projectId, workflowRunId, {
      ...query,
      include_inactive: true,
    }),

  getDraftClaimCompactionNodesByWorkflow: (
    projectId: string,
    workflowRunId: string,
    query: WorkflowDraftClaimCompactionNodesQuery = {},
  ) => {
    const params = new URLSearchParams();
    if (typeof query.group_ref === 'string' && query.group_ref.length > 0) {
      params.set('group_ref', query.group_ref);
    }
    if (typeof query.node_ref === 'string' && query.node_ref.length > 0) {
      params.set('node_ref', query.node_ref);
    }
    if (typeof query.active_only === 'boolean') {
      params.set('active_only', String(query.active_only));
    }
    if (typeof query.limit === 'number') {
      params.set('limit', String(query.limit));
    }
    if (typeof query.offset === 'number') {
      params.set('offset', String(query.offset));
    }
    const queryString = params.toString();
    return authedJsonRequest<WorkflowDraftClaimCompactionNodesResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/draft-claim-compaction-nodes${
        queryString ? `?${queryString}` : ''
      }`,
      {
        method: 'GET',
      },
    );
  },

  getDraftClaimClustersByWorkflow: (
    projectId: string,
    workflowRunId: string,
    query: WorkflowDraftClaimClustersQuery = {},
  ) => {
    const params = new URLSearchParams();
    if (typeof query.include_batches === 'boolean') {
      params.set('include_batches', String(query.include_batches));
    }
    if (typeof query.limit === 'number') {
      params.set('limit', String(query.limit));
    }
    if (typeof query.offset === 'number') {
      params.set('offset', String(query.offset));
    }
    const queryString = params.toString();
    return authedJsonRequest<WorkflowDraftClaimClustersResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/draft-claim-clusters${
        queryString ? `?${queryString}` : ''
      }`,
      {
        method: 'GET',
      },
    );
  },

  getDraftClaimClusterMembersByWorkflow: (
    projectId: string,
    workflowRunId: string,
    groupRef: string,
    query: DraftClaimClusterGroupMembersQuery = {},
  ) => {
    const params = new URLSearchParams();
    if (typeof query.limit === 'number') {
      params.set('limit', String(query.limit));
    }
    if (typeof query.offset === 'number') {
      params.set('offset', String(query.offset));
    }
    const queryString = params.toString();
    return authedJsonRequest<DraftClaimClusterGroupMembersResponse>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/draft-claim-clusters/${encodeURIComponent(groupRef)}/members${
        queryString ? `?${queryString}` : ''
      }`,
      {
        method: 'GET',
      },
    );
  },

  updateCurationItem: (
    projectId: string,
    workflowRunId: string,
    itemRef: string,
    payload: DraftClaimCurationItemUpdatePayload,
  ) =>
    authedJsonRequest<DraftClaimCurationWorkspaceResponse | { item: DraftClaimCurationItem }>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace/items/${encodeURIComponent(itemRef)}`,
      {
        method: 'PATCH',
        body: payload,
      },
    ),

  excludeCurationItem: (
    projectId: string,
    workflowRunId: string,
    itemRef: string,
    reason?: string,
  ) =>
    authedJsonRequest<DraftClaimCurationWorkspaceResponse | { item: DraftClaimCurationItem }>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace/items/${encodeURIComponent(itemRef)}/exclude`,
      {
        method: 'POST',
        body: reason?.trim() ? { exclusion_reason: reason.trim() } : {},
      },
    ),

  includeCurationItem: (projectId: string, workflowRunId: string, itemRef: string) =>
    authedJsonRequest<DraftClaimCurationWorkspaceResponse | { item: DraftClaimCurationItem }>(
      `/api/projects/${projectId}/knowledge/workflows/${encodeURIComponent(workflowRunId)}/curation-workspace/items/${encodeURIComponent(itemRef)}/include`,
      {
        method: 'POST',
      },
    ),

  getFrontendWorkflowEvents: (
    projectId: string,
    documentId: string,
    workflowRunId: string,
    query: FrontendWorkflowEventsQuery = {},
  ) =>
    authedJsonRequest<FrontendWorkflowEventsResponse>(
      `/api/projects/${projectId}/knowledge/source-documents/${encodeURIComponent(documentId)}/workflows/${encodeURIComponent(workflowRunId)}/frontend-events${frontendWorkflowEventsQueryString(query)}`,
      {
        method: 'GET',
      },
    ),

  streamFrontendWorkflowEvents,

  workflowLiveState: (projectId: string, documentId: string) =>
    authedJsonRequest<WorkbenchWorkflowLiveStateResponse>(
      `/api/projects/${projectId}/knowledge/${encodeURIComponent(documentId)}/workflow-live-state`,
      {
        method: 'GET',
      },
    ),

  streamWorkflowLiveState,

  progress: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeProcessingReport>(
      `/api/projects/${projectId}/knowledge/${documentId}/progress`,
      {
        method: 'GET',
      },
    ),

  fragments: (projectId: string, documentId: string, limit = 5) =>
    authedJsonRequest<KnowledgeAnswerDraftsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/fragments?limit=${limit}`,
      {
        method: 'GET',
      },
    ),

  sourceUnits: (projectId: string, documentId: string, limit = 1000) =>
    authedJsonRequest<KnowledgeSourceUnitsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/source-units?limit=${limit}`,
      {
        method: 'GET',
      },
    ),

  priceFacts: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgePriceFactsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts`,
      {
        method: 'GET',
      },
    ),

  projectCommercialTruthReview: (
    projectId: string,
    policy: KnowledgeCommercialTruthReviewPolicy = 'manual_review',
  ) =>
    authedJsonRequest<KnowledgeCommercialTruthReviewResponse>(
      `/api/projects/${projectId}/knowledge/commercial-truth-review?policy=${policy}`,
      {
        method: 'GET',
      },
    ),

  commercialTruthReview: (
    projectId: string,
    documentId: string,
    policy: KnowledgeCommercialTruthReviewPolicy = 'manual_review',
  ) =>
    authedJsonRequest<KnowledgeCommercialTruthReviewResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/commercial-truth-review?policy=${policy}`,
      {
        method: 'GET',
      },
    ),

  publishPriceFacts: (
    projectId: string,
    documentId: string,
    payload: KnowledgePriceFactsActionRequest,
  ) =>
    authedJsonRequest<KnowledgePriceFactsMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts/publish`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  rejectPriceFacts: (
    projectId: string,
    documentId: string,
    payload: KnowledgePriceFactsActionRequest,
  ) =>
    authedJsonRequest<KnowledgePriceFactsMutationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/price-facts/reject`,
      {
        method: 'POST',
        body: JSON.stringify(payload),
      },
    ),

  importQuality: (projectId: string, documentId: string) =>
    authedJsonRequest<KnowledgeImportQualityReport>(
      `/api/projects/${projectId}/knowledge/${documentId}/import-quality`,
      {
        method: 'GET',
      },
    ),

  preview: (
    projectId: string,
    question: string,
    limit = 5,
    retrievalMode: KnowledgePreviewRetrievalMode = 'runtime_equivalent',
  ) =>
    authedJsonRequest<
      KnowledgePreviewResponse,
      { question: string; limit: number; retrieval_mode: KnowledgePreviewRetrievalMode }
    >(
      `/api/projects/${projectId}/knowledge/preview`,
      {
        method: 'POST',
        body: { question, limit, retrieval_mode: retrievalMode },
      },
    ),

  usage: (projectId: string) =>
    authedJsonRequest<KnowledgeUsageResponse>(`/api/projects/${projectId}/knowledge/usage`, {
      method: 'GET',
    }),

  upload: (
    projectId: string,
    file: File,
    preprocessingMode: KnowledgePreprocessingMode = 'faq',
  ) => {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('preprocessing_mode', preprocessingMode);

    return authedMultipartRequest(`/api/projects/${projectId}/knowledge`, formData);
  },
};
