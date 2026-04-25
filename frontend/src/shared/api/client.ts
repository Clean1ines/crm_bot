import createClient from 'openapi-fetch';
import toast from 'react-hot-toast';
import type { paths, components } from './generated/schema';
import { createTimeoutMiddleware } from './fetchWithTimeout';
import { queryClient } from './queryClient';

// ---------- Base URL for API (from environment) ----------
const API_BASE_URL = import.meta.env.VITE_API_URL || '';
const LOGIN_PATH = '/login';
const AUTH_CLEARED_EVENT = 'mrak-auth-cleared';

declare global {
  interface Window {
    __lastToast: string | null;
    __isRedirectingToLogin?: boolean;
  }
}

// ---------- Token Management ----------
export const getSessionToken = (): string | null => localStorage.getItem('mrak_token');
export const setSessionToken = (token: string): void => localStorage.setItem('mrak_token', token);
export const clearSessionToken = (): void => localStorage.removeItem('mrak_token');

// ---------- Centralized Unauthorized Handling ----------
export const handleUnauthorizedResponse = (): void => {
  clearSessionToken();

  try {
    queryClient.clear();
  } catch {
    // Query cache cleanup is best-effort. Auth cleanup and redirect must still happen.
  }

  window.dispatchEvent(new Event(AUTH_CLEARED_EVENT));

  if (window.location.pathname === LOGIN_PATH) {
    return;
  }

  if (window.__isRedirectingToLogin) {
    return;
  }

  window.__isRedirectingToLogin = true;
  window.location.replace(LOGIN_PATH);
};

const isUnauthorized = (response: Response): boolean => response.status === 401;

// ---------- Types ----------
export type ProjectResponse = components['schemas']['ProjectResponse'];
type ProjectCreate = components['schemas']['ProjectCreate'];
type ProjectUpdate = components['schemas']['ProjectUpdate'];
type BotTokenRequest = components['schemas']['BotTokenRequest'];
type ManagerAddRequest = components['schemas']['ManagerAddRequest'];
type ReplyRequest = components['schemas']['ReplyRequest'];
type ChatMessageRequest = components['schemas']['ChatMessageRequest'];
type UpdateMemoryRequest = components['schemas']['UpdateMemoryRequest'];
export type ProjectSettingsUpdate = {
  brand_name?: string;
  industry?: string;
  tone_of_voice?: string;
  default_language?: string;
  default_timezone?: string;
  system_prompt_override?: string;
};
export type ProjectPoliciesUpdate = {
  escalation_policy_json?: Record<string, unknown>;
  routing_policy_json?: Record<string, unknown>;
  crm_policy_json?: Record<string, unknown>;
  response_policy_json?: Record<string, unknown>;
  privacy_policy_json?: Record<string, unknown>;
};
export type ProjectLimitProfileUpdate = {
  monthly_token_limit?: number;
  requests_per_minute?: number;
  max_concurrent_threads?: number;
  priority?: number;
  fallback_model?: string;
};
export type ProjectIntegrationUpsert = {
  provider: string;
  status?: string;
  config_json?: Record<string, unknown>;
  credentials_encrypted?: string;
};
export type ProjectChannelUpsert = {
  kind: 'platform' | 'client' | 'manager' | 'widget';
  provider: string;
  status?: string;
  config_json?: Record<string, unknown>;
};

async function authedJsonRequest<TBody>(
  path: string,
  options: { method: string; body?: TBody }
) {
  const token = getSessionToken();
  const headers = new Headers({ 'Content-Type': 'application/json' });
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const data = await response.json().catch(() => null);

  if (isUnauthorized(response)) {
    handleUnauthorizedResponse();
  }

  if (!response.ok) throw data;
  return { data, response };
}

