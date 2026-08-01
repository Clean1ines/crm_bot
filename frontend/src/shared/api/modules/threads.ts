import { client } from '../core/openapi';
import type { components } from '../generated/schema';
import type { ThreadStatusFilter } from '../../../entities/thread/model/status';

type ReplyRequest = components['schemas']['ReplyRequest'];
type UpdateMemoryRequest = components['schemas']['UpdateMemoryRequest'];
type UpdateResolutionRequest = components['schemas']['UpdateResolutionRequest'];
export type TicketResolution = components['schemas']['TicketResolutionResponse'];

export type ThreadListParams = {
  project_id: string;
  limit?: number;
  offset?: number;
  status_filter?: ThreadStatusFilter;
  search?: string | null;
};

export const threadsApi = {
  list: (params: ThreadListParams) =>
    client.GET('/api/threads', {
      params: { query: params },
    }),

  getMessages: (threadId: string, limit?: number, offset?: number) =>
    client.GET('/api/threads/{thread_id}/messages', {
      params: {
        path: { thread_id: threadId },
        query: { limit, offset },
      },
    }),

  reply: (threadId: string, message: string) =>
    client.POST('/api/threads/{thread_id}/reply', {
      params: { path: { thread_id: threadId } },
      body: { message } as ReplyRequest,
    }),

  claim: (threadId: string) =>
    client.POST('/api/threads/{thread_id}/claim', {
      params: { path: { thread_id: threadId } },
    }),

  close: (threadId: string) =>
    client.POST('/api/threads/{thread_id}/close', {
      params: { path: { thread_id: threadId } },
    }),

  getTimeline: (threadId: string, limit?: number, offset?: number) =>
    client.GET('/api/threads/{thread_id}/timeline', {
      params: {
        path: { thread_id: threadId },
        query: { limit, offset },
      },
    }),

  getMemory: (threadId: string) =>
    client.GET('/api/threads/{thread_id}/memory', {
      params: { path: { thread_id: threadId } },
    }),

  updateMemory: (threadId: string, key: string, value: unknown) =>
    client.PATCH('/api/threads/{thread_id}/memory', {
      params: { path: { thread_id: threadId } },
      body: {
        key,
        value: JSON.stringify(value),
      } as UpdateMemoryRequest,
    }),

  getState: (threadId: string) =>
    client.GET('/api/threads/{thread_id}/state', {
      params: { path: { thread_id: threadId } },
    }),

  getResolution: (threadId: string) =>
    client.GET('/api/threads/{thread_id}/resolution', {
      params: { path: { thread_id: threadId } },
    }),

  updateResolution: (threadId: string, body: UpdateResolutionRequest) =>
    client.PATCH('/api/threads/{thread_id}/resolution', {
      params: { path: { thread_id: threadId } },
      body,
    }),

  regenerateResolution: (threadId: string) =>
    client.POST('/api/threads/{thread_id}/resolution/regenerate', {
      params: { path: { thread_id: threadId } },
    }),
};
