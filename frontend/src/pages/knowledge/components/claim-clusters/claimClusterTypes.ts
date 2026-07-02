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
