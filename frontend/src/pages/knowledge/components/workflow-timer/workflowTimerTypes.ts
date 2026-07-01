export type WorkflowTimerInput = {
  mode?: string | null;
  active_elapsed_seconds?: number | null;
  wall_elapsed_seconds?: number | null;
  current_active_started_at?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  is_live?: boolean | null;
} | null | undefined;
