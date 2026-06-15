import React, { useEffect, useMemo, useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';

import { BaseModal } from '@shared/ui';
import { getErrorMessage } from '@shared/api/core/errors';
import {
  knowledgeApi,
  type DraftClaimCurationEditablePayload,
  type DraftClaimCurationItem,
  type DraftClaimCurationItemUpdatePayload,
  type DraftClaimCurationWorkspaceResponse,
} from '@shared/api/modules/knowledge';

type DraftClaimCurationWorkspaceModalProps = {
  projectId: string;
  workflowRunId: string;
  documentName: string;
  onClose: () => void;
};

type EditableDraft = {
  key: string;
  claim: string;
  claimKind: string;
  granularity: string;
  possibleQuestionsText: string;
  exclusionScope: string;
  evidenceBlock: string;
  triplesText: string;
};

const formatNumber = (value: number): string =>
  new Intl.NumberFormat('ru-RU').format(Math.max(0, Math.floor(value || 0)));

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const recordText = (value: Record<string, unknown>, key: string): string | null => {
  const field = value[key];
  return typeof field === 'string' && field.trim() ? field.trim() : null;
};

const draftFromPayload = (payload: DraftClaimCurationEditablePayload): EditableDraft => ({
  key: payload.key,
  claim: payload.claim,
  claimKind: payload.claim_kind,
  granularity: payload.granularity,
  possibleQuestionsText: payload.possible_questions.join('\n'),
  exclusionScope: payload.exclusion_scope,
  evidenceBlock: payload.evidence_block,
  triplesText: JSON.stringify(payload.triples, null, 2),
});

const parseTriples = (value: string): Record<string, unknown>[] => {
  const parsed: unknown = JSON.parse(value);
  if (!Array.isArray(parsed)) {
    throw new Error('triples должен быть JSON-массивом объектов');
  }
  return parsed.map((item, index) => {
    if (!isRecord(item)) {
      throw new Error(`triples[${index}] должен быть объектом`);
    }
    return item;
  });
};

const updatePayloadFromDraft = (draft: EditableDraft): DraftClaimCurationItemUpdatePayload => {
  const key = draft.key.trim();
  const claim = draft.claim.trim();

  if (!key) {
    throw new Error('key не может быть пустым');
  }
  if (!claim) {
    throw new Error('claim не может быть пустым');
  }

  return {
    key,
    claim,
    claim_kind: draft.claimKind.trim(),
    granularity: draft.granularity.trim(),
    possible_questions: draft.possibleQuestionsText
      .split(/\r?\n/)
      .map((item) => item.trim())
      .filter((item) => item.length > 0),
    exclusion_scope: draft.exclusionScope.trim(),
    evidence_block: draft.evidenceBlock.trim(),
    triples: parseTriples(draft.triplesText),
  };
};

const itemSearchText = (item: DraftClaimCurationItem): string =>
  [
    item.editable_payload.key,
    item.editable_payload.claim,
    item.editable_payload.claim_kind,
    item.editable_payload.granularity,
    item.editable_payload.evidence_block,
    item.editable_payload.exclusion_scope,
    ...item.editable_payload.possible_questions,
    item.group_ref,
    item.compacted_node_ref,
  ]
    .join(' ')
    .toLowerCase();

const shortClaim = (item: DraftClaimCurationItem): string => {
  const claim = item.editable_payload.claim.trim();
  if (claim.length <= 120) return claim;
  return `${claim.slice(0, 117)}…`;
};

export const DraftClaimCurationWorkspaceModal: React.FC<
  DraftClaimCurationWorkspaceModalProps
> = ({ projectId, workflowRunId, documentName, onClose }) => {
  const queryClient = useQueryClient();
  const [selectedItemRef, setSelectedItemRef] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [excludeReason, setExcludeReason] = useState('');
  const [draft, setDraft] = useState<EditableDraft | null>(null);

  const queryKey = ['draft-claim-curation-workspace', projectId, workflowRunId];

  const workspaceQuery = useQuery({
    queryKey,
    queryFn: async (): Promise<DraftClaimCurationWorkspaceResponse> => {
      try {
        const { data } = await knowledgeApi.openCurationWorkspace(
          projectId,
          workflowRunId,
        );
        return data;
      } catch {
        const { data } = await knowledgeApi.readCurationWorkspace(
          projectId,
          workflowRunId,
        );
        return data;
      }
    },
    enabled: Boolean(projectId && workflowRunId),
    retry: false,
  });

  const workspace = workspaceQuery.data ?? null;
  const items = workspace?.items ?? [];
  const filteredItems = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();
    if (!query) return items;
    return items.filter((item) => itemSearchText(item).includes(query));
  }, [items, searchQuery]);

  const selectedItem =
    items.find((item) => item.item_ref === selectedItemRef) ??
    filteredItems[0] ??
    items[0] ??
    null;

  useEffect(() => {
    if (!selectedItem && selectedItemRef !== null) {
      setSelectedItemRef(null);
      setDraft(null);
      return;
    }

    if (selectedItem && selectedItem.item_ref !== selectedItemRef) {
      setSelectedItemRef(selectedItem.item_ref);
      setDraft(draftFromPayload(selectedItem.editable_payload));
    }
  }, [selectedItem, selectedItemRef]);

  const refreshWorkspace = async (): Promise<void> => {
    await queryClient.invalidateQueries({ queryKey });
    await queryClient.invalidateQueries({
      queryKey: ['knowledge-workflow-live-state', projectId],
    });
    await queryClient.invalidateQueries({ queryKey: ['knowledge-documents', projectId] });
  };

  const saveMutation = useMutation({
    mutationFn: async (item: DraftClaimCurationItem) => {
      if (!draft) throw new Error('Нет выбранного claim для сохранения');
      const payload = updatePayloadFromDraft(draft);
      await knowledgeApi.updateCurationItem(
        projectId,
        workflowRunId,
        item.item_ref,
        payload,
      );
    },
    onSuccess: async () => {
      toast.success('Изменения сохранены');
      await refreshWorkspace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось сохранить claim'));
    },
  });

  const excludeMutation = useMutation({
    mutationFn: async (item: DraftClaimCurationItem) => {
      await knowledgeApi.excludeCurationItem(
        projectId,
        workflowRunId,
        item.item_ref,
        excludeReason,
      );
    },
    onSuccess: async () => {
      toast.success('Claim исключён из публикации');
      setExcludeReason('');
      await refreshWorkspace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось исключить claim'));
    },
  });

  const includeMutation = useMutation({
    mutationFn: async (item: DraftClaimCurationItem) => {
      await knowledgeApi.includeCurationItem(projectId, workflowRunId, item.item_ref);
    },
    onSuccess: async () => {
      toast.success('Claim возвращён в публикацию');
      await refreshWorkspace();
    },
    onError: (error: unknown) => {
      toast.error(getErrorMessage(error, 'Не удалось вернуть claim'));
    },
  });

  const itemCount = items.length;
  const excludedCount = items.filter((item) => item.excluded).length;
  const publishableCount = itemCount - excludedCount;
  const isMutating =
    saveMutation.isPending || excludeMutation.isPending || includeMutation.isPending;

  return (
    <BaseModal
      isOpen
      onClose={onClose}
      title="Курация знаний"
      cancelLabel="Закрыть"
      maxWidthClassName="max-w-6xl"
    >
      <div className="space-y-4">
        <div className="rounded-xl bg-[var(--surface-secondary)] p-3 text-sm text-[var(--text-secondary)]">
          <div className="font-semibold text-[var(--text-primary)]">
            Документ: {documentName}
          </div>
          <div className="mt-1 break-all text-xs">
            workflow_run_id: {workflowRunId}
          </div>
          {workspace && (
            <div className="mt-2 flex flex-wrap gap-2 text-xs">
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                workspace: {workspace.workspace.status}
              </span>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                всего знаний: {formatNumber(itemCount)}
              </span>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                исключено: {formatNumber(excludedCount)}
              </span>
              <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                будет опубликовано: {formatNumber(publishableCount)}
              </span>
            </div>
          )}
          <button
            type="button"
            disabled
            title="Публикация будет подключена следующим шагом"
            className="mt-3 rounded-lg bg-[var(--control-bg)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] opacity-60"
          >
            Опубликовать
          </button>
        </div>

        {workspaceQuery.isLoading && (
          <div className="flex items-center gap-2 rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            <Loader2 className="h-4 w-4 animate-spin" />
            Открываем workspace курации…
          </div>
        )}

        {workspaceQuery.error && (
          <div className="rounded-xl border border-[var(--accent-danger)]/30 bg-[var(--accent-danger-bg)] p-4 text-sm text-[var(--accent-danger-text)]">
            {getErrorMessage(workspaceQuery.error, 'Не удалось открыть workspace курации')}
          </div>
        )}

        {workspace && itemCount === 0 && (
          <div className="rounded-xl bg-[var(--surface-secondary)] p-4 text-sm text-[var(--text-muted)]">
            В workspace пока нет compacted claims.
          </div>
        )}

        {workspace && itemCount > 0 && (
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(260px,360px)_1fr]">
            <div className="space-y-3">
              <input
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Найти claim…"
                className="w-full rounded-xl bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
              />
              <div className="max-h-[60vh] space-y-2 overflow-y-auto pr-1">
                {filteredItems.map((item) => (
                  <button
                    key={item.item_ref}
                    type="button"
                    onClick={() => {
                      setSelectedItemRef(item.item_ref);
                      setDraft(draftFromPayload(item.editable_payload));
                    }}
                    className={`w-full rounded-xl border p-3 text-left transition-colors ${
                      selectedItem?.item_ref === item.item_ref
                        ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/10'
                        : 'border-[var(--border-subtle)] bg-[var(--surface-secondary)] hover:bg-[var(--surface-hover)]'
                    }`}
                  >
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      {shortClaim(item)}
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-muted)]">
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                        {item.editable_payload.claim_kind}
                      </span>
                      <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5">
                        {item.editable_payload.granularity}
                      </span>
                      {item.excluded && (
                        <span className="rounded-full bg-[var(--accent-danger-bg)] px-2 py-0.5 text-[var(--accent-danger-text)]">
                          исключён
                        </span>
                      )}
                    </div>
                  </button>
                ))}
              </div>
            </div>

            {selectedItem && draft && (
              <div className="space-y-4 rounded-xl bg-[var(--surface-secondary)] p-4">
                <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <div className="text-sm font-semibold text-[var(--text-primary)]">
                      Редактирование compacted claim
                    </div>
                    <div className="mt-1 break-all text-xs text-[var(--text-muted)]">
                      {selectedItem.item_ref}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => saveMutation.mutate(selectedItem)}
                      disabled={isMutating}
                      className="rounded-lg bg-[var(--accent-primary)] px-3 py-1.5 text-xs font-medium text-white disabled:opacity-50"
                    >
                      Сохранить изменения
                    </button>
                    {selectedItem.excluded ? (
                      <button
                        type="button"
                        onClick={() => includeMutation.mutate(selectedItem)}
                        disabled={isMutating}
                        className="rounded-lg bg-[var(--accent-success-bg)] px-3 py-1.5 text-xs font-medium text-[var(--accent-success-text)] disabled:opacity-50"
                      >
                        Вернуть в публикацию
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => excludeMutation.mutate(selectedItem)}
                        disabled={isMutating}
                        className="rounded-lg bg-[var(--accent-danger-bg)] px-3 py-1.5 text-xs font-medium text-[var(--accent-danger-text)] disabled:opacity-50"
                      >
                        Исключить
                      </button>
                    )}
                  </div>
                </div>

                {!selectedItem.excluded && (
                  <label className="block text-xs text-[var(--text-muted)]">
                    Причина исключения
                    <input
                      value={excludeReason}
                      onChange={(event) => setExcludeReason(event.target.value)}
                      placeholder="например: дубль, слишком общий claim, неверная область"
                      className="mt-1 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                    />
                  </label>
                )}

                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <label className="block text-xs text-[var(--text-muted)]">
                    key
                    <input
                      value={draft.key}
                      onChange={(event) =>
                        setDraft((current) =>
                          current ? { ...current, key: event.target.value } : current,
                        )
                      }
                      className="mt-1 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="block text-xs text-[var(--text-muted)]">
                    claim_kind
                    <input
                      value={draft.claimKind}
                      onChange={(event) =>
                        setDraft((current) =>
                          current
                            ? { ...current, claimKind: event.target.value }
                            : current,
                        )
                      }
                      className="mt-1 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="block text-xs text-[var(--text-muted)]">
                    granularity
                    <input
                      value={draft.granularity}
                      onChange={(event) =>
                        setDraft((current) =>
                          current
                            ? { ...current, granularity: event.target.value }
                            : current,
                        )
                      }
                      className="mt-1 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                    />
                  </label>
                  <label className="block text-xs text-[var(--text-muted)]">
                    exclusion_scope
                    <input
                      value={draft.exclusionScope}
                      onChange={(event) =>
                        setDraft((current) =>
                          current
                            ? { ...current, exclusionScope: event.target.value }
                            : current,
                        )
                      }
                      className="mt-1 w-full rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                    />
                  </label>
                </div>

                <label className="block text-xs text-[var(--text-muted)]">
                  claim
                  <textarea
                    value={draft.claim}
                    onChange={(event) =>
                      setDraft((current) =>
                        current ? { ...current, claim: event.target.value } : current,
                      )
                    }
                    rows={4}
                    className="mt-1 w-full resize-y rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                  />
                </label>

                <label className="block text-xs text-[var(--text-muted)]">
                  possible_questions — по одному вопросу на строку
                  <textarea
                    value={draft.possibleQuestionsText}
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, possibleQuestionsText: event.target.value }
                          : current,
                      )
                    }
                    rows={4}
                    className="mt-1 w-full resize-y rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                  />
                </label>

                <label className="block text-xs text-[var(--text-muted)]">
                  evidence_block
                  <textarea
                    value={draft.evidenceBlock}
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, evidenceBlock: event.target.value }
                          : current,
                      )
                    }
                    rows={4}
                    className="mt-1 w-full resize-y rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)]"
                  />
                </label>

                <label className="block text-xs text-[var(--text-muted)]">
                  triples JSON
                  <textarea
                    value={draft.triplesText}
                    onChange={(event) =>
                      setDraft((current) =>
                        current
                          ? { ...current, triplesText: event.target.value }
                          : current,
                      )
                    }
                    rows={7}
                    className="mt-1 w-full resize-y rounded-lg bg-[var(--control-bg)] px-3 py-2 font-mono text-xs text-[var(--text-primary)]"
                  />
                </label>

                <details className="rounded-xl bg-[var(--surface-elevated)] p-3 text-xs text-[var(--text-secondary)]">
                  <summary className="cursor-pointer font-semibold text-[var(--text-primary)]">
                    Машинные поля и provenance
                  </summary>
                  <div className="mt-3 space-y-3">
                    <div className="break-all">
                      <div>merge_decision: {selectedItem.editable_payload.merge_decision}</div>
                      <div>group_ref: {selectedItem.group_ref}</div>
                      <div>compacted_node_ref: {selectedItem.compacted_node_ref}</div>
                      <div>
                        source_claim_refs: {selectedItem.source_claim_refs.join(', ')}
                      </div>
                    </div>

                    <div>
                      <div className="font-semibold text-[var(--text-primary)]">
                        Исходные утверждения
                      </div>
                      <div className="mt-2 space-y-2">
                        {(selectedItem.provenance?.raw_claims ?? []).map((rawClaim) => (
                          <div
                            key={rawClaim.raw_claim_ref}
                            className="rounded-lg bg-[var(--control-bg)] p-2"
                          >
                            <div className="font-medium text-[var(--text-primary)]">
                              {rawClaim.claim}
                            </div>
                            <div className="mt-1 text-[var(--text-muted)]">
                              {rawClaim.evidence_block}
                            </div>
                          </div>
                        ))}
                        {(selectedItem.provenance?.raw_claims ?? []).length === 0 && (
                          <div className="text-[var(--text-muted)]">—</div>
                        )}
                      </div>
                    </div>

                    <div>
                      <div className="font-semibold text-[var(--text-primary)]">
                        Source units
                      </div>
                      <div className="mt-2 space-y-2">
                        {(selectedItem.provenance?.source_units ?? []).map(
                          (sourceUnit, index) => (
                            <div
                              key={`${recordText(sourceUnit, 'source_unit_ref') ?? index}`}
                              className="rounded-lg bg-[var(--control-bg)] p-2"
                            >
                              <div className="break-all font-medium text-[var(--text-primary)]">
                                {recordText(sourceUnit, 'source_unit_ref') ?? 'source unit'}
                              </div>
                              <div className="mt-1 text-[var(--text-muted)]">
                                {recordText(sourceUnit, 'source_unit_text') ?? '—'}
                              </div>
                            </div>
                          ),
                        )}
                        {(selectedItem.provenance?.source_units ?? []).length === 0 && (
                          <div className="text-[var(--text-muted)]">—</div>
                        )}
                      </div>
                    </div>
                  </div>
                </details>
              </div>
            )}
          </div>
        )}
      </div>
    </BaseModal>
  );
};
