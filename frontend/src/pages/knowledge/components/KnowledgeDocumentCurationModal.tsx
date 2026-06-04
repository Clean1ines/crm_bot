import React, { useMemo, useState } from 'react';
import { ChevronDown, Loader2, Search } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import { BaseModal } from '@shared/ui';
import {
  knowledgeApi,
  type WorkbenchEvidenceTraceCanonicalFact,
  type WorkbenchEvidenceTraceFinding,
  type WorkbenchEvidenceTraceSourceUnit,
  type WorkbenchEvidenceTraceSurface,
} from '@shared/api/modules/knowledge';
import { getErrorMessage } from '@shared/api/core/errors';

const formatNumber = (value: number): string => {
  if (!Number.isFinite(value)) return '0';
  return new Intl.NumberFormat().format(value);
};

const stringValues = (values: unknown[]): string[] => (
  values
    .map((value) => (typeof value === 'string' ? value.trim() : ''))
    .filter((value) => value.length > 0)
);

const searchText = (
  section: WorkbenchEvidenceTraceSourceUnit,
): string => [
  section.title,
  section.text_excerpt,
  ...section.findings.map((finding) => [
    finding.claim,
    finding.claim_kind,
    finding.answer,
    ...stringValues(finding.evidence_quotes),
  ].join(' ')),
  ...section.canonical_facts.map((fact) => [
    fact.claim,
    fact.claim_kind,
    fact.answer,
    ...stringValues(fact.evidence_quotes),
  ].join(' ')),
  ...section.surfaces.map((surface) => [
    surface.claim,
    surface.answer,
    surface.claim_kind,
    ...stringValues(surface.evidence_quotes),
  ].join(' ')),
].join(' ').toLowerCase();

const factSearchText = (fact: WorkbenchEvidenceTraceCanonicalFact): string => [
  fact.claim,
  fact.answer,
  fact.short_answer,
  fact.claim_kind,
  fact.status,
  ...stringValues(fact.question_variants),
  ...stringValues(fact.evidence_quotes),
].join(' ').toLowerCase();

const surfaceSearchText = (surface: WorkbenchEvidenceTraceSurface): string => [
  surface.title,
  surface.claim,
  surface.answer,
  surface.short_answer,
  surface.claim_kind,
  surface.status,
  surface.curation_state,
  ...stringValues(surface.question_variants),
  ...stringValues(surface.evidence_quotes),
].join(' ').toLowerCase();

const TraceDetailRow: React.FC<{ label: string; children: React.ReactNode }> = ({
  label,
  children,
}) => (
  <div>
    <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--text-muted)]">
      {label}
    </div>
    <div className="text-sm leading-relaxed text-[var(--text-primary)]">
      {children}
    </div>
  </div>
);

const EvidenceList: React.FC<{ values: unknown[] }> = ({ values }) => {
  const quotes = stringValues(values);
  if (quotes.length === 0) {
    return <span className="text-[var(--text-muted)]">—</span>;
  }

  return (
    <div className="space-y-2">
      {quotes.slice(0, 4).map((quote, index) => (
        <div
          key={`${quote}-${index}`}
          className="rounded-lg bg-[var(--control-bg)] p-2 text-xs leading-relaxed text-[var(--text-secondary)]"
        >
          {quote}
        </div>
      ))}
      {quotes.length > 4 && (
        <div className="text-xs text-[var(--text-muted)]">
          + ещё {formatNumber(quotes.length - 4)}
        </div>
      )}
    </div>
  );
};

const FindingCard: React.FC<{ finding: WorkbenchEvidenceTraceFinding }> = ({
  finding,
}) => (
  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-3">
    <div className="text-sm font-semibold text-[var(--text-primary)]">
      {finding.claim || finding.title || finding.claim_local_ref || 'Claim observation'}
    </div>
    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">claim</span>
      {finding.claim_kind && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {finding.claim_kind}
        </span>
      )}
      {finding.confidence !== null && typeof finding.confidence === 'number' && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          confidence {finding.confidence.toFixed(2)}
        </span>
      )}
      {finding.claim_local_ref && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {finding.claim_local_ref}
        </span>
      )}
    </div>
    <details className="mt-3 text-xs text-[var(--text-secondary)]">
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Evidence
      </summary>
      <div className="mt-2">
        <EvidenceList values={finding.evidence_quotes} />
      </div>
    </details>
  </div>
);

