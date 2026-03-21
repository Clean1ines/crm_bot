import { useState, useCallback } from 'react';

interface AnalyzeRequestBody {
  prompt: string;
  mode?: string;
  model?: string;
  project_id?: string;
}

// Функция для получения токена из sessionStorage
const getSessionToken = (): string | null => {
  return sessionStorage.getItem('mrak_session_token');
};

export const useStreaming = () => {
  const [isStreaming, setIsStreaming] = useState(false);

  const startStream = useCallback(
    async (
      body: AnalyzeRequestBody,
      callbacks: {
        onChunk: (chunk: string) => void;
        onFinish: (fullText: string) => void;
        onError?: (err: unknown) => void;
      }
    ) => {
      setIsStreaming(true);
      try {
        // Получаем токен и добавляем в заголовки
        const token = getSessionToken();
        const headers: Record<string, string> = {
          'Content-Type': 'application/json',
        };
        if (token) {
          headers['Authorization'] = `Bearer ${token}`;
        }

        const response = await fetch('/api/analyze', {
          method: 'POST',
          headers,
          body: JSON.stringify(body),
        });

        if (!response.ok) {
          const errorText = await response.text().catch(() => 'Unknown error');
          throw new Error(`HTTP ${response.status}: ${errorText}`);
        }

        if (!response.body) {
          throw new Error('Response body is null');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          fullText += chunk;
          callbacks.onChunk(chunk);
        }

        callbacks.onFinish(fullText);
      } catch (err) {
        if (callbacks.onError) callbacks.onError(err);
        else console.error(err);
      } finally {
        setIsStreaming(false);
      }
    },
    []
  );

  return { isStreaming, startStream };
};