// ---------- Error Message Extraction ----------
export const getErrorMessage = (error: unknown): string => {
  if (error && typeof error === 'object') {
    if ('detail' in error && typeof error.detail === 'string') return error.detail;
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

// Response middleware: handles errors and expired sessions centrally
client.use({
  onResponse({ response }) {
    if (isUnauthorized(response)) {
      handleUnauthorizedResponse();
      showErrorToast('Сессия истекла. Войдите снова.');
      return response;
    }

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

    if (isUnauthorized(response)) {
      handleUnauthorizedResponse();
    }

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
    getConfiguration: (projectId: string) =>
      authedJsonRequest(`/api/projects/${projectId}/configuration`, { method: 'GET' }),
    updateSettings: (projectId: string, body: ProjectSettingsUpdate) =>
      authedJsonRequest(`/api/projects/${projectId}/settings`, { method: 'PATCH', body }),
    updatePolicies: (projectId: string, body: ProjectPoliciesUpdate) =>
      authedJsonRequest(`/api/projects/${projectId}/policies`, { method: 'PATCH', body }),
    updateLimits: (projectId: string, body: ProjectLimitProfileUpdate) =>
      authedJsonRequest(`/api/projects/${projectId}/limits`, { method: 'PATCH', body }),
    listIntegrations: (projectId: string) =>
      authedJsonRequest(`/api/projects/${projectId}/integrations`, { method: 'GET' }),
    upsertIntegration: (projectId: string, body: ProjectIntegrationUpsert) =>
      authedJsonRequest(`/api/projects/${projectId}/integrations`, { method: 'POST', body }),
    listChannels: (projectId: string) =>
      authedJsonRequest(`/api/projects/${projectId}/channels`, { method: 'GET' }),
    upsertChannel: (projectId: string, body: ProjectChannelUpsert) =>
      authedJsonRequest(`/api/projects/${projectId}/channels`, { method: 'POST', body }),
  },
  members: {
    list: async (projectId: string) => {
      return authedJsonRequest(`/api/projects/${projectId}/members`, { method: 'GET' });
    },
    upsert: async (projectId: string, body: { user_id: string; role: string }) => {
      return authedJsonRequest(`/api/projects/${projectId}/members`, { method: 'POST', body });
    },
    remove: async (projectId: string, memberUserId: string) => {
      const token = getSessionToken();
      const headers = new Headers({ 'Content-Type': 'application/json' });
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/members/${memberUserId}`, {
        method: 'DELETE',
        headers,
      });
      if (isUnauthorized(response)) {
        handleUnauthorizedResponse();
      }
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw data;
      }
      return { data: null, response };
    },
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
  },
  chat: {
    sendStream: (projectId: string, message: string, model?: string, visitorId?: string) =>
      fetch(`${API_BASE_URL}/api/chat/projects/${projectId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, model, visitor_id: visitorId } as ChatMessageRequest),
      }),
  },
  knowledge: {
    upload: async (projectId: string, file: File) => {
      const formData = new FormData();
      formData.append('file', file);
      const token = getSessionToken();
      const headers = new Headers();
      if (token) {
        headers.set('Authorization', `Bearer ${token}`);
      }
      const response = await fetch(`${API_BASE_URL}/api/projects/${projectId}/knowledge`, {
        method: 'POST',
        headers,
        body: formData,
      });
      if (isUnauthorized(response)) {
        handleUnauthorizedResponse();
      }
      return response;
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
      if (isUnauthorized(response)) {
        handleUnauthorizedResponse();
      }
      if (!response.ok) throw data;
      return { data, response };
    },
    emailRegister: async (body: { email: string; password: string; full_name?: string }) =>
      authedJsonRequest('/api/auth/email/register', { method: 'POST', body }),
    emailLogin: async (body: { email: string; password: string }) =>
      authedJsonRequest('/api/auth/email/login', { method: 'POST', body }),
    linkEmail: async (body: { email: string; password: string }) =>
      authedJsonRequest('/api/auth/link/email', { method: 'POST', body }),
    requestEmailVerification: async () =>
      authedJsonRequest('/api/auth/email/verification/request', { method: 'POST' }),
    confirmEmailVerification: async (body: { token: string }) =>
      authedJsonRequest('/api/auth/email/verification/confirm', { method: 'POST', body }),
    googleLogin: async (body: { provider_subject: string; email?: string; full_name?: string }) =>
      authedJsonRequest('/api/auth/google/login', { method: 'POST', body }),
    googleLoginWithIdToken: async (body: { id_token: string }) =>
      authedJsonRequest('/api/auth/google/login/id-token', { method: 'POST', body }),
    linkGoogle: async (body: { provider_subject: string; email?: string }) =>
      authedJsonRequest('/api/auth/link/google', { method: 'POST', body }),
    linkGoogleWithIdToken: async (body: { id_token: string }) =>
      authedJsonRequest('/api/auth/link/google/id-token', { method: 'POST', body }),
    changePassword: async (body: { new_password: string; current_password?: string }) =>
      authedJsonRequest('/api/auth/password/change', { method: 'POST', body }),
    requestPasswordReset: async (body: { email: string }) =>
      authedJsonRequest('/api/auth/password/reset/request', { method: 'POST', body }),
    confirmPasswordReset: async (body: { token: string; new_password: string }) =>
      authedJsonRequest('/api/auth/password/reset/confirm', { method: 'POST', body }),
    unlinkMethod: async (provider: 'telegram' | 'email' | 'google') =>
      authedJsonRequest(`/api/auth/methods/${provider}`, { method: 'DELETE' }),
    me: async () => authedJsonRequest('/api/auth/me', { method: 'GET' }),
    methods: async () => authedJsonRequest('/api/auth/methods', { method: 'GET' }),
  },
  clients: {
    list: (params: { project_id: string; limit?: number; offset?: number; search?: string | null }) =>
      client.GET('/api/clients', { params: { query: params } }),
    get: (clientId: string, projectId: string) =>
      client.GET('/api/clients/{client_id}', { params: { path: { client_id: clientId }, query: { project_id: projectId } } }),
  },
});
