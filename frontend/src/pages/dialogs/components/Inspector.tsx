import * as React from 'react';
import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import type { MemoryEntry, TimelineEvent, ThreadState } from '../../../entities/thread/model/types';
import { Edit2, Save, X, AlertCircle, ChevronDown } from 'lucide-react';
import frontendLogger from '../../../shared/lib/logger';
import { getClientDisplayName } from '../../../shared/lib/clients';

interface Tab {
  id: string;
  label: string;
  component: () => React.ReactNode;
}

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
  const [showTabMenu, setShowTabMenu] = useState(false);
  const moreButtonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const requestIdRef = useRef(0);
  const isMountedRef = useRef(true);

  const isRequestValid = (id: number) => id === requestIdRef.current && isMountedRef.current;

  // Component lifecycle logging
  useEffect(() => {
    frontendLogger.debug('Inspector mounted', { threadId, projectId });
    return () => {
      frontendLogger.debug('Inspector unmounted', { threadId, projectId });
    };
  }, [threadId, projectId]);

  // Log active tab changes
  useEffect(() => {
    frontendLogger.debug('Inspector active tab changed', { inspectorActiveTab, threadId });
  }, [inspectorActiveTab, threadId]);

  const renderSummary = () => {
    const state = threadState as ThreadState & {
      status?: string;
      lifecycle?: string;
      total_messages?: number;
      created_at?: string;
      updated_at?: string;
      interaction_mode?: string;
    };
    const clientName = getClientDisplayName(state?.client, 'Клиент');
    const isDemo = state?.interaction_mode === 'demo';
    return (
      <div className="space-y-3">
        {isDemo && (
          <div className="bg-[var(--accent-muted)] text-[var(--accent-primary)] px-2 py-1 rounded-md text-xs inline-block shadow-sm">
            Демо-режим
          </div>
        )}
        <div className="grid grid-cols-1 gap-3">
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Клиент</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{clientName}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Статус</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{state?.status || '—'}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Настроение</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{state?.lifecycle || '—'}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Сообщений</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{state?.total_messages ?? 0}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Создан</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{state?.created_at ? new Date(state.created_at).toLocaleString() : '—'}</div>
          </div>
          <div className="bg-white rounded-lg shadow-sm p-3">
            <div className="text-xs text-[var(--text-muted)] mb-1">Обновлён</div>
            <div className="text-sm font-medium text-[var(--text-primary)]">{state?.updated_at ? new Date(state.updated_at).toLocaleString() : '—'}</div>
          </div>
        </div>
      </div>
    );
  };

  const renderMemory = () => (
    <div className="space-y-2">
      {threadMemory.map((entry) => (
        <div key={entry.id} className="rounded-lg p-2 shadow-sm hover:shadow-md transition-all bg-white">
          {editingMemoryKey === entry.key ? (
            <div>
              <textarea
                value={editingMemoryValue}
                onChange={(e) => setEditingMemoryValue(e.target.value)}
                className="w-full p-1 bg-[var(--surface-secondary)] rounded text-sm font-mono focus:ring-1 focus:ring-[var(--accent-primary)]"
                rows={3}
              />
              <div className="flex gap-2 mt-2 justify-end">
                <button onClick={saveEditMemory} className="text-[var(--accent-success)] text-sm flex items-center gap-1"><Save className="w-3 h-3" /> Сохранить</button>
                <button onClick={cancelEditMemory} className="text-[var(--accent-danger)] text-sm flex items-center gap-1"><X className="w-3 h-3" /> Отмена</button>
              </div>
            </div>
          ) : (
            <div>
              <div className="flex justify-between">
                <span className="font-mono text-sm text-[var(--text-primary)]">{entry.key}</span>
                <button onClick={() => startEditMemory(entry)} className="text-[var(--text-muted)] hover:text-[var(--accent-primary)] text-xs flex items-center gap-1"><Edit2 className="w-3 h-3" /> Редактировать</button>
              </div>
              <div className="text-sm text-[var(--text-secondary)] break-all mt-1 font-mono">
                {typeof entry.value === 'object' ? JSON.stringify(entry.value, null, 2) : String(entry.value)}
              </div>
              <div className="text-xs text-[var(--text-muted)] mt-1">тип: {entry.type}</div>
            </div>
          )}
        </div>
      ))}
    </div>
  );

  const renderDecisionTrace = () => {
    const policyEvents = threadTimeline.filter(e => e.type === 'policy_decision');
    return (
      <div className="space-y-3">
        {policyEvents.length === 0 && <div className="text-sm text-[var(--text-muted)]">Нет записей решений</div>}
        {policyEvents.map((event) => {
          const payload = event.payload;
          const decision = typeof payload.decision === 'string' ? payload.decision : '—';
          const intent = typeof payload.intent === 'string' ? payload.intent : '—';
          const lifecycle = typeof payload.lifecycle === 'string' ? payload.lifecycle : '—';
          const cta = typeof payload.cta === 'string' ? payload.cta : '—';
          const repeatCount = typeof payload.repeat_count === 'number' ? payload.repeat_count : undefined;
          const leadStatus = typeof payload.lead_status === 'string' ? payload.lead_status : undefined;
          return (
            <div key={event.id} className="bg-white rounded-lg shadow-sm p-3">
              <div className="text-xs text-[var(--text-muted)] mb-1">
                {new Date(event.ts).toLocaleString()}
              </div>
              <div className="text-sm font-mono">Решение: {decision}</div>
              <div className="text-xs text-[var(--text-secondary)] mt-1">
                Намерение: {intent}, ЖЦ: {lifecycle}, CTA: {cta}
              </div>
              {repeatCount !== undefined && (
                <div className="text-xs text-[var(--text-muted)] mt-1">Повторов: {repeatCount}</div>
              )}
              {leadStatus !== undefined && (
                <div className="text-xs text-[var(--text-muted)] mt-1">Статус лида: {leadStatus}</div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

  const renderTimeline = () => (
    <div className="space-y-3">
      {threadTimeline.map((event) => {
        const isEscalation = event.type === 'ticket_created';
        return (
          <div
            key={event.id}
            className={`p-3 rounded-lg shadow-sm ${isEscalation ? 'bg-[var(--accent-muted)]' : 'bg-white'}`}
          >
            <div className="flex items-center gap-2 text-xs text-[var(--text-muted)] mb-1">
              {isEscalation && <AlertCircle className="w-3 h-3 text-[var(--accent-danger)]" />}
              <span>{new Date(event.ts).toLocaleString()}</span>
            </div>
            <div className="text-sm font-mono">{event.type}</div>
            <div className="text-xs text-[var(--text-secondary)] break-all mt-1">
              {JSON.stringify(event.payload).slice(0, 100)}
            </div>
          </div>
        );
      })}
      {hasMoreTimeline && (
        <button onClick={loadMoreTimeline} className="text-[var(--accent-primary)] text-sm">
          Загрузить ещё
        </button>
      )}
    </div>
  );

  const renderRaw = () => (
    <pre className="text-xs overflow-auto bg-white p-2 rounded-lg shadow-sm">
      {JSON.stringify(threadState, null, 2)}
    </pre>
  );

  const tabs: Tab[] = [
    { id: 'summary', label: 'Сводка', component: renderSummary },
    { id: 'memory', label: 'Память', component: renderMemory },
    { id: 'decision', label: 'Решение', component: renderDecisionTrace },
    { id: 'timeline', label: 'События', component: renderTimeline },
    { id: 'raw', label: 'Raw', component: renderRaw },
  ];

  // Data loading effect with request cancellation
  useEffect(() => {
    frontendLogger.debug('Inspector data loading effect triggered', { threadId });
    isMountedRef.current = true;
    const currentRequestId = ++requestIdRef.current;

    if (!threadId) {
      frontendLogger.debug('No threadId, clearing inspector state');
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
        if (!isRequestValid(currentRequestId)) {
          frontendLogger.debug('State request outdated, ignoring', { requestId: currentRequestId });
          return;
        }
        if (!error && data && typeof data === 'object' && 'state' in data) {
          setThreadState(data.state as ThreadState);
          frontendLogger.debug('State loaded successfully', { threadId });
        } else if (error) {
          frontendLogger.warn('State load error', { error });
        }
      } catch (err) {
        if (isRequestValid(currentRequestId)) {
          frontendLogger.error('Failed to load thread state', err, { threadId });
        }
      }
    };

    const loadMemory = async () => {
      try {
        const { data, error } = await api.threads.getMemory(threadId);
        if (!isRequestValid(currentRequestId)) {
          frontendLogger.debug('Memory request outdated, ignoring', { requestId: currentRequestId });
          return;
        }
        if (!error && data && typeof data === 'object' && 'memory' in data && Array.isArray(data.memory)) {
          setThreadMemory(data.memory as MemoryEntry[]);
          frontendLogger.debug('Memory loaded successfully', { threadId, count: data.memory.length });
        } else if (error) {
          frontendLogger.warn('Memory load error', { error });
        }
      } catch (err) {
        if (isRequestValid(currentRequestId)) {
          frontendLogger.error('Failed to load thread memory', err, { threadId });
        }
      }
    };

    const loadTimeline = async () => {
      if (!isRequestValid(currentRequestId)) {
        frontendLogger.debug('Timeline request cancelled before start', { requestId: currentRequestId });
        return;
      }
      setLoadingInspector(true);
      frontendLogger.debug('Loading timeline', { threadId, timelineLimit });
      try {
        const { data, error } = await api.threads.getTimeline(threadId, timelineLimit, 0);
        if (!isRequestValid(currentRequestId)) {
          frontendLogger.debug('Timeline request outdated, ignoring', { requestId: currentRequestId });
          return;
        }
        if (!error && data && typeof data === 'object' && 'events' in data && Array.isArray(data.events)) {
          setThreadTimeline(data.events as TimelineEvent[]);
          setHasMoreTimeline((data.events as TimelineEvent[]).length === timelineLimit);
          frontendLogger.debug('Timeline loaded successfully', { threadId, count: data.events.length });
        } else if (error) {
          frontendLogger.warn('Timeline load error', { error });
        }
      } catch (err) {
        if (isRequestValid(currentRequestId)) {
          frontendLogger.error('Failed to load timeline', err, { threadId });
        }
      } finally {
        if (isRequestValid(currentRequestId)) {
          setLoadingInspector(false);
        } else {
          frontendLogger.debug('Timeline loading finished but request invalid, not resetting loading state');
        }
      }
    };

    loadState();
    loadMemory();
    loadTimeline();

    return () => {
      frontendLogger.debug('Inspector data loading effect cleanup', { threadId, requestId: currentRequestId });
      isMountedRef.current = false;
    };
  }, [threadId, timelineLimit, setThreadState, setThreadMemory, setThreadTimeline, setLoadingInspector]);

  const loadMoreTimeline = async () => {
    if (!threadId || !hasMoreTimeline) {
      frontendLogger.debug('loadMoreTimeline skipped', { threadId, hasMoreTimeline });
      return;
    }
    const currentRequestId = requestIdRef.current;
    if (!isRequestValid(currentRequestId)) {
      frontendLogger.debug('loadMoreTimeline ignored due to stale request');
      return;
    }

    const newOffset = timelineOffset + timelineLimit;
    frontendLogger.debug('Loading more timeline', { threadId, newOffset, limit: timelineLimit });
    try {
      const { data, error } = await api.threads.getTimeline(threadId, timelineLimit, newOffset);
      if (!isRequestValid(currentRequestId)) {
        frontendLogger.debug('loadMoreTimeline outdated, ignoring');
        return;
      }
      if (!error && data && typeof data === 'object' && 'events' in data && Array.isArray(data.events)) {
        const newEvents = data.events as TimelineEvent[];
        setThreadTimeline([...threadTimeline, ...newEvents]);
        setTimelineOffset(newOffset);
        setHasMoreTimeline(newEvents.length === timelineLimit);
        frontendLogger.debug('More timeline loaded', { threadId, newCount: newEvents.length });
      } else if (error) {
        frontendLogger.warn('loadMoreTimeline error', { error });
      }
    } catch (err) {
      if (isRequestValid(currentRequestId)) {
        frontendLogger.error('Failed to load more timeline', err, { threadId });
      }
    }
  };

  const updateMemory = async (key: string, value: unknown) => {
    if (!threadId) return;
    const currentRequestId = requestIdRef.current;
    if (!isRequestValid(currentRequestId)) return;
    frontendLogger.debug('Updating memory', { threadId, key });
    try {
      const { error } = await api.threads.updateMemory(threadId, key, value);
      if (!isRequestValid(currentRequestId)) return;
      if (error) {
        frontendLogger.warn('Memory update error', { error });
      } else {
        const { data } = await api.threads.getMemory(threadId);
        if (!isRequestValid(currentRequestId)) return;
        if (data && typeof data === 'object' && 'memory' in data && Array.isArray(data.memory)) {
          setThreadMemory(data.memory as MemoryEntry[]);
          frontendLogger.debug('Memory updated and reloaded', { threadId, key });
        }
      }
    } catch (err) {
      if (isRequestValid(currentRequestId)) {
        frontendLogger.error('Failed to update memory', err, { threadId, key });
      }
    }
  };

  const startEditMemory = (entry: MemoryEntry) => {
    frontendLogger.debug('Start editing memory', { key: entry.key });
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
      frontendLogger.debug('Saving memory edit', { key: editingMemoryKey });
      await updateMemory(editingMemoryKey, parsedValue);
      setEditingMemoryKey(null);
      setEditingMemoryValue('');
    }
  };

  const cancelEditMemory = () => {
    frontendLogger.debug('Cancel memory edit', { key: editingMemoryKey });
    setEditingMemoryKey(null);
    setEditingMemoryValue('');
  };

  // Click outside to close dropdown – but ignore clicks inside the dropdown itself
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      // If the click is on the toggle button, let the button handle toggling.
      if (moreButtonRef.current && moreButtonRef.current.contains(target)) {
        return;
      }
      // If the click is inside the dropdown container, don't close.
      if (dropdownRef.current && dropdownRef.current.contains(target)) {
        return;
      }
      // Otherwise close the menu.
      setShowTabMenu(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Force content re-render when tab changes by using a key
  const contentKey = `${inspectorActiveTab}-${threadId}`;

  return (
    <div className="flex flex-col h-full bg-white shadow-sm">
      <div className="p-4">
        <div className="relative">
          <button
            ref={moreButtonRef}
            onClick={() => setShowTabMenu(!showTabMenu)}
            className="px-2 py-1 text-sm rounded-md text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] transition-all flex items-center gap-1"
          >
            <span>{tabs.find(t => t.id === inspectorActiveTab)?.label || 'Вкладки'}</span>
            <ChevronDown className="w-3 h-3" />
          </button>
          {showTabMenu && (
            <div
              ref={dropdownRef}
              className="absolute left-0 mt-1 w-40 bg-white rounded-md shadow-lg border border-[var(--border-subtle)] z-20"
            >
              {tabs.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => {
                    console.log('Tab clicked from dropdown:', tab.id);
                    frontendLogger.debug('Tab selected from dropdown', { tab: tab.id });
                    setInspectorActiveTab(tab.id as 'summary' | 'memory' | 'decision' | 'timeline' | 'raw');
                    setShowTabMenu(false);
                  }}
                  className={`block w-full text-left px-3 py-2 text-sm ${
                    inspectorActiveTab === tab.id
                      ? 'bg-[var(--accent-muted)] text-[var(--accent-primary)]'
                      : 'text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4" key={contentKey}>
        {isLoadingInspector && <div className="text-center text-[var(--text-muted)]">Загрузка...</div>}
        {!threadId && <div className="text-center text-[var(--text-muted)]">Выберите диалог</div>}
        {threadId && !isLoadingInspector && tabs.find(t => t.id === inspectorActiveTab)?.component()}
      </div>
    </div>
  );
};
