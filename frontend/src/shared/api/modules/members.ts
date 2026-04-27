import { authedDeleteRequest, authedJsonRequest } from '../core/http';

export type ProjectMemberUpsertRequest = {
  user_id: string;
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
