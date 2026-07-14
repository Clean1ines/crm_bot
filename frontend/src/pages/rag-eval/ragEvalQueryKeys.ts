export const ragEvalQueryKeys = {
  all: ['workbench-rag-eval'] as const,
  project: (projectId: string | undefined) =>
    [...ragEvalQueryKeys.all, projectId] as const,
  documents: (projectId: string | undefined) =>
    [...ragEvalQueryKeys.project(projectId), 'documents'] as const,
  latest: (projectId: string | undefined) =>
    [...ragEvalQueryKeys.project(projectId), 'latest'] as const,
  run: (projectId: string | undefined, runId: string | undefined) =>
    [...ragEvalQueryKeys.project(projectId), 'runs', runId] as const,
  questions: (projectId: string | undefined, runId: string | undefined) =>
    [...ragEvalQueryKeys.run(projectId, runId), 'questions'] as const,
  promotionCandidates: (projectId: string | undefined, runId: string | undefined) =>
    [...ragEvalQueryKeys.run(projectId, runId), 'promotion-candidates'] as const,
  embeddingRevisions: (projectId: string | undefined, runId: string | undefined) =>
    [...ragEvalQueryKeys.run(projectId, runId), 'embedding-revisions'] as const,
  embeddingRevision: (projectId: string | undefined, revisionId: string | undefined) =>
    [...ragEvalQueryKeys.project(projectId), 'embedding-revisions', revisionId] as const,
  verifications: (projectId: string | undefined, runId: string | undefined) =>
    [...ragEvalQueryKeys.run(projectId, runId), 'post-promotion-verifications'] as const,
  verification: (projectId: string | undefined, revisionId: string | undefined) =>
    [...ragEvalQueryKeys.project(projectId), 'embedding-revisions', revisionId, 'verification'] as const,
};
