import { authedJsonRequest } from '../core/http';

export type SurfaceCompilationRun = {
  id: string;
  project_id: string;
  document_id: string;
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

export type SurfaceCompilationResponse = {
  run: SurfaceCompilationRun | null;
  stages: SurfaceCompilationStage[];
};

export type RetrievalSurface = {
  id: string;
  run_id: string;
  surface_key: string;
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
  source_chunk_indexes: number[];
  confidence: number;
  warnings: string[];
  linked_candidate_id: string | null;
  linked_canonical_entry_id: string | null;
  linked_runtime_entry_id: string | null;
};

export type SurfacesResponse = {
  surfaces: RetrievalSurface[];
};

export type SurfaceRelation = {
  parent_surface_key: string;
  child_surface_key: string;
  relation_type: string;
  reason: string;
  confidence: number;
};

export type SurfaceRelationsResponse = {
  relations: SurfaceRelation[];
};

export type SurfaceOwnership = {
  question: string;
  owner_surface_key: string;
  question_kind: string;
  confidence: number;
  reason: string;
  rejected_from_surface_keys: string[];
};

export type SurfaceReassignment = {
  question: string;
  from_surface_key: string;
  to_surface_key: string;
  reason: string;
  confidence: number;
};

export type SurfaceOwnershipResponse = {
  ownership: SurfaceOwnership[];
  reassignments: SurfaceReassignment[];
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

  publish: (projectId: string, documentId: string, surfaceId: string) =>
    authedJsonRequest<SurfacePublishResponse>(
      `/api/projects/${projectId}/knowledge/${documentId}/surfaces/${surfaceId}/publish`,
      { method: 'POST' },
    ),
};
