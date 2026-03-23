import React, { useState, useEffect, useCallback } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import type { Thread } from '../../../entities/thread/model/types';

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
    if (status === 'manual') return 'bg-red-500';
    if (interactionMode === 'demo') return 'bg-yellow-500';
    return 'bg-green-500';
  };

  return (
    <div className="flex flex-col h-full border-r border-[var(--ios-border)] bg-[var(--ios-bg)]">
      <div className="p-4 border-b border-[var(--ios-border)]">
        <input
          type="text"
          placeholder="Поиск по имени..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full px-3 py-2 rounded-lg bg-[var(--ios-input-bg)] text-[var(--text-main)] border border-[var(--ios-border)] focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <div className="flex gap-2 mt-2">
          <button
            onClick={() => setStatusFilter(null)}
            className={`px-2 py-1 text-xs rounded-full ${!statusFilter ? 'bg-blue-500 text-white' : 'bg-[var(--ios-bg-secondary)] text-[var(--text-muted)]'}`}
          >
            Все
          </button>
          <button
            onClick={() => setStatusFilter('active')}
            className={`px-2 py-1 text-xs rounded-full ${statusFilter === 'active' ? 'bg-blue-500 text-white' : 'bg-[var(--ios-bg-secondary)] text-[var(--text-muted)]'}`}
          >
            Авто
          </button>
          <button
            onClick={() => setStatusFilter('manual')}
            className={`px-2 py-1 text-xs rounded-full ${statusFilter === 'manual' ? 'bg-blue-500 text-white' : 'bg-[var(--ios-bg-secondary)] text-[var(--text-muted)]'}`}
          >
            Менеджер
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {threads.map((thread) => (
          <div
            key={thread.thread_id}
            onClick={() => setSelectedThreadId(thread.thread_id)}
            className={`p-3 border-b border-[var(--ios-border)] cursor-pointer transition-colors ${
              selectedThreadId === thread.thread_id
                ? 'bg-[var(--ios-selected)]'
                : 'hover:bg-[var(--ios-hover)]'
            }`}
          >
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${getStatusColor(thread.status, thread.interaction_mode)}`} />
              <div className="flex-1">
                <div className="flex justify-between items-baseline">
                  <span className="font-medium text-[var(--text-main)]">
                    {thread.client?.full_name || thread.client?.username || 'Клиент'}
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">
                    {thread.last_message?.created_at
                      ? new Date(thread.last_message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                      : ''}
                  </span>
                </div>
                <div className="text-sm text-[var(--text-muted)] truncate">
                  {thread.last_message?.content || 'Нет сообщений'}
                </div>
              </div>
            </div>
          </div>
        ))}
        {hasMore && !loading && threads.length > 0 && (
          <button
            onClick={loadMore}
            className="w-full p-2 text-center text-sm text-[var(--text-muted)] hover:text-[var(--text-main)]"
          >
            Загрузить ещё
          </button>
        )}
        {loading && <div className="p-4 text-center text-[var(--text-muted)]">Загрузка...</div>}
      </div>
    </div>
  );
};
