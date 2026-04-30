import type { Project } from './types';

export type ProjectAccessRole = 'owner' | 'admin' | 'manager' | 'viewer';

const ADMIN_ROLES: ReadonlySet<string> = new Set(['owner', 'admin']);

export const isProjectAdminRole = (role: string | null | undefined): role is ProjectAccessRole => (
  typeof role === 'string' && ADMIN_ROLES.has(role)
);

export const getProjectHomeSegment = (role: string | null | undefined): 'dialogs' | 'tickets' => (
  role === 'manager' ? 'tickets' : 'dialogs'
);

export const getProjectHomePath = (
  projectId: string,
  role: string | null | undefined,
): string => `/projects/${projectId}/${getProjectHomeSegment(role)}`;

export const getProjectRole = (
  project: Project | null | undefined,
): string | null => (typeof project?.access_role === 'string' ? project.access_role : null);
