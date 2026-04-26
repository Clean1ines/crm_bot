import { create } from 'zustand';

export interface ProjectSelectionState {
  selectedProjectId: string | null;
  currentProjectId: string | null;
  setSelectedProjectId: (id: string | null) => void;
  setCurrentProjectId: (id: string | null) => void;
  clearSelectedProject: () => void;
}

export const useProjectStore = create<ProjectSelectionState>((set) => ({
  selectedProjectId: null,
  currentProjectId: null,

  setSelectedProjectId: (id) =>
    set({
      selectedProjectId: id,
      currentProjectId: id,
    }),

  setCurrentProjectId: (id) =>
    set({
      selectedProjectId: id,
      currentProjectId: id,
    }),

  clearSelectedProject: () =>
    set({
      selectedProjectId: null,
      currentProjectId: null,
    }),
}));
