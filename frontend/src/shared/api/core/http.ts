import { API_BASE_URL } from './config';
import { getSessionToken, handleUnauthorizedResponse, isUnauthorized } from './session';

export type ApiJsonResult<TResponse> = {
  data: TResponse;
  response: Response;
};

export const createAuthHeaders = (contentType: string | null = 'application/json'): Headers => {
  const headers = new Headers();

  if (contentType) {
    headers.set('Content-Type', contentType);
  }

  const token = getSessionToken();
  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }

  return headers;
};

export async function authedJsonRequest<TResponse = unknown, TBody = unknown>(
  path: string,
  options: { method: string; body?: TBody },
): Promise<ApiJsonResult<TResponse>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: options.method,
    headers: createAuthHeaders('application/json'),
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
  });

  const data = await response.json().catch(() => null) as TResponse;

  if (isUnauthorized(response)) {
    handleUnauthorizedResponse();
  }

  if (!response.ok) {
    throw data;
  }

  return { data, response };
}

export async function authedDeleteRequest(
  path: string,
): Promise<ApiJsonResult<null>> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'DELETE',
    headers: createAuthHeaders('application/json'),
  });

  if (isUnauthorized(response)) {
    handleUnauthorizedResponse();
  }

  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw data;
  }

  return { data: null, response };
}

export async function authedMultipartRequest(
  path: string,
  formData: FormData,
): Promise<Response> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: createAuthHeaders(null),
    body: formData,
  });

  if (isUnauthorized(response)) {
    handleUnauthorizedResponse();
  }

  return response;
}
