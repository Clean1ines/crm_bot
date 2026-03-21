import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { ProjectState } from './types';

export const useProjectStore = create<ProjectState>()(
  persist(
    (set) => ({
      projects: [],
      currentProjectId: null,

      setProjects: (projects) => set({ projects }),
      
      setCurrentProjectId: (id) => {
        set({ currentProjectId: id });
        if (id) localStorage.setItem('selectedProjectId', id);
        else localStorage.removeItem('selectedProjectId');
      },

      addProject: (project) =>
        set((state) => ({ projects: [...state.projects, project] })),

      updateProject: (id, updates) =>
        set((state) => ({
          projects: state.projects.map((p) =>
            p.id === id ? { ...p, ...updates } : p
          ),
        })),

      removeProject: (id) =>
        set((state) => ({
          projects: state.projects.filter((p) => p.id !== id),
        })),
    }),
    {
      name: 'project-entity-storage',
      partialize: (state) => ({
        currentProjectId: state.currentProjectId,
      }),
    }
  )
);
