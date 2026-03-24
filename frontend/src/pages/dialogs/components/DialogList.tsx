import React, { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import type { Thread, Client, LastMessage } from '../../../entities/thread/model/types';
import { Search, Circle } from 'lucide-react';

interface DialogListProps {
  projectId: string;
}

export const DialogList: React.FC<DialogListProps> = ({ projectId }) => {
  const { selectedThreadId, setSelectedThreadId } = useAppStore();
  const [threads, setThreads] = useState<Thread[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  const [limit] = useState(20);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const fetchThreads = useCallback(async (reset = false) => {
    if (!projectId) return;
    setLoading(true);
    try {
      const { data, error } = await api.threads.list({
        project_id: projectId,
        limit,
        offset: reset ? 0 : offset,
        status_filter: statusFilter,
        search: search || null,
      });
      if (error) {
        console.error('Failed to fetch threads', error);
        return;
      }
      if (data) {
        if (reset) {
          setThreads(data);
          setOffset(limit);
          setHasMore(data.length === limit);
        } else {
          setThreads((prev) => [...prev, ...data]);
          setOffset(offset + limit);
          setHasMore(data.length === limit);
        }
      }
    } catch (err) {
      console.error('Error fetching threads', err);
    } finally {
      setLoading(false);
    }
  }, [projectId, limit, offset, statusFilter, search]);

  useEffect(() => {
    setOffset(0);
    fetchThreads(true);
  }, [projectId, statusFilter, search]);

  const loadMore = () => {
    if (!loading && hasMore) {
      fetchThreads();
    }
  };

  const getStatusColor = (status: string, interactionMode: string) => {
    if (status === 'manual') return 'text-[var(--accent-danger)]';
    if (interactionMode === 'demo') return 'text-[var(--accent-warning)]';
    return 'text-[var(--accent-success)]';
  };

  const getLastMessageRole = (thread: Thread) => {
    return 'assistant';
  };

  const getMessageBackground = (role: string) => {
    if (role === 'assistant') return 'bg-[var(--surface-secondary)]';
    if (role === 'manager') return 'bg-[var(--accent-muted)]';
    return 'bg-white';
  };

  return (
    <div className="flex flex-col h-full bg-white shadow-sm">
      <div className="p-4">
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
        {threads.map((thread) => {
          const client = thread.client as unknown as Client;
          const lastMsg = thread.last_message as unknown as LastMessage | null;
          const isActive = selectedThreadId === thread.thread_id;
          const lastMsgRole = getLastMessageRole(thread);
          const bubbleBg = getMessageBackground(lastMsgRole);
          return (
            <div
              key={thread.thread_id}
              onClick={() => setSelectedThreadId(thread.thread_id)}
              className={`relative p-3 mx-2 mb-1 rounded-lg cursor-pointer transition-all duration-150 ${
                isActive
                  ? 'bg-[var(--surface-secondary)] shadow-sm'
                  : 'hover:bg-[var(--surface-secondary)] hover:shadow-sm'
              }`}
            >
              {isActive && (
                <div className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-6 bg-[var(--accent-primary)] rounded-full" />
              )}
              <div className="flex items-center gap-2">
                <Circle className={`w-2 h-2 fill-current ${getStatusColor(thread.status, thread.interaction_mode)}`} />
                <div className="flex-1 min-w-0">
                  <div className="flex justify-between items-baseline">
                    <span className="font-medium text-[var(--text-primary)] truncate">
                      {client?.full_name || client?.username || 'Клиент'}
                    </span>
                    <span className="text-xs text-[var(--text-muted)] ml-2 flex-shrink-0">
                      {lastMsg?.created_at
                        ? new Date(lastMsg.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                        : ''}
                    </span>
                  </div>
                  <div className="text-sm text-[var(--text-secondary)] truncate">
                    <span className={`inline-block px-1 rounded ${bubbleBg}`}>
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
