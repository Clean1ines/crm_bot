import React, { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../../app/store';
import { api } from '../../../shared/api/client';
import { useWebSocket } from '../../../shared/lib/websocket';
import type { Message } from '../../../entities/thread/model/types';

interface ChatWindowProps {
  threadId: string | null;
  projectId: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ threadId, projectId }) => {
  const {
    messages,
    addMessage,
    setMessages,
    clearMessages,
    isLoadingMessages,
    setLoadingMessages,
    selectedModel,
    inspectorActiveTab,
    setInspectorActiveTab,
    setThreadState,
    setThreadTimeline,
    setThreadMemory,
  } = useAppStore();

  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [limit] = useState(50);
  const [offset] = useState(0);

  // Load messages when thread changes
  useEffect(() => {
    if (!threadId) {
      clearMessages();
      return;
    }
    const loadMessages = async () => {
      setLoadingMessages(true);
      try {
        const { data, error } = await api.threads.getMessages(threadId, limit, offset);
        if (error) {
          console.error('Failed to load messages', error);
          return;
        }
        if (data && 'messages' in data) {
          setMessages(data.messages as Message[]);
        }
      } catch (err) {
        console.error('Error loading messages', err);
      } finally {
        setLoadingMessages(false);
      }
    };
    loadMessages();
  }, [threadId, limit, offset, setMessages, setLoadingMessages]);

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // WebSocket for real-time updates
  const { isConnected } = useWebSocket({
    threadId,
    onMessage: (msg) => {
      if (msg.type === 'new_message' && msg.message) {
        addMessage(msg.message as Message);
      }
      // Optionally refresh inspector data when relevant events occur
      if (msg.type === 'escalation') {
        // Could trigger reload of thread state, timeline, memory
      }
    },
  });

  const handleSend = async () => {
    if (!threadId || !inputText.trim() || isSending) return;
    setIsSending(true);
    try {
      const { error } = await api.threads.reply(threadId, inputText);
      if (error) {
        console.error('Failed to send reply', error);
      } else {
        setInputText('');
        // Optionally reload messages after a short delay to get the new message
        setTimeout(async () => {
          const { data } = await api.threads.getMessages(threadId, limit, offset);
          if (data && 'messages' in data) {
            setMessages(data.messages as Message[]);
          }
        }, 500);
      }
    } catch (err) {
      console.error('Error sending reply', err);
    } finally {
      setIsSending(false);
    }
  };

  const onMessageClick = (message: Message) => {
    if (message.role === 'assistant' && message.metadata?.explanation) {
      // Open inspector on decision tab and show explanation
      setInspectorActiveTab('decision');
    }
  };

  return (
    <div className="flex flex-col h-full bg-[var(--ios-bg)]">
      {/* Header */}
      <div className="p-3 border-b border-[var(--ios-border)] flex items-center justify-between">
        <div className="font-medium text-[var(--text-main)]">
          {threadId ? `Диалог ${threadId.slice(0, 8)}` : 'Выберите диалог'}
        </div>
        {threadId && (
          <div className="text-xs text-[var(--text-muted)]">
            {isConnected ? '🔵 Онлайн' : '⚪ Офлайн'}
          </div>
        )}
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {isLoadingMessages && <div className="text-center text-[var(--text-muted)]">Загрузка сообщений...</div>}
        {messages.map((msg, idx) => (
          <div
            key={msg.id || idx}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[70%] rounded-lg p-3 cursor-pointer ${
                msg.role === 'user'
                  ? 'bg-blue-500 text-white'
                  : msg.role === 'assistant'
                  ? 'bg-[var(--ios-bg-secondary)] text-[var(--text-main)]'
                  : 'bg-gray-500 text-white'
              }`}
              onClick={() => onMessageClick(msg)}
            >
              <div className="text-sm whitespace-pre-wrap">{msg.content}</div>
              {msg.metadata?.latency_ms && (
                <div className="text-xs opacity-70 mt-1">
                  ⏱️ {msg.metadata.latency_ms}ms | 🧠 {msg.metadata.tokens || 0} токенов
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      {threadId && (
        <div className="p-3 border-t border-[var(--ios-border)]">
          <div className="flex gap-2">
            <textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
              placeholder="Введите ответ менеджера..."
              className="flex-1 resize-none rounded-lg bg-[var(--ios-input-bg)] text-[var(--text-main)] border border-[var(--ios-border)] p-2 focus:outline-none focus:ring-1 focus:ring-blue-500"
              rows={2}
              disabled={isSending}
            />
            <button
              onClick={handleSend}
              disabled={!inputText.trim() || isSending}
              className="px-4 py-2 bg-blue-500 text-white rounded-lg disabled:opacity-50"
            >
              Отправить
            </button>
          </div>
        </div>
      )}
    </div>
  );
};
