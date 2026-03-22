import { create } from 'zustand';

interface AppState {
  selectedModel: string | null;
  setSelectedModel: (model: string | null) => void;
}

export const useAppStore = create<AppState>((set) => ({
  selectedModel: null,
  setSelectedModel: (model) => set({ selectedModel: model }),
}));
