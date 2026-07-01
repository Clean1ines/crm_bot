import type {
  WorkbenchDraftClaimArtifactLiveState,
  WorkbenchLlmAttemptLiveState,
  WorkbenchSectionQueueItemLiveState,
} from '@shared/api/modules/knowledge';

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
  liveState: WorkbenchDraftClaimArtifactLiveState;
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
  liveState: WorkbenchLlmAttemptLiveState;
};

export type ClaimBuilderSectionRowView = {
  queueItemId: string;
  sectionId: string;
  sectionIndex: number;
  sectionKey: string;
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
  liveState: WorkbenchSectionQueueItemLiveState;
};
