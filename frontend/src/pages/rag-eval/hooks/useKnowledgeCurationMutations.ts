import { useMutation, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { getErrorMessage } from '../../../shared/api/client';
import { knowledgeCurationApi, type KnowledgeCurationEntry, type KnowledgeEntryMergePreview, type KnowledgeEntryMergePreviewRequest, type KnowledgeEntryPatchRequest } from '../../../shared/api/modules/knowledgeCuration';

export const useKnowledgeCurationMutations = (
  projectId: string,
  documentId: string,
  versionEntryId: string | undefined,
  onInvalidateRagEval?: () => Promise<void>,
  onPatchSuccess?: () => void,
  onMergeApplied?: (partial: boolean, error?: string) => void,
  onPreviewSuccess?: (preview: KnowledgeEntryMergePreview) => void,
  onPatchError?: (message: string) => void,
  onGenericError?: (message: string) => void,
) => {
  const queryClient = useQueryClient();
  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ['knowledge-curation', projectId, documentId] });
    await queryClient.invalidateQueries({ queryKey: ['knowledge-curation-actions', projectId, documentId] });
    if (onInvalidateRagEval) await onInvalidateRagEval();
  };

  const statusMutation = useMutation({
    mutationFn: async ({ entry, action }: { entry: KnowledgeCurationEntry; action: 'hide_entry' | 'reject_entry' | 'restore_entry' | 'publish_entry' | 'unpublish_entry' }) => knowledgeCurationApi.setEntryStatus(projectId, documentId, entry.id, { action, expected_version: entry.version, reason: `Manual ${action}`, idempotency_key: crypto.randomUUID() }),
    onSuccess: async () => { toast.success('Статус обновлён'); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось обновить статус')); },
  });

  const patchMutation = useMutation({
    mutationFn: async ({ entry, payload }: { entry: KnowledgeCurationEntry; payload: KnowledgeEntryPatchRequest }) => knowledgeCurationApi.patchEntry(projectId, documentId, entry.id, payload),
    onSuccess: async () => { onPatchSuccess?.(); toast.success('Entry сохранён'); await invalidate(); },
    onError: (error) => { onPatchError?.(getErrorMessage(error, 'Не удалось сохранить entry')); },
  });

  const rebuildMutation = useMutation({
    mutationFn: async (entry: KnowledgeCurationEntry) => knowledgeCurationApi.rebuildEntryEmbedding(projectId, documentId, entry.id, { expected_version: entry.version, reason: 'Manual embedding rebuild', idempotency_key: crypto.randomUUID() }),
    onSuccess: async () => { toast.success('Embedding rebuild выполнен'); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось rebuild embedding')); },
  });

  const previewMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.previewMerge(projectId, documentId, payload),
    onSuccess: ({ data }) => { onPreviewSuccess?.(data.preview); },
    onError: (error) => { onGenericError?.(getErrorMessage(error, 'Preview merge failed')); },
  });

  const applyMergeMutation = useMutation({
    mutationFn: async (payload: KnowledgeEntryMergePreviewRequest) => knowledgeCurationApi.applyMerge(projectId, documentId, payload),
    onSuccess: async ({ data }) => { onMergeApplied?.(Boolean(data.partial), data.error); await invalidate(); },
    onError: (error) => { onGenericError?.(getErrorMessage(error, 'Apply merge failed')); },
  });

  const restoreVersionMutation = useMutation({
    mutationFn: async (versionId: string) => knowledgeCurationApi.restoreEntryVersion(projectId, documentId, String(versionEntryId), versionId, 'Manual version restore'),
    onSuccess: async () => { toast.success('Версия восстановлена'); await invalidate(); },
    onError: (error) => { toast.error(getErrorMessage(error, 'Не удалось восстановить версию')); },
  });

  return { statusMutation, patchMutation, rebuildMutation, previewMutation, applyMergeMutation, restoreVersionMutation };
};
