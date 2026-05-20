import type { KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';
import type { CurationSort } from '../components/KnowledgeCurationFiltersBar';
import { listQuestionsCount } from './knowledgeCurationFilters';

export const sortKnowledgeCurationEntries = (entries: KnowledgeCurationEntry[], sort: CurationSort, duplicateSize: Map<string, number>): KnowledgeCurationEntry[] => {
  const copy = [...entries];
  copy.sort((left, right) => {
    if (sort === 'title') return left.title.localeCompare(right.title);
    if (sort === 'status') return left.status.localeCompare(right.status);
    if (sort === 'updated_at') return String(right.updated_at || '').localeCompare(String(left.updated_at || ''));
    if (sort === 'source_refs_count') return right.source_refs.length - left.source_refs.length;
    if (sort === 'questions_count') return listQuestionsCount(right) - listQuestionsCount(left);
    if (sort === 'duplicate_group_size') return (duplicateSize.get(right.id) ?? 0) - (duplicateSize.get(left.id) ?? 0);
    return right.issues.length - left.issues.length;
  });
  return copy;
};
