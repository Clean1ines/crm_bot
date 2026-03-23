import createClient from 'openapi-fetch';
import toast from 'react-hot-toast';
import type { paths, components } from './generated/schema';
import { createTimeoutMiddleware } from './fetchWithTimeout';

// ---------- Base URL for API (from environment) ----------
const API_BASE_URL = import.meta.env.VITE_API_URL || '';

declare global {
  interface Window {
    __lastToast: string | null;
  }
}

// ---------- Token Management ----------
export const getSessionToken = (): string | null => localStorage.getItem('mrak_token');
export const setSessionToken = (token: string): void => localStorage.setItem('mrak_token', token);
export const clearSessionToken = (): void => localStorage.removeItem('mrak_token');

// ---------- Types ----------
export type ProjectResponse = components['schemas']['ProjectResponse'];
type ProjectCreate = components['schemas']['ProjectCreate'];
type ProjectUpdate = components['schemas']['ProjectUpdate'];
type BotTokenRequest = components['schemas']['BotTokenRequest'];
type ManagerAddRequest = components['schemas']['ManagerAddRequest'];
type ApplyTemplateRequest = components['schemas']['ApplyTemplateRequest'];
type ReplyRequest = components['schemas']['ReplyRequest'];
type ChatMessageRequest = components['schemas']['ChatMessageRequest'];
type UpdateMemoryRequest = components['schemas']['UpdateMemoryRequest'];

// ---------- Error Message Extraction ----------
export const getErrorMessage = (error: unknown): string => {
  if (error && typeof error === 'object') {
    if ('error' in error && typeof error.error === 'string') return error.error;
    if ('detail' in error && Array.isArray(error.detail)) {
      const details = error.detail as Array<{ msg?: string }>;
      return details.map(d => d.msg).filter(Boolean).join(', ');
    }
    if ('message' in error && typeof error.message === 'string') return error.message;
  }
  if (error instanceof Error) return error.message;
  return 'Произошла неизвестная ошибка';
};

// ---------- Toast Helpers ----------
const showErrorToast = (message: string): void => {
  const key = `error-${message}`;
  if (window.__lastToast === key) return;
  window.__lastToast = key;
  setTimeout(() => { window.__lastToast = null; }, 1000);
  toast.error(message);
};

// ---------- API Client Setup ----------
export const client = createClient<paths>({
  baseUrl: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
});

// Request middleware: adds Bearer token if available
client.use({
  onRequest({ request }) {
    const token = getSessionToken();
    if (token) {
      request.headers.set('Authorization', `Bearer ${token}`);
    }
    return request;
  },
});

// Response middleware: handles errors
client.use({
  onResponse({ response }) {
    if (!response.ok) {
      return response
        .clone()
        .json()
        .then((errData) => {
          const message = getErrorMessage(errData);
          showErrorToast(message);
          return response;
        })
        .catch(() => {
          const message = response.status >= 500 && response.status < 600
            ? 'Сервер временно недоступен. Пожалуйста, попробуйте позже.'
            : `Ошибка ${response.status}: ${response.statusText}`;
          showErrorToast(message);
          return response;
        });
    }
    return response;
  },
});

client.use(createTimeoutMiddleware(30000));

// ---------- Helper for streaming requests ----------
export async function streamFetch(
  url: string,
  options: RequestInit,
  onChunk: (chunk: string) => void,
  onFinish: (fullText: string) => void,
  onError: (err: Error) => void
) {
  // If URL is not absolute, prepend API_BASE_URL
  const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;
  try {
    const token = getSessionToken();
    const headers = new Headers(options.headers || {});
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    headers.set('Content-Type', 'application/json');

    const response = await fetch(fullUrl, { ...options, headers });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(getErrorMessage(errData) || `HTTP ${response.status}`);
    }
    const reader = response.body?.getReader();
    if (!reader) throw new Error('No response body');
    const decoder = new TextDecoder();
    let fullText = '';
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      const chunk = decoder.decode(value);
      fullText += chunk;
      onChunk(chunk);
    }
    onFinish(fullText);
  } catch (err) {
    onError(err instanceof Error ? err : new Error(String(err)));
  }
}

