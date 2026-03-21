import { Model, Mode } from './types';

export interface AiConfigSlice {
  models: Model[];
  modes: Mode[];
  selectedModel: string | null;
  setModels: (models: Model[]) => void;
  setModes: (modes: Mode[]) => void;
  setSelectedModel: (model: string | null) => void;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const createAiConfigSlice = (set: any): AiConfigSlice => ({
  models: [],
  modes: [],
  selectedModel: null,
  setModels: (models: Model[]) => set({ models }),
  setModes: (modes: Mode[]) => set({ modes }),
  setSelectedModel: (model: string | null) => set({ selectedModel: model }),
});
