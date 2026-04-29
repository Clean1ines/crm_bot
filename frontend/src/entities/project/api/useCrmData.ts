import { useQuery } from '@tanstack/react-query';
import { projectsApi } from '@shared/api/modules/projects';
import { membersApi } from '@shared/api/modules/members';
import { clientsApi } from '@shared/api/modules/clients';

export interface ProjectClient {
  id: string;
  user_id?: string | null;
  display_name?: string | null;
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
  display_name?: string | null;
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

const emptyConfiguration = (): ProjectConfiguration => ({
  project_id: '',
  settings: {},
  policies: {},
  limit_profile: {},
  integrations: [],
  channels: [],
  prompt_versions: [],
});

const asRecord = (value: unknown): Record<string, unknown> => (
  value && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
);

const asArray = <T>(value: unknown): T[] => (
  Array.isArray(value) ? value as T[] : []
);

const normalizeProjectConfiguration = (payload: unknown): ProjectConfiguration => {
  const record = asRecord(payload);

  return {
    project_id: String(record.project_id ?? ''),
    settings: asRecord(record.settings),
    policies: asRecord(record.policies),
    limit_profile: asRecord(record.limit_profile),
    integrations: asArray<Record<string, unknown>>(record.integrations),
    channels: asArray<Record<string, unknown>>(record.channels),
    prompt_versions: asArray<Record<string, unknown>>(record.prompt_versions),
  };
};

export const useProjectConfiguration = (projectId: string | undefined) => {
  return useQuery<ProjectConfiguration>({
    queryKey: ['project-configuration', projectId],
    queryFn: async () => {
      if (!projectId) {
        return emptyConfiguration();
      }

      const { data } = await projectsApi.getConfiguration(projectId);
      return normalizeProjectConfiguration(data);
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
      const { data } = await membersApi.list(projectId);

      const record = asRecord(data);
      const list = Array.isArray(data) ? data : asArray<unknown>(record.items);
      const normalized = list.map((item) => {
        const member = asRecord(item);

        return {
          user_id: String(member.user_id ?? member.id ?? ''),
          role: String(member.role ?? ''),
          display_name: typeof member.display_name === 'string' ? member.display_name : null,
          full_name: typeof member.full_name === 'string' ? member.full_name : null,
          username: typeof member.username === 'string' ? member.username : null,
          email: typeof member.email === 'string' ? member.email : null,
          created_at: typeof member.created_at === 'string' ? member.created_at : null,
        };
      }).filter((member) => member.user_id) as ProjectMember[];

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
      const { data, error } = await clientsApi.list({ project_id: projectId, search });
      if (error) throw error;

      const payload = asRecord(data);
      const stats = asRecord(payload.stats);

      return {
        clients: asArray<ProjectClient>(payload.clients),
        stats: {
          total_clients: Number(stats.total_clients ?? 0),
          new_clients_7d: Number(stats.new_clients_7d ?? 0),
          active_dialogs: Number(stats.active_dialogs ?? 0),
        },
      };
    },
    enabled: !!projectId,
  });
};
