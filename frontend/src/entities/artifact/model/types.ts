export interface Artifact {
  id: string;
  type: string;
  parent_id: string | null;
  content: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  version: string;
  status: string;
  summary?: string;
}

export interface ArtifactType {
  type: string;
  allowed_parents: string[];
  requires_clarification: boolean;
}
