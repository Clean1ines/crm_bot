import { useQuery } from '@tanstack/react-query';

import { projectsApi } from '@shared/api/modules/projects';
import type { Project } from '../model/types';
import { projectQueryKeys } from './queryKeys';

export const useProjectListQuery = () => {
  return useQuery<Project[]>({
    queryKey: projectQueryKeys.list(),
    queryFn: async () => {
      const { data, error } = await projectsApi.list();
      if (error) throw error;
      return Array.isArray(data) ? data : [];
    },
  });
};
