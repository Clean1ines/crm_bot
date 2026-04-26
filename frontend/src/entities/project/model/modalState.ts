import { create } from 'zustand';

import type { Project } from './types';

interface ProjectModalState {
  isCreateOpen: boolean;
  isDeleteOpen: boolean;
  deletingProject: Project | null;
  openCreateModal: () => void;
  openDeleteConfirm: (project: Project) => void;
  closeModals: () => void;
}

export const useProjectModalState = create<ProjectModalState>((set) => ({
  isCreateOpen: false,
  isDeleteOpen: false,
  deletingProject: null,

  openCreateModal: () => set({ isCreateOpen: true }),

  openDeleteConfirm: (project) =>
    set({
      deletingProject: project,
      isDeleteOpen: true,
    }),

  closeModals: () =>
    set({
      isCreateOpen: false,
      isDeleteOpen: false,
      deletingProject: null,
    }),
}));
