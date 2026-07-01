export type SourceIngestionStageInput = {
  id: string;
  status: string;
  current: number;
  total: number;
  started_at?: string | null;
  completed_at?: string | null;
} | null | undefined;

export type SourceIngestionLaneInput = {
  ready_count: number;
  leased_count: number;
  done_count: number;
  failed_count: number;
  waiting_count: number;
  items: unknown[];
};

export type SourceIngestionWorkflowInput = {
  stages: SourceIngestionStageInput[];
  section_lanes: SourceIngestionLaneInput[];
} | null | undefined;

export type SourceIngestionWorkflowStateInput = {
  workflow: SourceIngestionWorkflowInput;
} | null | undefined;

export type SourceIngestionProgressView = {
  visible: boolean;
  current: number;
  total: number;
  percent: number;
  readyCount: number;
  leasedCount: number;
  doneCount: number;
  failedCount: number;
  waitingCount: number;
  sectionCount: number;
  text: string;
};
