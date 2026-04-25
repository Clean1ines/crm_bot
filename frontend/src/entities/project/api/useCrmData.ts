import { useQuery } from '@tanstack/react-query';
import { api } from '@shared/api/client';

export interface ProjectClient {
  id: string;
  user_id?: string | null;
  username?: string | null;
  full_name?: string | null;
  email?: string | null;
  company?: string | null;
  phone?: string | null;
  metadata?: Record<string, unknown>;
  chat_id: number;
  source?: string | null;
  created_at?: string | null;
  last_activity_at?: string | null;
  threads_count?: number;
  latest_thread_id?: string | null;
}

export interface ProjectClientsStats {
  total_clients: number;
  new_clients_7d: number;
  active_dialogs: number;
}

export interface ProjectClientsResponse {
  clients: ProjectClient[];
  stats: ProjectClientsStats;
}

export interface ProjectMember {
  user_id: string;
  role: string;
  full_name?: string | null;
  username?: string | null;
  email?: string | null;
  created_at?: string | null;
}

export interface ProjectConfiguration {
  project_id: string;
  settings: Record<string, unknown>;
  policies: Record<string, unknown>;
  limit_profile: Record<string, unknown>;
  integrations: Array<Record<string, unknown>>;
  channels: Array<Record<string, unknown>>;
  prompt_versions: Array<Record<string, unknown>>;
}

export const useProjectConfiguration = (projectId: string | undefined) => {
  return useQuery<ProjectConfiguration>({
    queryKey: ['project-configuration', projectId],
    queryFn: async () => {
      if (!projectId) {
        return {
          project_id: '',
          settings: {},
          policies: {},
          limit_profile: {},
          integrations: [],
          channels: [],
          prompt_versions: [],
        };
      }

      const { data } = await api.projects.getConfiguration(projectId);
      return data as ProjectConfiguration;
    },
    enabled: !!projectId,
  });
};

export const useProjectManagers = (projectId: string | undefined) => {
  return useProjectMembers(projectId, ['manager', 'admin', 'owner']);
};

export const useProjectMembers = (
  projectId: string | undefined,
  roles?: string[],
) => {
  return useQuery<ProjectMember[]>({
    queryKey: ['members', projectId, roles?.join(',') ?? 'all'],
    queryFn: async () => {
      if (!projectId) return [];
      const { data } = await api.members.list(projectId);
      const list = Array.isArray(data) ? data : ((data as any)?.items || []);
      const normalized = (list as any[]).map((item) => ({
        user_id: String(item.user_id ?? item.id ?? ''),
        role: String(item.role ?? ''),
        full_name: item.full_name ?? null,
        username: item.username ?? null,
        email: item.email ?? null,
        created_at: item.created_at ?? null,
      })) as ProjectMember[];
      return roles?.length ? normalized.filter((member) => roles.includes(member.role)) : normalized;
    },
    enabled: !!projectId,
  });
};

export const useProjectClients = (projectId: string | undefined, search?: string) => {
  return useQuery<ProjectClientsResponse>({
    queryKey: ['clients', projectId, search],
    queryFn: async () => {
      if (!projectId) {
        return {
          clients: [],
          stats: { total_clients: 0, new_clients_7d: 0, active_dialogs: 0 },
        };
      }
      const { data, error } = await api.clients.list({ project_id: projectId, search });
      if (error) throw error;

      const payload = data as {
        clients?: ProjectClient[];
        stats?: Partial<ProjectClientsStats>;
      } | undefined;

      return {
        clients: payload?.clients || [],
        stats: {
          total_clients: payload?.stats?.total_clients ?? 0,
          new_clients_7d: payload?.stats?.new_clients_7d ?? 0,
          active_dialogs: payload?.stats?.active_dialogs ?? 0,
        },
      };
    },
    enabled: !!projectId,
  });
};
