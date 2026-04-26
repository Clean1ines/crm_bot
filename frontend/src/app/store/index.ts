import { create } from 'zustand';
import type { Message, ThreadState, MemoryEntry, TimelineEvent } from '../../entities/thread/model/types';

interface AppState {
  selectedThreadId: string | null;
  setSelectedThreadId: (id: string | null) => void;

  // Messages for current thread
  messages: Message[];
  addMessage: (message: Message) => void;
  setMessages: (messages: Message[]) => void;
  clearMessages: () => void;

  // Thread state (inspector)
  threadState: ThreadState | null;
  threadTimeline: TimelineEvent[];
  threadMemory: MemoryEntry[];
  setThreadState: (state: ThreadState | null) => void;
  setThreadTimeline: (events: TimelineEvent[]) => void;
  setThreadMemory: (memory: MemoryEntry[]) => void;
  clearInspector: () => void;

  // UI state
  isLoadingMessages: boolean;
  setLoadingMessages: (loading: boolean) => void;
  isLoadingInspector: boolean;
  setLoadingInspector: (loading: boolean) => void;
  inspectorActiveTab: 'summary' | 'memory' | 'decision' | 'timeline' | 'raw';
  setInspectorActiveTab: (tab: AppState['inspectorActiveTab']) => void;

  // Model selection
  selectedModel: string | null;
  setSelectedModel: (model: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedThreadId: null,
  setSelectedThreadId: (id) => set({ selectedThreadId: id }),

  messages: [],
  addMessage: (message) => set((state) => ({ messages: [...state.messages, message] })),
  setMessages: (messages) => set({ messages }),
  clearMessages: () => set({ messages: [] }),

  threadState: null,
  threadTimeline: [],
  threadMemory: [],
  setThreadState: (state) => set({ threadState: state }),
  setThreadTimeline: (events) => set({ threadTimeline: events }),
  setThreadMemory: (memory) => set({ threadMemory: memory }),
  clearInspector: () => set({ threadState: null, threadTimeline: [], threadMemory: [] }),

  isLoadingMessages: false,
  setLoadingMessages: (loading) => set({ isLoadingMessages: loading }),
  isLoadingInspector: false,
  setLoadingInspector: (loading) => set({ isLoadingInspector: loading }),
  inspectorActiveTab: 'summary',
  setInspectorActiveTab: (tab) => set({ inspectorActiveTab: tab }),

  selectedModel: null,
  setSelectedModel: (model) => set({ selectedModel: model }),
}));
