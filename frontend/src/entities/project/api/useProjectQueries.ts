import { useQuery } from '@tanstack/react-query';

import type { Project } from '../model/types';
import { api } from '@shared/api/client';
import { projectQueryKeys } from './queryKeys';

const normalizeProjects = (payload: unknown): Project[] => {
  return Array.isArray(payload) ? (payload as Project[]) : [];
};

export const useProjectsQuery = () => {
  return useQuery<Project[]>({
    queryKey: projectQueryKeys.list(),
    queryFn: async () => {
      const { data, error } = await api.GET('/api/projects');
      if (error) throw error;
      return normalizeProjects(data);
    },
  });
};
