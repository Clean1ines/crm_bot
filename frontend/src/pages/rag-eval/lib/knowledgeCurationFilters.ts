import type { KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';
import type { CurationFilter } from '../components/KnowledgeCurationFiltersBar';

const listCount = (value: unknown): number => Array.isArray(value) ? value.length : 0;
const issueTypes = (entry: KnowledgeCurationEntry): Set<string> => new Set(entry.issues.map((issue) => issue.type));

export const matchesKnowledgeCurationFilter = (entry: KnowledgeCurationEntry, filter: CurationFilter, duplicateIds: Set<string>): boolean => {
  const issues = issueTypes(entry);
  if (filter === 'all') return true;
  if (filter === 'published') return entry.status === 'published';
  if (filter === 'needs_review') return entry.status === 'needs_review';
  if (filter === 'hidden') return entry.status === 'hidden';
  if (filter === 'rejected') return entry.status === 'rejected';
  if (filter === 'merged') return entry.status === 'merged' || Boolean((entry.metadata.curation as Record<string, unknown> | undefined)?.merged_into);
  if (filter === 'possible_duplicates') return duplicateIds.has(entry.id);
  if (filter === 'missing_source_refs') return issues.has('missing_source_refs');
  if (filter === 'missing_embedding') return !entry.has_embedding;
  if (filter === 'no_retrieval_surface') return issues.has('published_without_retrieval_row');
  if (filter === 'fallback_chunk') return entry.entry_kind === 'fallback_chunk';
  if (filter === 'suspicious_short') return issues.has('empty_or_too_short_answer');
  if (filter === 'changed_recently') return Boolean(entry.updated_at);
  return true;
};

export const listQuestionsCount = (entry: KnowledgeCurationEntry): number => listCount(entry.enrichment.questions);
