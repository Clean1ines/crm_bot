import type {
  WorkbenchClaimClusterLiveState,
  WorkbenchClaimCompactionComparisonLiveState,
  WorkbenchCompactedClaimPreviewLiveState,
} from '@shared/api/modules/knowledge';

export type ClaimClustersDraftArtifact = {
  observationRef: string;
  claim: string;
};

export type ClaimClustersExtractedFact = {
  key: string;
  text: string;
};

export type FinalCompactedFact = WorkbenchCompactedClaimPreviewLiveState & {
  cluster_ref: string;
};

export type ClaimClusterCompactionAttemptView = {
  key: string;
  workItemId: string | null;
  batchRef: string | null;
  groupRef: string | null;
  attemptNumber: number;
  status: string;
  statusLabel: string;
  toneClassName: string;
  modelName: string | null;
  provider: string | null;
  tokenCount: number;
  durationMs: number | null;
  startedAt: string | null;
  completedAt: string | null;
  errorMessage: string | null;
};

export type ClaimClusterCompactionView = {
  ready: number;
  leased: number;
  done: number;
  retry: number;
  failed: number;
  needsDecision: number;
  previewCount: number;
  progressPercent: number;
  attention: number;
  isComplete: boolean;
  panelTone: string;
  userSummary: string;
  attempts: ClaimClusterCompactionAttemptView[];
  llmAttemptCount: number;
  succeededAttemptCount: number;
  runningAttemptCount: number;
  tokens: number;
};

export type ClaimClustersView = {
  hasClusters: boolean;
  clusters: WorkbenchClaimClusterLiveState[];
  hasComparisons: boolean;
  comparisons: WorkbenchClaimCompactionComparisonLiveState[];
  clusteredClaimCount: number;
  embeddedClaimCount: number;
  resolvedComparisonCount: number;
  compactedClusterCount: number;
  extractedFacts: ClaimClustersExtractedFact[];
  finalFacts: FinalCompactedFact[];
  compaction: ClaimClusterCompactionView;
};
