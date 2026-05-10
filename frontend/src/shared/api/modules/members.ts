import { authedDeleteRequest, authedJsonRequest } from '../core/http';

export type ProjectMemberUpsertRequest = {
  user_id: string;
  role: string;
};

export type ProjectInvitationCreateRequest = {
  email: string;
  first_name?: string;
  last_name?: string;
  role: 'admin' | 'manager';
};

export type ProjectInvitationResponse = {
  status: string;
  project_id: string;
  email: string;
  role: string;
  expires_at: string;
  delivery: string;
  invite_link?: string | null;
};

export type ProjectInvitationAcceptResponse = {
  status: string;
  project_id: string;
  user_id: string;
  email: string;
  role: string;
};

export const membersApi = {
  list: (projectId: string) =>
    authedJsonRequest(`/api/projects/${projectId}/members`, {
      method: 'GET',
    }),

  upsert: (projectId: string, body: ProjectMemberUpsertRequest) =>
    authedJsonRequest(`/api/projects/${projectId}/members`, {
      method: 'POST',
      body,
    }),

  remove: (projectId: string, memberUserId: string) =>
    authedDeleteRequest(`/api/projects/${projectId}/members/${memberUserId}`),

  createInvitation: (projectId: string, body: ProjectInvitationCreateRequest) =>
    authedJsonRequest<ProjectInvitationResponse, ProjectInvitationCreateRequest>(
      `/api/projects/${projectId}/members/invitations`,
      {
        method: 'POST',
        body,
      },
    ),

  acceptInvitation: (token: string) =>
    authedJsonRequest<ProjectInvitationAcceptResponse, { token: string }>(
      '/api/projects/invitations/accept',
      {
        method: 'POST',
        body: { token },
      },
    ),

  getReplyHistory: (
    projectId: string,
    managerUserId: string,
    limit?: number,
    offset?: number,
  ) => {
    const params = new URLSearchParams();

    if (limit !== undefined) {
      params.set('limit', String(limit));
    }

    if (offset !== undefined) {
      params.set('offset', String(offset));
    }

    const query = params.toString();
    const suffix = query ? `?${query}` : '';

    return authedJsonRequest(
      `/api/projects/${projectId}/members/${managerUserId}/reply-history${suffix}`,
      {
        method: 'GET',
      },
    );
  },
};
