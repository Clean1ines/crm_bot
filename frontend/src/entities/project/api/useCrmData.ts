import { useQuery } from '@tanstack/react-query';
import { api } from '@shared/api/client';

export const useProjectManagers = (projectId: string | undefined) => {
  return useQuery<number[]>({
    queryKey: ['managers', projectId],
    queryFn: async () => {
      if (!projectId) return [];
      const { data, error } = await api.projects.getManagers(projectId);
      if (error) throw error;
      // Handle cases where data might be an object wrapping the list
      const list = Array.isArray(data) ? data : ((data as any)?.managers || (data as any)?.items || []);
      return list as number[];
    },
    enabled: !!projectId,
  });
};

export const useProjectClients = (projectId: string | undefined, search?: string) => {
  return useQuery<any[]>({
    queryKey: ['clients', projectId, search],
    queryFn: async () => {
      if (!projectId) return [];
      const { data, error } = await api.clients.list({ project_id: projectId, search });
      if (error) throw error;
      // Handle cases where data might be an object wrapping the list (e.g. { threads: [] })
      const list = Array.isArray(data) ? data : ((data as any)?.threads || (data as any)?.items || []);
      return list as any[];
    },
    enabled: !!projectId,
  });
};
