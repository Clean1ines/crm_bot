import { useMemo, useState } from 'react';
import type { KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';

export const useKnowledgeCurationSelection = (entries: KnowledgeCurationEntry[]) => {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const selectedEntries = useMemo(() => entries.filter((entry) => selectedIds.has(entry.id)), [entries, selectedIds]);
  const toggleEntry = (entryId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(entryId)) next.delete(entryId);
      else if (next.size < 12) next.add(entryId);
      return next;
    });
  };
  const clearSelection = () => setSelectedIds(new Set());
  return { selectedIds, selectedEntries, toggleEntry, clearSelection, setSelectedIds };
};
