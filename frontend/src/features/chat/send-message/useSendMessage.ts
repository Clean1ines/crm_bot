import { useState } from 'react';
import { useAppStore } from '@/app/store';
import { useProjectStore } from '@entities/project';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useStreaming } from '@/shared/api/streaming';
import { streamFetch } from '@shared/api/client';

export const useSendMessage = (executionId?: string) => {
  const [inputValue, setInputValue] = useState('');
  const { showNotification } = useNotification();
  const addMessage = useAppStore((s) => s.addMessage);
  const currentProjectId = useProjectStore((s) => s.currentProjectId);
  const selectedModel = useAppStore((s) => s.selectedModel);
  const mode = '01_CORE';

  const { isStreaming: isOldStreaming, startStream } = useStreaming();

  const [isStreaming, setIsStreaming] = useState(false);

  const sendMessage = async (text: string) => {
    if (!currentProjectId) {
      showNotification('Сначала выберите проект', 'error');
      return;
    }
    if (!text.trim()) return;

    addMessage({ role: 'user', content: text, timestamp: Date.now() });
    setInputValue('');

    if (executionId) {
      setIsStreaming(true);
      try {
        const body = { message: text, model: selectedModel || undefined };
        await streamFetch(
          `/api/executions/${executionId}/messages`,
          {
            method: 'POST',
            body: JSON.stringify(body),
          },
          () => {}, // chunk not needed
          (fullText) => {
            addMessage({ role: 'assistant', content: fullText, timestamp: Date.now() });
            setIsStreaming(false);
          },
          (err) => {
            showNotification('Ошибка: ' + err.message, 'error');
            setIsStreaming(false);
          }
        );
      } catch {
        showNotification('Ошибка при отправке сообщения', 'error');
        setIsStreaming(false);
      }
    } else {
      // Fallback to old streaming (project-level)
      await startStream(
        { prompt: text, mode, model: selectedModel || undefined, project_id: currentProjectId },
        {
          onChunk: () => {},
          onFinish: (fullText) => {
            addMessage({ role: 'assistant', content: fullText, timestamp: Date.now() });
          },
          onError: (err) => {
            const message = err instanceof Error ? err.message : String(err);
            showNotification('Ошибка: ' + message, 'error');
          },
        }
      );
    }
  };

  return { sendMessage, isStreaming: isStreaming || isOldStreaming, inputValue, setInputValue };
};