import { useState } from 'react';
import { streamFetch } from '@shared/api/client';

const getVisitorId = (projectId: string) => {
  const key = `crm_bot_widget_visitor:${projectId}`;
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const next = window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random()}`;
  window.localStorage.setItem(key, next);
  return next;
};

export const useSendMessage = (projectId: string) => {
  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = async (
    text: string,
    onChunk: (chunk: string) => void,
    onFinish: (fullText: string) => void,
    model?: string
  ) => {
    setIsStreaming(true);
    try {
      await streamFetch(
        `/api/chat/projects/${projectId}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ message: text, model, visitor_id: getVisitorId(projectId) }),
        },
        onChunk,
        onFinish,
        (err) => {
          console.error('Stream error:', err);
          setIsStreaming(false);
        }
      );
    } finally {
      setIsStreaming(false);
    }
  };

  return { sendMessage, isStreaming };
};
