import React from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { useParams } from 'react-router-dom';

import {
  knowledgeSurfaceApi,
  type RetrievalSurface,
  type SurfaceMergeDecision,
  type SurfaceOwnership,
  type SurfaceReassignment,
  type SurfaceRelation,
} from '@shared/api/modules/knowledgeSurface';
import { getErrorMessage } from '@shared/api/core/errors';

const FILTERS = [
  ['all', 'All'],
  ['umbrella', 'Umbrella'],
  ['child', 'Child'],
  ['document_upload', 'Document Upload'],
  ['curation', 'Curation'],
  ['retrieval_quality', 'Retrieval Quality'],
  ['integration', 'Integration'],
  ['channel', 'Channel'],
  ['handoff', 'Handoff / Limits'],
  ['other', 'Other'],
] as const;

type SurfaceFilter = (typeof FILTERS)[number][0];

const formatMetric = (value: unknown): string => {
  if (typeof value === 'number' && Number.isFinite(value)) return value.toLocaleString('ru-RU');
  if (typeof value === 'string') return value;
  if (typeof value === 'boolean') return value ? 'yes' : 'no';
  return '';
};

const ownedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => surface.owned_questions || ownership.filter((item) => item.owner_surface_key === surface.surface_key);

const rejectedQuestionsForSurface = (
  surface: RetrievalSurface,
  ownership: SurfaceOwnership[],
): SurfaceOwnership[] => surface.rejected_questions || ownership.filter((item) => item.rejected_from_surface_keys.includes(surface.surface_key));

const relationsForSurface = (
  surface: RetrievalSurface,
  relations: SurfaceRelation[],
): SurfaceRelation[] => surface.relations || relations.filter((item) => (
  item.parent_surface_key === surface.surface_key || item.child_surface_key === surface.surface_key
));

const reassignmentsForSurface = (
  surface: RetrievalSurface,
  reassignments: SurfaceReassignment[],
): SurfaceReassignment[] => [
  ...(surface.incoming_reassignments || []),
  ...(surface.outgoing_reassignments || []),
  ...reassignments.filter((item) => item.from_surface_key === surface.surface_key || item.to_surface_key === surface.surface_key),
];

const mergeDecisionsForSurface = (
  surface: RetrievalSurface,
  mergeDecisions: SurfaceMergeDecision[],
): SurfaceMergeDecision[] => surface.merge_decisions || mergeDecisions.filter((item) => (
  item.survivor_surface_key === surface.surface_key
  || item.merged_surface_keys.includes(surface.surface_key)
  || item.keep_separate_surface_keys.includes(surface.surface_key)
));

const matchesFilter = (surface: RetrievalSurface, filter: SurfaceFilter): boolean => {
  if (filter === 'all') return true;
  if (filter === 'handoff') return surface.surface_kind === 'handoff' || surface.surface_kind === 'service_limits';
  if (filter === 'other') {
    return !['umbrella', 'child', 'document_upload', 'curation', 'retrieval_quality', 'integration', 'channel', 'handoff', 'service_limits'].includes(surface.surface_kind);
  }
  return surface.surface_kind === filter;
};

const QuestionChips: React.FC<{ title: string; items: SurfaceOwnership[] }> = ({ title, items }) => {
  if (items.length === 0) return null;
  return (
    <div className="mt-2">
      <div className="mb-1 text-xs font-medium text-[var(--text-secondary)]">{title}</div>
      <div className="flex flex-wrap gap-1">
        {items.slice(0, 10).map((item) => (
          <span key={`${title}-${item.owner_surface_key}-${item.question}`} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-secondary)]" title={item.reason}>
            {item.question}
          </span>
        ))}
      </div>
    </div>
  );
};

