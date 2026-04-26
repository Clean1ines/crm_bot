import type { components } from '../generated/schema';
import { API_BASE_URL } from '../core/config';

type ChatMessageRequest = components['schemas']['ChatMessageRequest'];

export const chatApi = {
  sendStream: (projectId: string, message: string, model?: string, visitorId?: string) =>
    fetch(`${API_BASE_URL}/api/chat/projects/${projectId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        model,
        visitor_id: visitorId,
      } as ChatMessageRequest),
    }),
};
