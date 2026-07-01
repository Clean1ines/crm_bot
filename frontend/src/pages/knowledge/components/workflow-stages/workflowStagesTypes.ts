export type WorkflowStageInput = {
  id: string;
  label?: string;
  status: string;
  current: number;
  total: number;
  message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type WorkflowStageCountContext = {
  hasClaimClusters: boolean;
  embeddedClaimCount: number;
  clusteredClaimCount: number;
  claimClusterCount: number;
  hasCompactionComparisons: boolean;
  compactedClusterCount: number;
};

export type WorkflowStageRowView = {
  id: string;
  title: string;
  status: string;
  statusLabel: string;
  toneClassName: string;
  pillClassName: string;
  current: number;
  total: number;
  showCounts: boolean;
  message: string | null;
};