export const SurfaceCompilationSummary: React.FC<{
  documentId: string;
  enabled: boolean;
  isDocumentProcessing: boolean;
}> = ({ documentId, enabled, isDocumentProcessing }) => {
  const { projectId } = useParams<{ projectId: string }>();
  const queryClient = useQueryClient();
  const [filter, setFilter] = React.useState<SurfaceFilter>('all');
  const queryEnabled = Boolean(projectId && enabled);
  const refetchInterval = isDocumentProcessing ? 3000 : false;

  const compilationQuery = useQuery({
    queryKey: ['knowledge-surface-compilation', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { run: null, stages: [], source_units: [] };
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

  const mergeDecisionsQuery = useQuery({
    queryKey: ['knowledge-surface-merge-decisions', projectId, documentId],
    queryFn: async () => {
      if (!projectId) return { merge_decisions: [] };
      const { data } = await knowledgeSurfaceApi.mergeDecisions(projectId, documentId);
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
        queryClient.invalidateQueries({ queryKey: ['knowledge-surface-merge-decisions', projectId, documentId] }),
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
  const reassignments = ownershipQuery.data?.reassignments || [];
  const mergeDecisions = mergeDecisionsQuery.data?.merge_decisions || [];
  const filteredSurfaces = surfaces.filter((surface) => matchesFilter(surface, filter));
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
            {['source_unit_count', 'surface_count', 'relation_count', 'ownership_count', 'merge_decision_count'].map((key) => {
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

      <div className="mb-3 flex flex-wrap gap-1 text-xs">
        {FILTERS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            onClick={() => setFilter(value)}
            className={`rounded-full px-2 py-0.5 transition-colors ${filter === value ? 'bg-[var(--accent-primary)]/10 text-[var(--accent-primary)]' : 'bg-[var(--control-bg)] text-[var(--text-secondary)]'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {stages.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-1 text-xs">
          {stages.map((stage) => (
            <span key={stage.id} className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-[var(--text-secondary)]" title={stage.error_message || stage.output_summary}>
              {stage.stage_kind}: {stage.status}
            </span>
          ))}
        </div>
      )}

      {surfaces.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">
          {isLoading ? 'Loading surfaces…' : 'No compiled surfaces are available yet.'}
        </p>
      ) : filteredSurfaces.length === 0 ? (
        <p className="text-xs text-[var(--text-muted)]">No surfaces match this filter.</p>
      ) : (
        <div className="space-y-2">
          {filteredSurfaces.map((surface) => {
            const ownedQuestions = ownedQuestionsForSurface(surface, ownership);
            const rejectedQuestions = rejectedQuestionsForSurface(surface, ownership);
            const surfaceRelations = relationsForSurface(surface, relations);
            const surfaceReassignments = reassignmentsForSurface(surface, reassignments);
            const surfaceMergeDecisions = mergeDecisionsForSurface(surface, mergeDecisions);
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

                <QuestionChips title="Owned questions" items={ownedQuestions} />
                <QuestionChips title="Rejected from this surface" items={rejectedQuestions} />

                {surfaceReassignments.length > 0 && (
                  <div className="mt-2 text-xs text-[var(--text-muted)]">
                    Reassignments: {surfaceReassignments.map((item) => `${item.question}: ${item.from_surface_key} → ${item.to_surface_key}`).join(' · ')}
                  </div>
                )}

                {surfaceRelations.length > 0 && (
                  <div className="mt-2 text-xs text-[var(--text-muted)]">
                    Relations: {surfaceRelations.map((item) => `${item.parent_surface_key} ${item.relation_type} ${item.child_surface_key}`).join(' · ')}
                  </div>
                )}

                {surfaceMergeDecisions.length > 0 && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Merge decisions</summary>
                    <div className="mt-1 space-y-1">
                      {surfaceMergeDecisions.map((item) => (
                        <p key={item.id}>
                          {item.decision_type}: survivor {item.survivor_surface_key}; merged [{item.merged_surface_keys.join(', ') || '—'}]; keep separate [{item.keep_separate_surface_keys.join(', ') || '—'}]. {item.reason}
                        </p>
                      ))}
                    </div>
                  </details>
                )}

                {(surface.source_excerpt || surface.source_chunk_indexes.length > 0) && (
                  <details className="mt-2 text-xs text-[var(--text-secondary)]">
                    <summary className="cursor-pointer">Source evidence</summary>
                    <p className="mt-1">chunks: {surface.source_chunk_indexes.join(', ') || '—'}</p>
                    {surface.source_excerpt && <p className="mt-1 whitespace-pre-wrap">{surface.source_excerpt}</p>}
                  </details>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
