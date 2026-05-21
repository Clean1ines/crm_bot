import { t } from '@shared/i18n';
import React from 'react';
import { Edit3, EyeOff, GitMerge, History, RefreshCw, RotateCcw, SearchCheck, XCircle } from 'lucide-react';
import type { KnowledgeCurationEntry } from '../../../shared/api/modules/knowledgeCuration';

const listCount = (value: unknown): number => Array.isArray(value) ? value.length : 0;

export const KnowledgeEntryCurationCard: React.FC<{
  entry: KnowledgeCurationEntry;
  selected: boolean;
  onToggle: () => void;
  onEdit: () => void;
  onVersions: () => void;
  onDiagnostics: () => void;
  onStatus: (action: 'hide_entry' | 'reject_entry' | 'restore_entry' | 'publish_entry' | 'unpublish_entry') => void;
  onRebuild: () => void;
}> = ({ entry, selected, onToggle, onEdit, onVersions, onDiagnostics, onStatus, onRebuild }) => (
  <article className="rounded-2xl bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-card)]">
    <div className="flex items-start gap-3">
      <input type="checkbox" checked={selected} onChange={onToggle} className="mt-1 h-4 w-4" />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="truncate text-base font-semibold text-[var(--text-primary)]">{entry.title}</h3>
          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-muted)]">{entry.status}/{entry.visibility}</span>
          <span className={`rounded-full px-2 py-0.5 text-xs ${entry.runtime_eligible ? 'bg-emerald-500/10 text-emerald-600' : 'bg-amber-500/10 text-amber-600'}`}>{entry.runtime_eligible ? 'runtime eligible' : 'non-runtime'}</span>
          <span className="rounded-full bg-[var(--control-bg)] px-2 py-0.5 text-xs text-[var(--text-muted)]">v{entry.version}</span>
        </div>
        <p className="mt-2 line-clamp-3 text-sm text-[var(--text-secondary)]">{entry.answer}</p>
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-muted)]">
          <span>{t('ragEval.curation.entry.kindPrefix')} {entry.entry_kind}</span>
          <span>{t('ragEval.curation.entry.sourceRefsPrefix')} {entry.source_refs.length}</span>
          <span>questions: {listCount(entry.enrichment.questions)}</span>
          <span>tags: {listCount(entry.enrichment.tags)}</span>
          <span>{t('ragEval.curation.entry.embeddingPrefix')} {entry.has_embedding ? t('ragEval.curation.boolean.yes') : t('ragEval.curation.boolean.no')}</span>
          <span>{t('ragEval.curation.entry.retrievalRowPrefix')} {entry.has_retrieval_surface ? t('ragEval.curation.boolean.yes') : t('ragEval.curation.boolean.no')}</span>
        </div>
        {!!entry.issues.length && (
          <div className="mt-3 flex flex-wrap gap-2">
            {entry.issues.map((issue) => <span key={`${entry.id}-${issue.type}`} className="rounded-full bg-red-500/10 px-2 py-0.5 text-xs text-red-500">{issue.message}</span>)}
          </div>
        )}
      </div>
    </div>
    <div className="mt-4 flex flex-wrap gap-2">
      <button type="button" onClick={onEdit} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><Edit3 className="mr-1 inline h-4 w-4" />Edit</button>
      <button type="button" onClick={() => onStatus('hide_entry')} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><EyeOff className="mr-1 inline h-4 w-4" />Hide</button>
      <button type="button" onClick={() => onStatus('reject_entry')} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-red-500"><XCircle className="mr-1 inline h-4 w-4" />Reject</button>
      <button type="button" onClick={() => onStatus('restore_entry')} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><RotateCcw className="mr-1 inline h-4 w-4" />Restore</button>
      <button type="button" onClick={() => onStatus(entry.status === 'published' ? 'unpublish_entry' : 'publish_entry')} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><SearchCheck className="mr-1 inline h-4 w-4" />{entry.status === 'published' ? 'Unpublish' : 'Publish'}</button>
      <button type="button" onClick={onRebuild} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><RefreshCw className="mr-1 inline h-4 w-4" />Rebuild search</button>
      <button type="button" onClick={onVersions} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><History className="mr-1 inline h-4 w-4" />Versions</button>
      <button type="button" onClick={onDiagnostics} className="rounded-xl bg-[var(--control-bg)] px-3 py-1.5 text-sm text-[var(--text-primary)]"><GitMerge className="mr-1 inline h-4 w-4" />Diagnostics</button>
    </div>
  </article>
);
