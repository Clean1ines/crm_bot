import React, { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../../../app/store';
import { threadsApi } from '../../../shared/api/modules/threads';
import type { Thread, Client, LastMessage } from '../../../entities/thread/model/types';
import { Search, Circle } from 'lucide-react';
import { getClientDisplayName } from '../../../shared/lib/clients';

interface DialogListProps {
  projectId: string;
  mobile?: boolean;
  onThreadSelect?: (threadId: string) => void;
}

export const DialogList: React.FC<DialogListProps> = ({ projectId, mobile = false, onThreadSelect }) => {
  const { selectedThreadId, setSelectedThreadId } = useAppStore();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [limit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const fetchThreads = useCallback(async (nextOffset: number, reset = false) => {
    if (!projectId) return;
    setLoading(true);
    setLoadError(null);
    try {
      const { data, error } = await threadsApi.list({
        project_id: projectId,
        limit,
        offset: nextOffset,
        status_filter: statusFilter,
        search: search || null,
      });
      if (error) {
        console.error('Failed to fetch threads', error);
        setLoadError('Не удалось загрузить диалоги');
        if (reset) {
          setThreads([]);
          setHasMore(false);
        }
        return;
      }

      const nextThreads = Array.isArray(data) ? data : [];
      if (reset) {
        setThreads(nextThreads);
      } else {
        setThreads((prev) => [...prev, ...nextThreads]);
      }
      setOffset(nextOffset + limit);
      setHasMore(nextThreads.length === limit);
    } catch (err) {
      console.error('Error fetching threads', err);
      setLoadError('Не удалось загрузить диалоги');
      if (reset) {
        setThreads([]);
        setHasMore(false);
      }
    } finally {
      setLoading(false);
    }
  }, [projectId, limit, statusFilter, search]);

  useEffect(() => {
    setOffset(0);
    void fetchThreads(0, true);
  }, [fetchThreads]);

  const loadMore = () => {
    if (!loading && hasMore) {
      void fetchThreads(offset, false);
    }
  };

  const getStatusColor = (status: string) => {
    if (status === 'manual') return 'text-[var(--accent-danger)]';
    return 'text-[var(--accent-success)]';
  };

  const getLastMessageRole = () => {
    return 'assistant';
  };

  const getMessageBackground = (role: string) => {
    if (role === 'assistant') return 'bg-[var(--surface-secondary)]';
    if (role === 'manager') return 'bg-[var(--accent-muted)]';
    return 'bg-[var(--surface-card)] border border-[var(--border-subtle)]';
  };

  const handleThreadSelect = (threadId: string) => {
    setSelectedThreadId(threadId);
    onThreadSelect?.(threadId);
  };

  return (
    <div className={`flex h-full min-h-0 flex-col bg-[var(--surface-card)] shadow-sm ${mobile ? '' : 'border-r border-[var(--border-subtle)]'}`}>
      <div className="border-b border-[var(--border-subtle)] p-4">
        {mobile && (
          <div className="mb-4">
            <h1 className="text-xl font-bold text-[var(--text-primary)]">Диалоги</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">Выберите диалог, чтобы открыть переписку.</p>
          </div>
        )}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder="Поиск по имени..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 rounded-lg bg-[var(--surface-secondary)] text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] transition-all"
          />
        </div>
        <div className="flex gap-2 mt-3">
          {[
            { label: 'Все', value: null },
            { label: 'Авто', value: 'active' },
            { label: 'Менеджер', value: 'manual' },
          ].map((filter) => (
            <button
              key={filter.label}
              onClick={() => setStatusFilter(filter.value)}
              className={`px-2 py-1 text-xs rounded-full transition-all ${
                statusFilter === filter.value
                  ? 'bg-[var(--accent-primary)] text-white shadow-sm'
                  : 'bg-[var(--surface-secondary)] text-[var(--text-secondary)] hover:bg-white hover:shadow-sm hover:text-[var(--text-primary)]'
              }`}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loadError && (
          <div className="m-3 rounded-lg bg-[var(--accent-danger-bg)] p-3 text-sm text-[var(--accent-danger-text)]">
            {loadError}
          </div>
        )}
        {!loadError && !loading && threads.length === 0 && (
          <div className="p-4 text-center text-sm text-[var(--text-muted)]">
            Диалоги не найдены
          </div>
        )}
        {threads.map((thread) => {
          const client = thread.client as unknown as Client;
          const lastMsg = thread.last_message as unknown as LastMessage | null;
          const isActive = selectedThreadId === thread.thread_id;
          const lastMsgRole = getLastMessageRole();
          const bubbleBg = getMessageBackground(lastMsgRole);
          const clientName = getClientDisplayName(client, 'Клиент');
          return (
            <div
              key={thread.thread_id}
              onClick={() => handleThreadSelect(thread.thread_id)}
              className={`relative mx-2 mb-1 rounded-lg border border-transparent p-3 cursor-pointer transition-all duration-150 ${
                isActive
                  ? 'border-[var(--border-subtle)] bg-[var(--surface-secondary)] shadow-sm'
                  : 'hover:border-[var(--border-subtle)] hover:bg-[var(--surface-secondary)] hover:shadow-sm'
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-[var(--accent-primary)] rounded-full" />
              )}
              <div className="flex items-center gap-2">
                <Circle className={`w-2 h-2 fill-current ${getStatusColor(thread.status || 'active')}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline">
                    <span className="font-medium text-[var(--text-primary)] truncate">
                      {clientName}
                    </span>
                    <span className="text-xs text-[var(--text-muted)] ml-2 flex-shrink-0">
                      {lastMsg?.created_at
                        ? new Date(lastMsg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : ''}
                    </span>
                  </div>
                  <div className="text-sm text-[var(--text-secondary)] truncate">
                    <span className={`inline-block max-w-full rounded px-1 ${bubbleBg}`}>
                      {lastMsg?.content || 'Нет сообщений'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          );
        })}
        {hasMore && !loading && threads.length > 0 && (
          <button
            onClick={loadMore}
            className="w-full p-2 text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-primary)] transition-colors"
          >
            Загрузить ещё
          </button>
        )}
        {loading && <div className="p-4 text-center text-[var(--text-muted)]">Загрузка...</div>}
      </div>
    </div>
  );
};
