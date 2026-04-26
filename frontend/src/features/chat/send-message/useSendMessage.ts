import { useState } from 'react';
import { streamFetch } from '@shared/api/core/stream';
import { getOrCreateVisitorId } from '@shared/lib/visitorStorage';

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
          body: JSON.stringify({ message: text, model, visitor_id: getOrCreateVisitorId(projectId) }),
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
