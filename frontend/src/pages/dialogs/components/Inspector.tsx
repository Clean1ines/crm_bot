import * as React from 'react';
import { useEffect, useState, useRef } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import type { MemoryEntry, TimelineEvent, ThreadState } from '../../../entities/thread/model/types';
import { Edit2, Save, X, MoreHorizontal, AlertCircle, ChevronDown } from 'lucide-react';

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
  const [visibleTabs, setVisibleTabs] = useState<string[]>([]);
  const [hiddenTabs, setHiddenTabs] = useState<Tab[]>([]);
  const [showHiddenMenu, setShowHiddenMenu] = useState(false);
  const tabsContainerRef = useRef<HTMLDivElement>(null);
  const moreButtonRef = useRef<HTMLButtonElement>(null);

  const renderSummary = () => {
    const state = threadState as ThreadState & {
      status?: string;
      lifecycle?: string;
      total_messages?: number;
      created_at?: string;
      updated_at?: string;
      interaction_mode?: string;
    };
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
            <div className="text-sm font-medium text-[var(--text-primary)]">{threadId ? threadId.slice(0, 8) : '—'}</div>
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

  useEffect(() => {
    const checkOverflow = () => {
      if (!tabsContainerRef.current) return;
      const container = tabsContainerRef.current;
      const children = Array.from(container.children);
      let totalWidth = 0;
      const containerWidth = container.clientWidth;
      const visible: string[] = [];
      const hidden: Tab[] = [];

      for (let i = 0; i < children.length; i++) {
        const child = children[i] as HTMLElement;
        if (child.style.display === 'none') continue;
        totalWidth += child.offsetWidth;
        if (totalWidth <= containerWidth - 40) {
          visible.push(tabs[i].id);
        } else {
          hidden.push(tabs[i]);
        }
      }
      setVisibleTabs(visible);
      setHiddenTabs(hidden);
    };

    checkOverflow();
    window.addEventListener('resize', checkOverflow);
    return () => window.removeEventListener('resize', checkOverflow);
  }, [tabs]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (moreButtonRef.current && !moreButtonRef.current.contains(event.target as Node)) {
        setShowHiddenMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const visibleTabsList = tabs.filter(t => visibleTabs.includes(t.id));
  const hiddenTabsList = tabs.filter(t => !visibleTabs.includes(t.id));

  return (
    <div className="flex flex-col h-full bg-white shadow-sm">
      {/* Header without border */}
      <div className="p-4">
        <div className="relative flex items-center">
          <div
            ref={tabsContainerRef}
            className="flex gap-2 overflow-x-auto scrollbar-hide"
            style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
          >
            {visibleTabsList.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setInspectorActiveTab(tab.id as 'summary' | 'memory' | 'decision' | 'timeline' | 'raw')}
                className={`px-2 py-1 text-sm rounded-md transition-all whitespace-nowrap ${
                  inspectorActiveTab === tab.id
                    ? 'bg-[var(--accent-muted)] text-[var(--accent-primary)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          {hiddenTabsList.length > 0 && (
            <div className="relative ml-2">
              <button
                ref={moreButtonRef}
                onClick={() => setShowHiddenMenu(!showHiddenMenu)}
                className="px-2 py-1 text-sm rounded-md text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)] transition-all flex items-center gap-1"
              >
                <MoreHorizontal className="w-4 h-4" />
                <ChevronDown className="w-3 h-3" />
              </button>
              {showHiddenMenu && (
                <div className="absolute right-0 mt-1 w-40 bg-white rounded-md shadow-lg border border-[var(--border-subtle)] z-10">
                  {hiddenTabsList.map((tab) => (
                    <button
                      key={tab.id}
                      onClick={() => {
                        setInspectorActiveTab(tab.id as 'summary' | 'memory' | 'decision' | 'timeline' | 'raw');
                        setShowHiddenMenu(false);
                      }}
                      className="block w-full text-left px-3 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]"
                    >
                      {tab.label}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {isLoadingInspector && <div className="text-center text-[var(--text-muted)]">Загрузка...</div>}
        {!threadId && <div className="text-center text-[var(--text-muted)]">Выберите диалог</div>}
        {threadId && !isLoadingInspector && tabs.find(t => t.id === inspectorActiveTab)?.component()}
      </div>
    </div>
  );
};
