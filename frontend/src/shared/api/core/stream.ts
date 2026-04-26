import { API_BASE_URL } from './config';
import { getErrorMessage } from './errors';
import { createAuthHeaders } from './http';
import { handleUnauthorizedResponse, isUnauthorized } from './session';

export async function streamFetch(
  url: string,
  options: RequestInit,
  onChunk: (chunk: string) => void,
  onFinish: (fullText: string) => void,
  onError: (err: Error) => void,
) {
  const fullUrl = url.startsWith('http') ? url : `${API_BASE_URL}${url}`;

  try {
    const headers = createAuthHeaders('application/json');

    new Headers(options.headers || {}).forEach((value, key) => {
      headers.set(key, value);
    });

    const response = await fetch(fullUrl, {
      ...options,
      headers,
    });

    if (isUnauthorized(response)) {
      handleUnauthorizedResponse();
    }

    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(getErrorMessage(errData) || `HTTP ${response.status}`);
    }

    const reader = response.body?.getReader();
    if (!reader) {
      throw new Error('No response body');
    }

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
  } catch (error) {
    onError(error instanceof Error ? error : new Error(String(error)));
  }
}
