import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { knowledgeCurationApi, type KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';
import { matchesKnowledgeCurationFilter } from '../lib/knowledgeCurationFilters';
import { sortKnowledgeCurationEntries } from '../lib/knowledgeCurationSort';
import type { CurationFilter, CurationSort } from '../components/KnowledgeCurationFiltersBar';

export const useKnowledgeCurationQueries = (
  projectId: string,
  documentId: string,
  filter: CurationFilter,
  sort: CurationSort,
  versionEntryId?: string,
) => {
  const curationQuery = useQuery({
    queryKey: ['knowledge-curation', projectId, documentId],
    queryFn: async () => (await knowledgeCurationApi.getDocumentCuration(projectId, documentId)).data,
    enabled: !!projectId && !!documentId,
    retry: false,
  });

  const actionsQuery = useQuery({
    queryKey: ['knowledge-curation-actions', projectId, documentId],
    queryFn: async () => (await knowledgeCurationApi.listActions(projectId, documentId)).data.actions,
    enabled: !!projectId && !!documentId,
    retry: false,
  });

  const versionsQuery = useQuery({
    queryKey: ['knowledge-curation-versions', projectId, documentId, versionEntryId],
    queryFn: async () => (await knowledgeCurationApi.listEntryVersions(projectId, documentId, String(versionEntryId))).data.versions,
    enabled: !!projectId && !!documentId && !!versionEntryId,
    retry: false,
  });

  const payload = curationQuery.data;
  const duplicateIds = useMemo(() => new Set((payload?.duplicate_groups ?? []).flatMap((group) => group.entry_ids)), [payload?.duplicate_groups]);
  const duplicateSize = useMemo(() => {
    const map = new Map<string, number>();
    for (const group of payload?.duplicate_groups ?? []) for (const id of group.entry_ids) map.set(id, Math.max(map.get(id) ?? 0, group.entry_ids.length));
    return map;
  }, [payload?.duplicate_groups]);
  const allEntries = useMemo<KnowledgeCurationEntry[]>(() => payload?.entries ?? [], [payload?.entries]);
  const visibleEntries = useMemo(
    () => sortKnowledgeCurationEntries(allEntries.filter((entry) => matchesKnowledgeCurationFilter(entry, filter, duplicateIds)), sort, duplicateSize),
    [allEntries, filter, duplicateIds, sort, duplicateSize],
  );

  return { curationQuery, actionsQuery, versionsQuery, payload, allEntries, visibleEntries };
};
