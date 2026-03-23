import React, { useEffect, useState } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import type { MemoryEntry, TimelineEvent, ThreadState } from '../../../entities/thread/model/types';

interface InspectorProps {
  threadId: string | null;
  projectId: string;
}

export const Inspector: React.FC<InspectorProps> = ({ threadId, projectId }) => {
  const {
    threadState,
    threadTimeline,
    threadMemory,
    setThreadState,
    setThreadTimeline,
    setThreadMemory,
    isLoadingInspector,
    setLoadingInspector,
    inspectorActiveTab,
    setInspectorActiveTab,
  } = useAppStore();

  const [editingMemoryKey, setEditingMemoryKey] = useState<string | null>(null);
  const [editingMemoryValue, setEditingMemoryValue] = useState<string>('');
  const [timelineLimit] = useState(30);
  const [timelineOffset, setTimelineOffset] = useState(0);
  const [hasMoreTimeline, setHasMoreTimeline] = useState(true);

  // Load inspector data when thread changes
  useEffect(() => {
    if (!threadId) {
      setThreadState(null);
      setThreadTimeline([]);
      setThreadMemory([]);
      setTimelineOffset(0);
      setHasMoreTimeline(true);
      return;
    }

    const loadState = async () => {
      try {
        const { data, error } = await api.threads.getState(threadId);
        if (!error && data && typeof data === 'object' && 'state' in data) {
          setThreadState(data.state as ThreadState);
        }
      } catch (err) {
        console.error('Failed to load thread state', err);
      }
    };

    const loadMemory = async () => {
      try {
        const { data, error } = await api.threads.getMemory(threadId);
        if (!error && data && typeof data === 'object' && 'memory' in data && Array.isArray(data.memory)) {
          setThreadMemory(data.memory as MemoryEntry[]);
        }
      } catch (err) {
        console.error('Failed to load memory', err);
      }
    };

    const loadTimeline = async () => {
      setLoadingInspector(true);
      try {
        const { data, error } = await api.threads.getTimeline(threadId, timelineLimit, 0);
        if (!error && data && typeof data === 'object' && 'events' in data && Array.isArray(data.events)) {
          setThreadTimeline(data.events as TimelineEvent[]);
          setHasMoreTimeline((data.events as TimelineEvent[]).length === timelineLimit);
        }
      } catch (err) {
        console.error('Failed to load timeline', err);
      } finally {
        setLoadingInspector(false);
      }
    };

    loadState();
    loadMemory();
    loadTimeline();
  }, [threadId, setThreadState, setThreadMemory, setThreadTimeline, setLoadingInspector]);

  const loadMoreTimeline = async () => {
    if (!threadId || !hasMoreTimeline) return;
    const newOffset = timelineOffset + timelineLimit;
    try {
      const { data, error } = await api.threads.getTimeline(threadId, timelineLimit, newOffset);
      if (!error && data && typeof data === 'object' && 'events' in data && Array.isArray(data.events)) {
        setThreadTimeline([...threadTimeline, ...(data.events as TimelineEvent[])]);
        setTimelineOffset(newOffset);
        setHasMoreTimeline((data.events as TimelineEvent[]).length === timelineLimit);
      }
    } catch (err) {
      console.error('Failed to load more timeline', err);
    }
  };

  const updateMemory = async (key: string, value: unknown) => {
    if (!threadId) return;
    try {
      const { error } = await api.threads.updateMemory(threadId, key, value);
      if (error) {
        console.error('Failed to update memory', error);
      } else {
        // Refresh memory list
        const { data } = await api.threads.getMemory(threadId);
        if (data && typeof data === 'object' && 'memory' in data && Array.isArray(data.memory)) {
          setThreadMemory(data.memory as MemoryEntry[]);
        }
      }
    } catch (err) {
      console.error('Error updating memory', err);
    }
  };

  const startEditMemory = (entry: MemoryEntry) => {
    setEditingMemoryKey(entry.key);
    setEditingMemoryValue(typeof entry.value === 'string' ? entry.value : JSON.stringify(entry.value));
  };

  const saveEditMemory = async () => {
    if (editingMemoryKey) {
      let parsedValue: unknown;
      try {
        parsedValue = JSON.parse(editingMemoryValue);
      } catch {
        parsedValue = editingMemoryValue;
      }
      await updateMemory(editingMemoryKey, parsedValue);
      setEditingMemoryKey(null);
      setEditingMemoryValue('');
    }
  };

  const cancelEditMemory = () => {
    setEditingMemoryKey(null);
    setEditingMemoryValue('');
  };

  const renderSummary = () => {
    const state = threadState as ThreadState & {
      status?: string;
      lifecycle?: string;
      total_messages?: number;
      created_at?: string;
      updated_at?: string;
    };
    return (
      <div className="space-y-2">
        <div className="text-sm text-[var(--text-muted)]">Клиент: {threadId ? threadId.slice(0, 8) : '—'}</div>
        <div className="text-sm text-[var(--text-muted)]">Статус: {state?.status || '—'}</div>
        <div className="text-sm text-[var(--text-muted)]">Настроение: {state?.lifecycle || '—'}</div>
        <div className="text-sm text-[var(--text-muted)]">Сообщений: {state?.total_messages ?? 0}</div>
        <div className="text-sm text-[var(--text-muted)]">Создан: {state?.created_at ? new Date(state.created_at).toLocaleString() : '—'}</div>
        <div className="text-sm text-[var(--text-muted)]">Обновлён: {state?.updated_at ? new Date(state.updated_at).toLocaleString() : '—'}</div>
      </div>
    );
  };

  const renderMemory = () => (
    <div className="space-y-2">
      {threadMemory.map((entry) => (
        <div key={entry.id} className="border border-[var(--ios-border)] rounded p-2">
          {editingMemoryKey === entry.key ? (
            <div>
              <input
                value={editingMemoryValue}
                onChange={(e) => setEditingMemoryValue(e.target.value)}
                className="w-full p-1 bg-[var(--ios-input-bg)] border border-[var(--ios-border)] rounded"
              />
              <div className="flex gap-2 mt-2">
                <button onClick={saveEditMemory} className="text-green-500 text-sm">Сохранить</button>
                <button onClick={cancelEditMemory} className="text-red-500 text-sm">Отмена</button>
              </div>
            </div>
          ) : (
            <div>
              <div className="flex justify-between">
                <span className="font-mono text-sm">{entry.key}</span>
                <button onClick={() => startEditMemory(entry)} className="text-blue-500 text-xs">✎</button>
              </div>
              <div className="text-sm text-[var(--text-muted)] break-all">
                {typeof entry.value === 'object' ? JSON.stringify(entry.value) : String(entry.value)}
              </div>
              <div className="text-xs text-[var(--text-muted)] mt-1">тип: {entry.type}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const renderDecision = () => {
    const state = threadState as ThreadState & {
      decision?: string;
      intent?: string;
      lifecycle?: string;
      cta?: string;
      confidence?: number;
    };
    return (
      <div className="space-y-2">
        <div className="text-sm">
          <span className="font-semibold">Решение:</span> {state?.decision || '—'}
        </div>
        <div className="text-sm">
          <span className="font-semibold">Намерение:</span> {state?.intent || '—'}
        </div>
        <div className="text-sm">
          <span className="font-semibold">Жизненный цикл:</span> {state?.lifecycle || '—'}
        </div>
        <div className="text-sm">
          <span className="font-semibold">CTA:</span> {state?.cta || '—'}
        </div>
        {state?.confidence !== undefined && (
          <div className="text-sm">
            <span className="font-semibold">Уверенность:</span> {state.confidence}
          </div>
        )}
      </div>
    );
  };

  const renderTimeline = () => (
    <div className="space-y-2">
      {threadTimeline.map((event) => (
        <div key={event.id} className="border-l-2 border-[var(--ios-border)] pl-2 py-1">
          <div className="text-xs text-[var(--text-muted)]">
            {new Date(event.ts).toLocaleString()}
          </div>
          <div className="text-sm font-mono">{event.type}</div>
          <div className="text-xs text-[var(--text-muted)] break-all">
            {JSON.stringify(event.payload).slice(0, 100)}
          </div>
        </div>
      ))}
      {hasMoreTimeline && (
        <button onClick={loadMoreTimeline} className="text-blue-500 text-sm mt-2">
          Загрузить ещё
        </button>
      )}
    </div>
  );

  const renderRaw = () => (
    <pre className="text-xs overflow-auto bg-[var(--ios-bg-secondary)] p-2 rounded">
      {JSON.stringify(threadState, null, 2)}
    </pre>
  );

  const tabs = [
    { id: 'summary', label: 'Сводка', component: renderSummary },
    { id: 'memory', label: 'Память', component: renderMemory },
    { id: 'decision', label: 'Решение', component: renderDecision },
    { id: 'timeline', label: 'События', component: renderTimeline },
    { id: 'raw', label: 'Raw', component: renderRaw },
  ] as const;

  return (
    <div className="flex flex-col h-full border-l border-[var(--ios-border)] bg-[var(--ios-bg)]">
      <div className="p-3 border-b border-[var(--ios-border)]">
        <div className="flex gap-2 overflow-x-auto">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setInspectorActiveTab(tab.id)}
              className={`px-3 py-1 text-sm rounded-full whitespace-nowrap ${
                inspectorActiveTab === tab.id
                  ? 'bg-blue-500 text-white'
                  : 'bg-[var(--ios-bg-secondary)] text-[var(--text-muted)]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {isLoadingInspector && <div className="text-center text-[var(--text-muted)]">Загрузка...</div>}
        {!threadId && <div className="text-center text-[var(--text-muted)]">Выберите диалог</div>}
        {threadId && !isLoadingInspector && tabs.find(t => t.id === inspectorActiveTab)?.component()}
      </div>
    </div>
  );
};