const CanonicalFactCard: React.FC<{
  fact: WorkbenchEvidenceTraceCanonicalFact;
  onMergeInto?: (factId: string) => void;
  onDelete?: (factId: string) => void;
}> = ({ fact, onMergeInto, onDelete }) => (
  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-3">
    <div className="text-sm font-semibold text-[var(--text-primary)]">
      {fact.claim || fact.fact_key || fact.fact_id}
    </div>
    <div className="mt-1 text-sm leading-relaxed text-[var(--text-muted)]">
      {fact.answer || fact.short_answer || '—'}
    </div>
    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
        canonical fact
      </span>
      {fact.claim_kind && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {fact.claim_kind}
        </span>
      )}
      {fact.status && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {fact.status}
        </span>
      )}
      {fact.source_section_ids.length > 0 && (
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          sections {formatNumber(fact.source_section_ids.length)}
        </span>
      )}
    </div>
    <details className="mt-3 text-xs text-[var(--text-secondary)]">
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Evidence
      </summary>
      <div className="mt-2">
        <EvidenceList values={fact.evidence_quotes} />
      </div>
    </details>
    {(onMergeInto || onDelete) && (
      <div className="mt-3 flex flex-wrap gap-1.5">
        {onMergeInto && (
          <button
            type="button"
            onClick={() => onMergeInto(fact.fact_id)}
            className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-xs text-[var(--accent-primary)] hover:bg-[var(--accent-primary)]/20"
          >
            Merge into…
          </button>
        )}
        {onDelete && (
          <button
            type="button"
            onClick={() => onDelete(fact.fact_id)}
            className="rounded-full bg-[var(--accent-danger-bg)] px-2 py-1 text-xs text-[var(--accent-danger-text)] hover:opacity-80"
          >
            Delete fact
          </button>
        )}
      </div>
    )}
  </div>
);

const SurfaceCard: React.FC<{
  surface: WorkbenchEvidenceTraceSurface;
  isMutating: boolean;
  onApprove: (surfaceId: string) => void;
  onReject: (surfaceId: string) => void;
  onEdit: (surface: WorkbenchEvidenceTraceSurface) => void;
  onPublish: (surfaceId: string) => void;
}> = ({ surface, isMutating, onApprove, onReject, onEdit, onPublish }) => (
  <div className="rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-elevated)] p-3">
    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <div className="text-sm font-semibold text-[var(--text-primary)]">
          {surface.title || surface.claim || surface.surface_id}
        </div>
        <div className="mt-1 text-sm leading-relaxed text-[var(--text-muted)]">
          {surface.answer || surface.short_answer || '—'}
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {surface.status}
        </span>
        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
          {surface.curation_state || 'uncurated'}
        </span>
      </div>
    </div>
    <details className="mt-3 text-xs text-[var(--text-secondary)]">
      <summary className="cursor-pointer font-medium text-[var(--text-primary)]">
        Evidence
      </summary>
      <div className="mt-2">
        <EvidenceList values={surface.evidence_quotes} />
      </div>
    </details>
    <div className="mt-3 flex flex-wrap gap-1.5">
      <button
        type="button"
        disabled={isMutating}
        onClick={() => onApprove(surface.surface_id)}
        className="rounded-full bg-emerald-500/10 px-2 py-1 text-xs text-emerald-700 disabled:opacity-50 dark:text-emerald-300"
      >
        Approve
      </button>
      <button
        type="button"
        disabled={isMutating}
        onClick={() => onReject(surface.surface_id)}
        className="rounded-full bg-[var(--accent-danger-bg)] px-2 py-1 text-xs text-[var(--accent-danger-text)] disabled:opacity-50"
      >
        Reject
      </button>
      <button
        type="button"
        disabled={isMutating}
        onClick={() => onEdit(surface)}
        className="rounded-full bg-[var(--control-bg)] px-2 py-1 text-xs text-[var(--text-secondary)] disabled:opacity-50"
      >
        Edit
      </button>
      <button
        type="button"
        disabled={isMutating}
        onClick={() => onPublish(surface.surface_id)}
        className="rounded-full bg-[var(--accent-primary)]/10 px-2 py-1 text-xs text-[var(--accent-primary)] disabled:opacity-50"
      >
        Publish selected
      </button>
    </div>
  </div>
);

