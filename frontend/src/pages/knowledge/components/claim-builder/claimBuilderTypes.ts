export type ClaimBuilderSourceUnitInput = {
  id: string;
  source_index: number;
  title: string;
  content: string;
};

export type ClaimBuilderSourceUnitsInput = {
  source_units: ClaimBuilderSourceUnitInput[];
} | null | undefined;

export type ClaimBuilderDraftClaimArtifactInput = {
  observation_ref: string;
  workflow_run_id?: string;
  source_document_ref?: string;
  source_unit_ref: string;
  section_id?: string;
  work_item_id: string;
  dispatch_attempt_id: string;
  claim_index: number;
  provider?: string;
  model_ref?: string;
  claim: string;
  granularity: string;
  possible_questions: string[];
  exclusion_scope: string;
  evidence_block: string;
  validation_decision?: string;
};

export type ClaimBuilderSectionQueueItemInput = {
  queue_item_id: string;
  section_id: string;
  section_index: number;
  section_key: string;
  status: string;
  attempt_count: number;
  next_attempt_at?: string | null;
  error_kind?: string | null;
  retry_plan?: string | null;
  user_action_required: boolean;
  blocked_reason?: string | null;
  draft_claims?: ClaimBuilderDraftClaimArtifactInput[];
};

export type ClaimBuilderSectionLaneInput = {
  items: ClaimBuilderSectionQueueItemInput[];
};

export type ClaimBuilderLlmAttemptInput = {
  node_run_id: string;
  section_id?: string | null;
  status: string;
  started_at?: string | null;
  completed_at?: string | null;
  duration_ms?: number | null;
  model_provider?: string | null;
  model_name?: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  error_kind?: string | null;
  error_message_user?: string | null;
  next_attempt_at?: string | null;
  user_action_required: boolean;
  blocked_reason?: string | null;
};

export type ClaimBuilderWorkflowInput = {
  section_lanes: ClaimBuilderSectionLaneInput[];
  llm_attempts: ClaimBuilderLlmAttemptInput[];
};

export type ClaimBuilderWorkflowStateInput = {
  workflow: ClaimBuilderWorkflowInput | null;
} | null | undefined;

export type ClaimBuilderDraftClaimArtifactView = {
  observationRef: string;
  sourceUnitRef: string;
  sectionId: string | null;
  workItemId: string;
  dispatchAttemptId: string;
  claimIndex: number;
  provider: string | null;
  modelRef: string | null;
  claim: string;
  granularity: string;
  possibleQuestions: string[];
  exclusionScope: string;
  evidenceBlock: string;
  validationDecision: string | null;
};

export type ClaimBuilderAttemptView = {
  nodeRunId: string;
  sectionId: string | null;
  status: string;
  provider: string | null;
  modelRef: string | null;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  errorKind: string | null;
  errorMessageUser: string | null;
  nextAttemptAt: string | null;
  userActionRequired: boolean;
  blockedReason: string | null;
  startedAt: string | null;
  completedAt: string | null;
  durationMs: number | null;
  artifacts: ClaimBuilderDraftClaimArtifactView[];
};

export type ClaimBuilderSectionRowView = {
  queueItemId: string;
  sectionId: string;
  sectionIndex: number;
  sectionKey: string;
  sourceUnit: ClaimBuilderSourceUnitInput | null;
  status: string;
  attemptCount: number;
  title: string;
  text: string | null;
  errorKind: string | null;
  retryPlan: string | null;
  nextAttemptAt: string | null;
  userActionRequired: boolean;
  blockedReason: string | null;
  attempts: ClaimBuilderAttemptView[];
};
