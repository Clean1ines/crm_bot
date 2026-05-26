import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import {
  knowledgeSurfaceApi,
  type RetrievalSurface,
  type SurfaceOwnership,
  type SurfaceRelation,
} from '@shared/api/modules/knowledgeSurface';
import { getErrorMessage } from '@shared/api/core/errors';

const formatMetric = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString('ru-RU');
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  return '';
};

const ownedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => ownership.filter((item) => item.owner_surface_key === surface.surface_key);

const relationsForSurface = (
  surface: RetrievalSurface,
  relations: SurfaceRelation[],
): SurfaceRelation[] => relations.filter((item) => (
  item.parent_surface_key === surface.surface_key || item.child_surface_key === surface.surface_key
));

export const SurfaceCompilationSummary: React.FC<{
  documentId: string;
  enabled: boolean;
  isDocumentProcessing: boolean;
}> = ({ documentId, enabled, isDocumentProcessing }) => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const queryEnabled = Boolean(projectId && enabled);
  const refetchInterval = isDocumentProcessing ? 3000 : false;

  const compilationQuery = useQuery({
    queryKey: ['knowledge-surface-compilation', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { run: null, stages: [] };
      const { data } = await knowledgeSurfaceApi.compilation(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const surfacesQuery = useQuery({
    queryKey: ['knowledge-surfaces', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { surfaces: [] };
      const { data } = await knowledgeSurfaceApi.surfaces(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const relationsQuery = useQuery({
    queryKey: ['knowledge-surface-relations', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { relations: [] };
      const { data } = await knowledgeSurfaceApi.relations(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const ownershipQuery = useQuery({
    queryKey: ['knowledge-surface-ownership', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { ownership: [], reassignments: [] };
      const { data } = await knowledgeSurfaceApi.ownership(projectId, documentId);
      return data;
    },
    enabled: queryEnabled,
    retry: false,
    refetchInterval,
  });

  const publishMutation = useMutation({
    mutationFn: async (surfaceId: string) => {
      if (!projectId) throw new Error('Project id is missing');
      const { data } = await knowledgeSurfaceApi.publish(projectId, documentId, surfaceId);
      return data;
    },
    onSuccess: async () => {
      toast.success('Surface published to runtime retrieval');
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['knowledge-surfaces', projectId, documentId] }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-surface-compilation', projectId, documentId] }),
        queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] }),
      ]);
    },
    onError: (error) => {
      toast.error(getErrorMessage(error, 'Could not publish surface'));
    },
  });

  if (!enabled) return null;

  const run = compilationQuery.data?.run || null;
  const stages = compilationQuery.data?.stages || [];
  const surfaces = surfacesQuery.data?.surfaces || [];
  const relations = relationsQuery.data?.relations || [];
  const ownership = ownershipQuery.data?.ownership || [];
  const isLoading = compilationQuery.isLoading || surfacesQuery.isLoading;

  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-3 text-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h5 className="font-semibold text-[var(--text-primary)]">FAQ Retrieval Surface Compilation</h5>
          <p className="text-xs text-[var(--text-muted)]">
            {run ? `${run.status} · ${run.prompt_version}` : isLoading ? 'Loading surface run…' : 'No surface run yet'}
          </p>
        </div>
        {run?.metrics && (
          <div className="flex flex-wrap gap-1 text-xs text-[var(--text-secondary)]">
            {['source_unit_count', 'surface_count', 'relation_count', 'ownership_count'].map((key) => {
              const value = formatMetric(run.metrics[key]);
              return value ? (
                <span key={key} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                  {key}: {value}
                </span>
              ) : null;
            })}
          </div>
        )}
      </div>

      {stages.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1 text-xs">
          {stages.map((stage) => (
            <span key={stage.id} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]">
              {stage.stage_kind}: {stage.status}
            </span>
          ))}
        </div>
      )}

      {surfaces.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">
          {isLoading ? 'Loading surfaces…' : 'No compiled surfaces are available yet.'}
        </p>
      ) : (
        <div className="space-y-2">
          {surfaces.map((surface) => {
            const ownedQuestions = ownedQuestionsForSurface(surface, ownership);
            const surfaceRelations = relationsForSurface(surface, relations);
            const isPublished = surface.publication_status === 'published' || Boolean(surface.linked_runtime_entry_id);
            return (
              <div key={surface.id} className="rounded-lg bg-[var(--surface-elevated)] p-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <h6 className="font-medium text-[var(--text-primary)]">{surface.title}</h6>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                        {surface.surface_kind}
                      </span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                        {surface.status}/{surface.publication_status}
                      </span>
                    </div>
                    <p className="mt-1 text-xs text-[var(--text-muted)]">{surface.canonical_question}</p>
                  </div>
                  <button
                    type="button"
                    disabled={isPublished || publishMutation.isPending}
                    onClick={() => publishMutation.mutate(surface.id)}
                    className="rounded-full bg-[var(--accent-primary)]/10 px-2.5 py-1 text-xs font-medium text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)]/20 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    {isPublished ? 'Published' : 'Publish'}
                  </button>
                </div>

                <p className="mt-2 text-xs leading-relaxed text-[var(--text-primary)]">{surface.short_answer || surface.answer}</p>
                {surface.short_answer && surface.answer && surface.short_answer !== surface.answer && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Full answer</summary>
                    <p className="mt-1 whitespace-pre-wrap leading-relaxed">{surface.answer}</p>
                  </details>
                )}

                {ownedQuestions.length > 0 && (
                  <div className="mt-2">
                    <div className="mb-1 text-xs font-medium text-[var(--text-secondary)]">Owned questions</div>
                    <div className="flex flex-wrap gap-1">
                      {ownedQuestions.slice(0, 8).map((item) => (
                        <span key={`${surface.id}-${item.question}`} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]">
                          {item.question}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {surfaceRelations.length > 0 && (
                  <div className="mt-2 text-xs text-[var(--text-muted)]">
                    Relations: {surfaceRelations.map((item) => `${item.parent_surface_key} ${item.relation_type} ${item.child_surface_key}`).join(' · ')}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