export const KnowledgeDocumentCurationModal: React.FC<{
  projectId: string;
  documentId: string;
  documentName: string;
  onClose: () => void;
}> = ({ projectId, documentId, documentName, onClose }) => {
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState('');
  const [expandedSectionIds, setExpandedSectionIds] = useState<string[]>([]);
  const [activeTab, setActiveTab] = useState<'sections' | 'facts' | 'surfaces' | 'gaps'>('sections');

  const traceQuery = useQuery({
    queryKey: ['knowledge-document-evidence-trace', projectId, documentId],
    queryFn: async () => {
      const { data } = await knowledgeApi.evidenceTrace(projectId, documentId);
      return data;
    },
  });

  const invalidateTrace = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: ['knowledge-document-evidence-trace', projectId, documentId],
    });
    await queryClient.invalidateQueries({
      queryKey: ['knowledge-documents', projectId],
    });
  };

  const approveSurfaceMutation = useMutation({
    mutationFn: (surfaceId: string) =>
      knowledgeApi.approveSurface(projectId, documentId, surfaceId),
    onSuccess: async () => {
      toast.success('Surface approved');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось approve surface'));
    },
  });

  const rejectSurfaceMutation = useMutation({
    mutationFn: ({ surfaceId, reason }: { surfaceId: string; reason: string }) =>
      knowledgeApi.rejectSurface(projectId, documentId, surfaceId, { reason }),
    onSuccess: async () => {
      toast.success('Surface rejected');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось reject surface'));
    },
  });

  const editSurfaceMutation = useMutation({
    mutationFn: ({ surfaceId, answer }: { surfaceId: string; answer: string }) =>
      knowledgeApi.editSurface(projectId, documentId, surfaceId, { answer }),
    onSuccess: async () => {
      toast.success('Surface updated');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось edit surface'));
    },
  });

  const mergeFactsMutation = useMutation({
    mutationFn: ({
      targetFactId,
      sourceFactIds,
      reason,
    }: {
      targetFactId: string;
      sourceFactIds: string[];
      reason: string;
    }) =>
      knowledgeApi.mergeFacts(projectId, documentId, targetFactId, {
        source_fact_ids: sourceFactIds,
        reason,
      }),
    onSuccess: async () => {
      toast.success('Facts merged');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось merge facts'));
    },
  });

  const deleteFactMutation = useMutation({
    mutationFn: ({ factId, reason }: { factId: string; reason: string }) =>
      knowledgeApi.deleteFact(projectId, documentId, factId, { reason }),
    onSuccess: async () => {
      toast.success('Fact deleted');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось delete fact'));
    },
  });

  const publishSelectedMutation = useMutation({
    mutationFn: (surfaceIds: string[]) =>
      knowledgeApi.publishSelectedSurfaces(projectId, documentId, { surface_ids: surfaceIds }),
    onSuccess: async () => {
      toast.success('Selected surfaces published');
      await invalidateTrace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось publish selected surfaces'));
    },
  });

  const isMutating =
    approveSurfaceMutation.isPending ||
    rejectSurfaceMutation.isPending ||
    editSurfaceMutation.isPending ||
    mergeFactsMutation.isPending ||
    deleteFactMutation.isPending ||
    publishSelectedMutation.isPending;

  const normalizedFilter = filter.trim().toLowerCase();
  const sections = useMemo(
    () => traceQuery.data?.source_units ?? [],
    [traceQuery.data?.source_units],
  );
  const findings = traceQuery.data?.findings ?? [];
  const canonicalFacts = useMemo(
    () => traceQuery.data?.canonical_facts ?? [],
    [traceQuery.data?.canonical_facts],
  );
  const surfaces = useMemo(
    () => traceQuery.data?.surfaces ?? [],
    [traceQuery.data?.surfaces],
  );
  const coverage = traceQuery.data?.coverage ?? {};
  const gaps = traceQuery.data?.gaps ?? {};

  const filteredSections = useMemo(() => {
    if (!normalizedFilter) return sections;
    return sections.filter((section) => searchText(section).includes(normalizedFilter));
  }, [normalizedFilter, sections]);

  const filteredFacts = useMemo(() => {
    if (!normalizedFilter) return canonicalFacts;
    return canonicalFacts.filter((fact) => factSearchText(fact).includes(normalizedFilter));
  }, [normalizedFilter, canonicalFacts]);

  const filteredSurfaces = useMemo(() => {
    if (!normalizedFilter) return surfaces;
    return surfaces.filter((surface) => surfaceSearchText(surface).includes(normalizedFilter));
  }, [normalizedFilter, surfaces]);

  const toggleSection = (sectionId: string): void => {
    setExpandedSectionIds((current) => (
      current.includes(sectionId)
        ? current.filter((id) => id !== sectionId)
        : [...current, sectionId]
    ));
  };

  const rejectSurface = (surfaceId: string): void => {
    const reason = window.prompt('Reason for rejection', '');
    if (reason === null) return;
    rejectSurfaceMutation.mutate({ surfaceId, reason });
  };

  const editSurface = (surface: WorkbenchEvidenceTraceSurface): void => {
    const nextAnswer = window.prompt('Edit answer', surface.answer || surface.short_answer || '');
    if (nextAnswer === null) return;
    editSurfaceMutation.mutate({
      surfaceId: surface.surface_id,
      answer: nextAnswer,
    });
  };

  const mergeIntoFact = (targetFactId: string): void => {
    const source = window.prompt('Source fact IDs to merge, comma separated', '');
    if (source === null) return;
    const sourceFactIds = source
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
    if (sourceFactIds.length === 0) {
      toast.error('source_fact_ids required');
      return;
    }
    mergeFactsMutation.mutate({
      targetFactId,
      sourceFactIds,
      reason: 'manual curation merge',
    });
  };

  const deleteFact = (factId: string): void => {
    if (!window.confirm(`Delete fact ${factId}?`)) return;
    deleteFactMutation.mutate({
      factId,
      reason: 'manual curation delete',
    });
  };

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title="Workbench trace & surface curation"
      maxWidthClassName="max-w-6xl"
    >
      <div className="space-y-4">
        <div className="rounded-xl bg-[var(--surface-secondary)] p-3">
          <div className="text-sm font-semibold text-[var(--text-primary)]">
            {documentName}
          </div>
          <p className="mt-1 text-xs leading-relaxed text-[var(--text-muted)]">
            Workbench trace plus explicit surface curation mutations: approve, reject, edit, merge, delete, publish selected.
          </p>
          <div className="mt-2 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
            <span>Секции: {formatNumber(sections.length)}</span>
            <span>Claims: {formatNumber(findings.length)}</span>
            <span>Canonical facts: {formatNumber(canonicalFacts.length)}</span>
            <span>Surfaces: {formatNumber(surfaces.length)}</span>
            <span>Coverage facts: {formatNumber(Number(coverage.canonical_facts_with_evidence ?? 0))}</span>
          </div>
        </div>

        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex flex-wrap gap-2">
            {[
              ['sections', 'Секции и claims'],
              ['facts', 'Canonical facts'],
              ['surfaces', 'Surfaces'],
              ['gaps', 'Пробелы / warnings'],
            ].map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setActiveTab(id as 'sections' | 'facts' | 'surfaces' | 'gaps')}
                className={`rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeTab === id
                    ? 'bg-[var(--accent-primary)] text-white'
                    : 'bg-[var(--control-bg)] text-[var(--text-muted)] hover:text-[var(--text-primary)]'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          <div className="relative min-w-[260px]">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
            <input
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
              placeholder="Поиск по claims, facts, surfaces, evidence"
              className="min-h-10 w-full rounded-lg bg-[var(--control-bg)] py-2 pl-9 pr-3 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
            />
          </div>
        </div>

        {traceQuery.isLoading ? (
          <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span>Загружаю trace документа…</span>
          </div>
        ) : traceQuery.error ? (
          <div className="rounded-xl bg-[var(--accent-danger-bg)] p-4 text-sm text-[var(--accent-danger-text)]">
            {getErrorMessage(traceQuery.error, 'Не удалось загрузить trace документа')}
          </div>
        ) : activeTab === 'sections' ? (
          <div className="max-h-[64vh] space-y-2 overflow-y-auto pr-1">
            {filteredSections.length === 0 ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                Ничего не найдено.
              </div>
            ) : filteredSections.map((section) => {
              const isExpanded = expandedSectionIds.includes(section.section_id);
              return (
                <div
                  key={section.section_id}
                  className="rounded-xl border border-[var(--border-subtle)] bg-[var(--surface-secondary)]"
                >
                  <button
                    type="button"
                    onClick={() => toggleSection(section.section_id)}
                    aria-expanded={isExpanded}
                    className="flex w-full items-start justify-between gap-3 px-3 py-3 text-left transition-colors hover:bg-[var(--control-bg)]"
                  >
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
                        #{section.section_index + 1} · {section.title || section.section_key}
                      </div>
                      <div className="mt-1 line-clamp-2 text-xs text-[var(--text-muted)]">
                        {section.text_excerpt || '—'}
                      </div>
                      <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                          {section.status}
                        </span>
                        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                          claims {formatNumber(section.findings.length)}
                        </span>
                        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                          facts {formatNumber(section.canonical_facts.length)}
                        </span>
                        <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                          surfaces {formatNumber(section.surfaces.length)}
                        </span>
                      </div>
                    </div>
                    <ChevronDown className={`mt-0.5 h-4 w-4 shrink-0 text-[var(--text-muted)] transition-transform ${isExpanded ? 'rotate-180' : ''}`} />
                  </button>

                  {isExpanded && (
                    <div className="space-y-4 border-t border-[var(--border-subtle)] px-3 py-3">
                      <TraceDetailRow label="Текст секции">
                        <div className="whitespace-pre-wrap">
                          {section.raw_text_excerpt || section.text_excerpt || '—'}
                        </div>
                      </TraceDetailRow>

                      <TraceDetailRow label="Извлечённые claims">
                        {section.findings.length === 0 ? (
                          <span className="text-[var(--text-muted)]">Claims не найдены.</span>
                        ) : (
                          <div className="space-y-2">
                            {section.findings.map((finding) => (
                              <FindingCard
                                key={finding.claim_observation_id}
                                finding={finding}
                              />
                            ))}
                          </div>
                        )}
                      </TraceDetailRow>

                      <TraceDetailRow label="Canonical facts из этой секции">
                        {section.canonical_facts.length === 0 ? (
                          <span className="text-[var(--text-muted)]">Факты пока не связаны с секцией.</span>
                        ) : (
                          <div className="space-y-2">
                            {section.canonical_facts.map((fact) => (
                              <CanonicalFactCard
                                key={fact.fact_id}
                                fact={fact}
                                onMergeInto={mergeIntoFact}
                                onDelete={deleteFact}
                              />
                            ))}
                          </div>
                        )}
                      </TraceDetailRow>

                      <TraceDetailRow label="Surfaces из этой секции">
                        {section.surfaces.length === 0 ? (
                          <span className="text-[var(--text-muted)]">Surfaces пока не связаны с секцией.</span>
                        ) : (
                          <div className="space-y-2">
                            {section.surfaces.map((surface) => (
                              <SurfaceCard
                                key={surface.surface_id}
                                surface={surface}
                                isMutating={isMutating}
                                onApprove={(surfaceId) => approveSurfaceMutation.mutate(surfaceId)}
                                onReject={rejectSurface}
                                onEdit={editSurface}
                                onPublish={(surfaceId) => publishSelectedMutation.mutate([surfaceId])}
                              />
                            ))}
                          </div>
                        )}
                      </TraceDetailRow>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        ) : activeTab === 'facts' ? (
          <div className="max-h-[64vh] space-y-2 overflow-y-auto pr-1">
            {filteredFacts.length === 0 ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                Canonical facts не найдены.
              </div>
            ) : filteredFacts.map((fact) => (
              <CanonicalFactCard
                key={fact.fact_id}
                fact={fact}
                onMergeInto={mergeIntoFact}
                onDelete={deleteFact}
              />
            ))}
          </div>
        ) : activeTab === 'surfaces' ? (
          <div className="max-h-[64vh] space-y-2 overflow-y-auto pr-1">
            {filteredSurfaces.length === 0 ? (
              <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
                Surfaces не найдены.
              </div>
            ) : filteredSurfaces.map((surface) => (
              <SurfaceCard
                key={surface.surface_id}
                surface={surface}
                isMutating={isMutating}
                onApprove={(surfaceId) => approveSurfaceMutation.mutate(surfaceId)}
                onReject={rejectSurface}
                onEdit={editSurface}
                onPublish={(surfaceId) => publishSelectedMutation.mutate([surfaceId])}
              />
            ))}
          </div>
        ) : (
          <div className="max-h-[64vh] space-y-3 overflow-y-auto pr-1">
            <TraceDetailRow label="Coverage">
              <pre className="overflow-x-auto rounded-lg bg-[var(--control-bg)] p-3 text-xs text-[var(--text-secondary)]">
                {JSON.stringify(coverage, null, 2)}
              </pre>
            </TraceDetailRow>
            <TraceDetailRow label="Gaps / warnings">
              <pre className="overflow-x-auto rounded-lg bg-[var(--control-bg)] p-3 text-xs text-[var(--text-secondary)]">
                {JSON.stringify(gaps, null, 2)}
              </pre>
            </TraceDetailRow>
          </div>
        )}
      </div>
    </BaseModal>
  );
};
