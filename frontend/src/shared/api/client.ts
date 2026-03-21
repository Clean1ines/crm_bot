import createClient from 'openapi-fetch';
import toast from 'react-hot-toast';
import type { paths, components } from './generated/schema';
import { createTimeoutMiddleware } from './fetchWithTimeout';

// Extend Window interface for deduplication
declare global {
  interface Window {
    __lastToast: string | null;
  }
}

// ---------- Types ----------
export type ProjectResponse = components['schemas']['ProjectResponse'];
type ProjectCreate = components['schemas']['ProjectCreate'];
type RunCreate = components['schemas']['RunCreate'];               // ADDED
type NodeExecutionCreate = components['schemas']['NodeExecutionCreate']; // ADDED
type MessageRequest = components['schemas']['MessageRequest'];     // ADDED
export type ValidateExecutionResponse = components['schemas']['ValidateExecutionResponse']; // ADDED и экспортирован

// ---------- Token Management ----------
const getSessionToken = (): string | null => {
  return sessionStorage.getItem('mrak_session_token');
};

const setSessionToken = (token: string): void => {
  sessionStorage.setItem('mrak_session_token', token);
};

const clearSessionToken = (): void => {
  sessionStorage.removeItem('mrak_session_token');
};

// ---------- Error Message Extraction ----------
export const getErrorMessage = (error: unknown): string => {
  if (error && typeof error === 'object') {
    if ('error' in error && typeof error.error === 'string') {
      return error.error;
    }
    if ('detail' in error && Array.isArray(error.detail)) {
      const details = error.detail as Array<{ msg?: string }>;
      return details.map(d => d.msg).filter(Boolean).join(', ');
    }
    if ('message' in error && typeof error.message === 'string') {
      return error.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return 'Произошла неизвестная ошибка';
};

// ---------- Toast Helpers ----------
const showErrorToast = (message: string): void => {
  const key = `error-${message}`;
  if (window.__lastToast === key) return;
  window.__lastToast = key;
  setTimeout(() => {
    window.__lastToast = null;
  }, 1000);
  toast.error(message);
};

// ---------- API Client Setup ----------
export const client = createClient<paths>({
  baseUrl: '',
  headers: {
    'Content-Type': 'application/json',
  },
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

// Response middleware: handles errors and 401
client.use({
  onResponse({ response }) {
    if (!response.ok) {
      if (response.status === 401) {
        clearSessionToken();
        window.location.href = '/login';
        return new Response(JSON.stringify({ error: 'Сессия истекла' }), {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        });
      }

      return response
        .clone()
        .json()
        .then((errData) => {
          const message = getErrorMessage(errData);
          showErrorToast(message);
          return response;
        })
        .catch(() => {
          let message: string;
          if (response.status >= 500 && response.status < 600) {
            message = 'Сервер временно недоступен. Пожалуйста, попробуйте позже.';
          } else {
            message = `Ошибка ${response.status}: ${response.statusText}`;
          }
          showErrorToast(message);
          return response;
        });
    }
    return response;
  },
});

client.use(createTimeoutMiddleware(30000));

// ---------- Helper for streaming requests ----------
async function streamFetch(
  url: string,
  options: RequestInit,
  onChunk: (chunk: string) => void,
  onFinish: (fullText: string) => void,
  onError: (err: Error) => void
) {
  try {
    const token = getSessionToken();
    const headers = new Headers(options.headers || {});
    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
    headers.set('Content-Type', 'application/json');

    const response = await fetch(url, {
      ...options,
      headers,
    });

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
export const api = {
  projects: {
    list: () => client.GET('/api/projects'),
    create: (body: ProjectCreate) => client.POST('/api/projects', { body }),
    update: (projectId: string, body: ProjectCreate) =>
      client.PUT('/api/projects/{project_id}', {
        params: { path: { project_id: projectId } },
        body,
      }),
    delete: (projectId: string) =>
      client.DELETE('/api/projects/{project_id}', { params: { path: { project_id: projectId } } }),
  },
  models: {
    list: () => client.GET('/api/models'),
  },
  modes: {
    list: () => client.GET('/api/modes'),
  },
  artifactTypes: {
    list: () => client.GET('/api/artifact-types'),
  },
  artifacts: {
    list: (projectId: string) =>
      client.GET('/api/projects/{project_id}/artifacts', { params: { path: { project_id: projectId } } }),
  },
  messages: {
    list: (projectId: string) =>
      client.GET('/api/projects/{project_id}/messages', { params: { path: { project_id: projectId } } }),
  },
  workflows: {
    list: (projectId?: string) =>
      client.GET('/api/workflows', {
        params: projectId ? { query: { project_id: projectId } } : undefined,
      }),
    get: (workflowId: string) =>
      client.GET('/api/workflows/{workflow_id}', {
        params: { path: { workflow_id: workflowId } },
      }),
    create: (data: components['schemas']['WorkflowCreate'] & { project_id: string }) =>
      client.POST('/api/workflows', { body: data }),
    update: (workflowId: string, data: components['schemas']['WorkflowUpdate']) =>
      client.PUT('/api/workflows/{workflow_id}', {
        params: { path: { workflow_id: workflowId } },
        body: data,
      }),
    delete: (workflowId: string) =>
      client.DELETE('/api/workflows/{workflow_id}', {
        params: { path: { workflow_id: workflowId } },
      }),
    nodes: {
      create: (workflowId: string, data: components['schemas']['WorkflowNodeCreate']) =>
        client.POST('/api/workflows/{workflow_id}/nodes', {
          params: { path: { workflow_id: workflowId } },
          body: data,
        }),
      update: (nodeRecordId: string, data: components['schemas']['WorkflowNodeUpdate']) =>
        client.PUT('/api/workflows/nodes/{node_record_id}', {
          params: { path: { node_record_id: nodeRecordId } },
          body: data,
        }),
      delete: (nodeRecordId: string) =>
        client.DELETE('/api/workflows/nodes/{node_record_id}', {
          params: { path: { node_record_id: nodeRecordId } },
        }),
    },
    edges: {
      create: (workflowId: string, data: components['schemas']['WorkflowEdgeCreate']) =>
        client.POST('/api/workflows/{workflow_id}/edges', {
          params: { path: { workflow_id: workflowId } },
          body: data,
        }),
      delete: (edgeRecordId: string) =>
        client.DELETE('/api/workflows/edges/{edge_record_id}', {
          params: { path: { edge_record_id: edgeRecordId } },
        }),
    },
  },
  // ==================== ADDED: runs and executions ====================
  runs: {
    create: (body: RunCreate) =>
      client.POST('/api/runs', { body }),
    get: (runId: string) =>
      client.GET('/api/runs/{run_id}', { params: { path: { run_id: runId } } }),
    executeNode: (runId: string, nodeId: string, body: NodeExecutionCreate) =>
      client.POST('/api/runs/{run_id}/nodes/{node_id}/execute', {
        params: { path: { run_id: runId, node_id: nodeId } },
        body,
      }),
    freeze: (runId: string) =>
      client.POST('/api/runs/{run_id}/freeze', { params: { path: { run_id: runId } } }),
    archive: (runId: string) =>
      client.POST('/api/runs/{run_id}/archive', { params: { path: { run_id: runId } } }),
  },
  executions: {
    getMessages: (executionId: string) =>
      client.GET('/api/executions/{exec_id}/messages', { params: { path: { exec_id: executionId } } }),
    // Streaming message endpoint – returns a raw Response for use with streamFetch
    sendMessageStream: (executionId: string, body: MessageRequest) =>
      fetch(`/api/executions/${executionId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    validate: (executionId: string) =>
      client.POST('/api/executions/{exec_id}/validate', {
        params: { path: { exec_id: executionId } },
        // body удалён, так как метод не требует тела
      }),
  },
  auth: {
    login: async (body: { master_key: string }) => {
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const data = await res.json();
        if (!res.ok) {
          const message = getErrorMessage(data) || `Ошибка входа (${res.status})`;
          showErrorToast(message);
          throw new Error(message);
        }
        if (data.session_token) {
          setSessionToken(data.session_token);
        }
        return data;
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Ошибка соединения с сервером';
        showErrorToast(message);
        throw error;
      }
    },
    logout: async () => {
      try {
        const res = await fetch('/api/auth/logout', { method: 'POST' });
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const message = getErrorMessage(data) || `Ошибка выхода (${res.status})`;
          showErrorToast(message);
        }
        clearSessionToken();
        return await res.json().catch(() => ({}));
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Ошибка соединения с сервером';
        showErrorToast(message);
        clearSessionToken();
        throw error;
      }
    },
    session: async () => {
      return client.GET('/api/auth/session', {});
    },
  },
};

// Re-export stream helper for use in hooks
export { streamFetch };