// ---------- Typed API Endpoints ----------
export const api = Object.assign(client, {
  projects: {
    list: () => client.GET('/api/projects'),
    create: (body: ProjectCreate) => client.POST('/api/projects', { body }),
    get: (projectId: string) => client.GET('/api/projects/{project_id}', { params: { path: { project_id: projectId } } }),
    update: (projectId: string, body: ProjectUpdate) => client.PUT('/api/projects/{project_id}', { params: { path: { project_id: projectId } }, body }),
    delete: (projectId: string) => client.DELETE('/api/projects/{project_id}', { params: { path: { project_id: projectId } } }),
    setBotToken: (projectId: string, token: string) => client.POST('/api/projects/{project_id}/bot-token', { params: { path: { project_id: projectId } }, body: { token } as BotTokenRequest }),
    setManagerToken: (projectId: string, token: string) => client.POST('/api/projects/{project_id}/manager-token', { params: { path: { project_id: projectId } }, body: { token } as BotTokenRequest }),
    getManagers: (projectId: string) => client.GET('/api/projects/{project_id}/managers', { params: { path: { project_id: projectId } } }),
    addManager: (projectId: string, chat_id: number) => client.POST('/api/projects/{project_id}/managers', { params: { path: { project_id: projectId } }, body: { chat_id } as ManagerAddRequest }),
    removeManager: (projectId: string, chat_id: number) => client.DELETE('/api/projects/{project_id}/managers/{chat_id}', { params: { path: { project_id: projectId, chat_id } } }),
    connectBot: (projectId: string, token: string, type: 'client' | 'manager') => client.POST('/api/projects/{project_id}/connect-bot', { params: { path: { project_id: projectId } }, body: { token, type } }),
  },
  templates: {
    list: () => client.GET('/api/templates'),
    apply: (projectId: string, template_slug: string) => client.POST('/api/templates/projects/{project_id}/apply', { params: { path: { project_id: projectId } }, body: { template_slug } as ApplyTemplateRequest }),
  },
  threads: {
    list: (params: { project_id: string; limit?: number; offset?: number; status_filter?: string | null; search?: string | null }) =>
      client.GET('/api/threads', { params: { query: params } }),
    getMessages: (threadId: string, limit?: number, offset?: number) =>
      client.GET('/api/threads/{thread_id}/messages', { params: { path: { thread_id: threadId }, query: { limit, offset } } }),
    reply: (threadId: string, message: string) =>
      client.POST('/api/threads/{thread_id}/reply', { params: { path: { thread_id: threadId } }, body: { message } as ReplyRequest }),
    getTimeline: (threadId: string, limit?: number, offset?: number) =>
      client.GET('/api/threads/{thread_id}/timeline', { params: { path: { thread_id: threadId }, query: { limit, offset } } }),
    getMemory: (threadId: string) =>
      client.GET('/api/threads/{thread_id}/memory', { params: { path: { thread_id: threadId } } }),
    updateMemory: (threadId: string, key: string, value: unknown) =>
      client.PATCH('/api/threads/{thread_id}/memory', { params: { path: { thread_id: threadId } }, body: { key, value: JSON.stringify(value) } as UpdateMemoryRequest }),
    getState: (threadId: string) =>
      client.GET('/api/threads/{thread_id}/state', { params: { path: { thread_id: threadId } } }),
    enableDemo: (threadId: string) =>
      client.POST('/api/threads/{thread_id}/demo', { params: { path: { thread_id: threadId } } }),
  },
  chat: {
    sendStream: (projectId: string, message: string, model?: string) =>
      fetch(`${API_BASE_URL}/api/chat/projects/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, model } as ChatMessageRequest),
      }),
  },
  knowledge: {
    upload: (projectId: string, file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      return fetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge`, {
        method: 'POST',
        body: formData,
      });
    },
  },
  auth: {
    telegram: async (body: { init_data: string }) => {
      const response = await fetch(`${API_BASE_URL}/api/auth/telegram`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await response.json();
      if (!response.ok) throw data;
      return { data, response };
    },
  },
  clients: {
    list: (params: { project_id: string; limit?: number; offset?: number; search?: string | null }) =>
      client.GET('/api/clients', { params: { query: params } }),
    get: (clientId: string, projectId: string) =>
      client.GET('/api/clients/{client_id}', { params: { path: { client_id: clientId }, query: { project_id: projectId } } }),
  },
});
