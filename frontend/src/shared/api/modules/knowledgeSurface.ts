import { authedJsonRequest } from '../core/http';

export type SurfaceCompilationRun = {
  id: string;
  project_id: string;
  document_id: string;
  mode?: string;
  status: string;
  compiler_kind: string;
  model: string;
  prompt_version: string;
  started_at: string | null;
  completed_at: string | null;
  error_type: string | null;
  error_message: string | null;
  metrics: Record<string, unknown>;
};

export type SurfaceCompilationStage = {
  id: string;
  run_id: string;
  document_id?: string;
  stage_kind: string;
  status: string;
  model: string;
  prompt_version: string;
  input_summary: string;
  output_summary: string;
  tokens_input: number;
  tokens_output: number;
  tokens_total: number;
  error_type: string | null;
  error_message: string | null;
  started_at: string | null;
  completed_at: string | null;
  metrics: Record<string, unknown>;
};

export type SurfaceSourceChild = {
  title: string;
  body: string;
  raw_text: string;
  label_kind: string;
  metadata: Record<string, unknown>;
};

export type SurfaceSourceUnit = {
  id: string;
  run_id: string;
  document_id: string;
  source_unit_key: string;
  source_chunk_indexes: number[];
  title: string;
  body: string;
  children: SurfaceSourceChild[];
  raw_text: string;
  section_path: string[];
  source_refs: string[];
  preprocessing_mode: string;
  metadata: Record<string, unknown>;
};

export type SurfaceCompilationResponse = {
  run: SurfaceCompilationRun | null;
  stages: SurfaceCompilationStage[];
  source_units?: SurfaceSourceUnit[];
};

export type SurfaceRelation = {
  id?: string;
  run_id?: string;
  document_id?: string;
  parent_surface_key: string;
  child_surface_key: string;
  relation_type: string;
  reason: string;
  confidence: number;
  source_refs?: string[];
};

export type SurfaceOwnership = {
  id?: string;
  run_id?: string;
  document_id?: string;
  question: string;
  owner_surface_key: string;
  question_kind: string;
  confidence: number;
  reason: string;
  rejected_from_surface_keys: string[];
};

export type SurfaceReassignment = {
  id?: string;
  run_id?: string;
  document_id?: string;
  question: string;
  from_surface_key: string;
  to_surface_key: string;
  reason: string;
  confidence: number;
};

export type SurfaceMergeDecision = {
  id: string;
  run_id: string;
  document_id: string;
  survivor_surface_key: string;
  merged_surface_keys: string[];
  keep_separate_surface_keys: string[];
  decision_type: string;
  reason: string;
  confidence: number;
};

export type RetrievalSurface = {
  id: string;
  run_id: string;
  document_id?: string;
  surface_key: string;
  local_surface_key?: string;
  surface_kind: string;
  title: string;
  canonical_question: string;
  answer: string;
  short_answer: string;
  answer_scope: string;
  question_scope: string;
  exclusion_scope: string;
  status: string;
  publication_status: string;
  source_refs: string[];
  source_excerpt?: string;
  source_chunk_indexes: number[];
  confidence: number;
  warnings: string[];
  metadata?: Record<string, unknown>;
  parent_surface_keys?: string[];
  child_surface_keys?: string[];
  owned_questions?: SurfaceOwnership[];
  rejected_questions?: SurfaceOwnership[];
  incoming_reassignments?: SurfaceReassignment[];
  outgoing_reassignments?: SurfaceReassignment[];
  relations?: SurfaceRelation[];
  merge_decisions?: SurfaceMergeDecision[];
  linked_candidate_id: string | null;
  linked_canonical_entry_id: string | null;
  linked_runtime_entry_id: string | null;
};

export type SurfacesResponse = {
  surfaces: RetrievalSurface[];
};

export type SurfaceRelationsResponse = {
  relations: SurfaceRelation[];
};

export type SurfaceOwnershipResponse = {
  ownership: SurfaceOwnership[];
  reassignments: SurfaceReassignment[];
};

export type SurfaceMergeDecisionsResponse = {
  merge_decisions: SurfaceMergeDecision[];
};

export type SurfacePublishResponse = {
  surface_id: string;
  publication_status: string;
  linked_runtime_entry_id: string | null;
};

export const knowledgeSurfaceApi = {
  compilation: (projectId: string, documentId: string) =>
    authedJsonRequest<SurfaceCompilationResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surface-compilation`,
      { method: 'GET' },
    ),

  surfaces: (projectId: string, documentId: string) =>
    authedJsonRequest<SurfacesResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces`,
      { method: 'GET' },
    ),

  relations: (projectId: string, documentId: string) =>
    authedJsonRequest<SurfaceRelationsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surface-relations`,
      { method: 'GET' },
    ),

  ownership: (projectId: string, documentId: string) =>
    authedJsonRequest<SurfaceOwnershipResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surface-ownership`,
      { method: 'GET' },
    ),

  mergeDecisions: (projectId: string, documentId: string) =>
    authedJsonRequest<SurfaceMergeDecisionsResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surface-merge-decisions`,
      { method: 'GET' },
    ),

  publish: (projectId: string, documentId: string, surfaceId: string) =>
    authedJsonRequest<SurfacePublishResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/${surfaceId}/publish`,
      { method: 'POST' },
    ),
};
