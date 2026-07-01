import type {
  ClaimBuilderAttemptView,
  ClaimBuilderDraftClaimArtifactInput,
  ClaimBuilderDraftClaimArtifactView,
  ClaimBuilderLlmAttemptInput,
  ClaimBuilderSectionQueueItemInput,
  ClaimBuilderSectionRowView,
  ClaimBuilderSourceUnitInput,
  ClaimBuilderSourceUnitsInput,
  ClaimBuilderWorkflowInput,
  ClaimBuilderWorkflowStateInput,
} from './claimBuilderTypes';

const claimBuilderAttemptStartedAtMs = (attempt: ClaimBuilderLlmAttemptInput): number => {
  const startedAtMs = Date.parse(attempt.started_at || '');
  return Number.isFinite(startedAtMs) ? startedAtMs : 0;
};

const sourceUnitTitle = (unit: ClaimBuilderSourceUnitInput | null): string =>
  unit?.title?.trim() || 'Без заголовка';

const sourceUnitText = (unit: ClaimBuilderSourceUnitInput | null): string | null => {
  const content = unit?.content?.trim();
  return content && content.length > 0 ? content : null;
};

const sourceUnitForSection = (
  item: ClaimBuilderSectionQueueItemInput,
  sourceUnitById: Map<string, ClaimBuilderSourceUnitInput>,
  sourceUnitByIndex: Map<number, ClaimBuilderSourceUnitInput>,
): ClaimBuilderSourceUnitInput | null =>
  sourceUnitById.get(item.section_id) ??
  sourceUnitByIndex.get(item.section_index) ??
  null;

const sectionItemsFromWorkflow = (
  workflow: ClaimBuilderWorkflowInput | null | undefined,
): ClaimBuilderSectionQueueItemInput[] =>
  (workflow?.section_lanes ?? [])
    .flatMap((lane) => lane.items)
    .sort((left, right) => left.section_index - right.section_index);

const draftClaimsFromSectionItems = (
  sectionItems: ClaimBuilderSectionQueueItemInput[],
): ClaimBuilderDraftClaimArtifactInput[] =>
  sectionItems.flatMap((item) => item.draft_claims ?? []);

const draftClaimArtifactView = (
  claim: ClaimBuilderDraftClaimArtifactInput,
): ClaimBuilderDraftClaimArtifactView => ({
  observationRef: claim.observation_ref,
  sourceUnitRef: claim.source_unit_ref,
  sectionId: claim.section_id ?? null,
  workItemId: claim.work_item_id,
  dispatchAttemptId: claim.dispatch_attempt_id,
  claimIndex: claim.claim_index,
  provider: claim.provider ?? null,
  modelRef: claim.model_ref ?? null,
  claim: claim.claim,
  granularity: claim.granularity,
  possibleQuestions: claim.possible_questions,
  exclusionScope: claim.exclusion_scope,
  evidenceBlock: claim.evidence_block,
  validationDecision: claim.validation_decision ?? null,
});

const artifactsByAttemptId = (
  claims: ClaimBuilderDraftClaimArtifactInput[],
): Map<string, ClaimBuilderDraftClaimArtifactView[]> => {
  const map = new Map<string, ClaimBuilderDraftClaimArtifactView[]>();

  claims.forEach((claim) => {
    const existing = map.get(claim.dispatch_attempt_id) ?? [];
    existing.push(draftClaimArtifactView(claim));
    map.set(claim.dispatch_attempt_id, existing);
  });

  map.forEach((artifacts) => {
    artifacts.sort((left, right) => left.claimIndex - right.claimIndex);
  });

  return map;
};

const attemptsForSection = (
  item: ClaimBuilderSectionQueueItemInput,
  attempts: ClaimBuilderLlmAttemptInput[],
  artifactsByAttempt: Map<string, ClaimBuilderDraftClaimArtifactView[]>,
): ClaimBuilderAttemptView[] =>
  attempts
    .filter(
      (attempt) =>
        attempt.section_id === item.section_id ||
        attempt.section_id === item.section_key,
    )
    .sort(
      (left, right) =>
        claimBuilderAttemptStartedAtMs(left) - claimBuilderAttemptStartedAtMs(right),
    )
    .map((attempt) => ({
      nodeRunId: attempt.node_run_id,
      sectionId: attempt.section_id ?? null,
      status: attempt.status,
      provider: attempt.model_provider ?? null,
      modelRef: attempt.model_name ?? null,
      promptTokens: attempt.prompt_tokens,
      completionTokens: attempt.completion_tokens,
      totalTokens: attempt.total_tokens,
      errorKind: attempt.error_kind ?? null,
      errorMessageUser: attempt.error_message_user ?? null,
      nextAttemptAt: attempt.next_attempt_at ?? null,
      userActionRequired: attempt.user_action_required,
      blockedReason: attempt.blocked_reason ?? null,
      startedAt: attempt.started_at ?? null,
      completedAt: attempt.completed_at ?? null,
      durationMs: attempt.duration_ms ?? null,
      artifacts: artifactsByAttempt.get(attempt.node_run_id) ?? [],
    }));

export const selectClaimBuilderSectionRows = (
  workflowLiveState: ClaimBuilderWorkflowStateInput,
  sourceUnitsResponse: ClaimBuilderSourceUnitsInput,
): ClaimBuilderSectionRowView[] => {
  const workflow = workflowLiveState?.workflow ?? null;
  const sourceUnits = sourceUnitsResponse?.source_units ?? [];
  const sourceUnitById = new Map(sourceUnits.map((unit) => [unit.id, unit]));
  const sourceUnitByIndex = new Map(sourceUnits.map((unit) => [unit.source_index, unit]));
  const sectionItems = sectionItemsFromWorkflow(workflow);
  const attempts = workflow?.llm_attempts ?? [];
  const artifactsByAttempt = artifactsByAttemptId(draftClaimsFromSectionItems(sectionItems));

  return sectionItems.map((item) => {
    const sourceUnit = sourceUnitForSection(item, sourceUnitById, sourceUnitByIndex);

    return {
      queueItemId: item.queue_item_id,
      sectionId: item.section_id,
      sectionIndex: item.section_index,
      sectionKey: item.section_key,
      status: item.status,
      attemptCount: item.attempt_count,
      title: sourceUnitTitle(sourceUnit),
      text: sourceUnitText(sourceUnit),
      errorKind: item.error_kind ?? null,
      retryPlan: item.retry_plan ?? null,
      nextAttemptAt: item.next_attempt_at ?? null,
      userActionRequired: item.user_action_required,
      blockedReason: item.blocked_reason ?? null,
      attempts: attemptsForSection(item, attempts, artifactsByAttempt),
    };
  });
};
