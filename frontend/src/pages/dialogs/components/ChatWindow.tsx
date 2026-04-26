import React, { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../../app/store';
import { threadsApi } from '../../../shared/api/modules/threads';
import type { Message } from '../../../entities/thread/model/types';
import { Send } from 'lucide-react';

interface ChatWindowProps {
  threadId: string | null;
  projectId: string;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({ threadId }) => {
  const {
    messages,
    setMessages,
    clearMessages,
    isLoadingMessages,
    setLoadingMessages,
    setInspectorActiveTab,
  } = useAppStore();

  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [limit] = useState(50);
  const [offset] = useState(0);

  useEffect(() => {
    if (!threadId) {
      clearMessages();
      setLoadingMessages(false);
      setLoadError(null);
      return;
    }
    const loadMessages = async () => {
      setLoadingMessages(true);
      setLoadError(null);
      try {
        const { data, error } = await threadsApi.getMessages(threadId, limit, offset);
        if (error) {
          console.error('Failed to load messages', error);
          setLoadError('Не удалось загрузить сообщения');
          setMessages([]);
          return;
        }
        if (data && typeof data === 'object' && 'messages' in data && Array.isArray(data.messages)) {
          setMessages(data.messages as Message[]);
        } else {
          setMessages([]);
        }
      } catch (err) {
        console.error('Error loading messages', err);
        setLoadError('Не удалось загрузить сообщения');
        setMessages([]);
      } finally {
        setLoadingMessages(false);
      }
    };
    loadMessages();
  }, [threadId, limit, offset, setMessages, setLoadingMessages, clearMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = async () => {
    if (!threadId || !inputText.trim() || isSending) return;
    setIsSending(true);
    try {
      const { error } = await threadsApi.reply(threadId, inputText);
      if (error) {
        console.error('Failed to send reply', error);
      } else {
        setInputText('');
        setTimeout(async () => {
          const { data } = await threadsApi.getMessages(threadId, limit, offset);
          if (data && typeof data === 'object' && 'messages' in data && Array.isArray(data.messages)) {
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
      setInspectorActiveTab('decision');
    }
  };


  return (
    <div className="flex flex-col h-full items-center justify-center bg-transparent">
      <div className="w-full max-w-3xl mx-4 my-4">
        <div className="bg-white rounded-xl shadow-card overflow-hidden transition-all">
          <div className="p-4 flex items-center justify-between">
            <div className="font-medium text-[var(--text-primary)]">
              {threadId ? `Диалог ${threadId.slice(0, 8)}` : 'Выберите диалог'}
            </div>
            <div className="flex items-center gap-2">
              {/* WebSocket индикатор удалён */}
            </div>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-6 max-h-[calc(100vh-180px)]">
            {isLoadingMessages && <div className="text-center text-[var(--text-muted)]">Загрузка сообщений...</div>}
            {loadError && <div className="text-center text-sm text-red-600">{loadError}</div>}
            {!isLoadingMessages && !loadError && threadId && (!Array.isArray(messages) || messages.length === 0) && (
              <div className="text-center text-sm text-[var(--text-muted)]">Сообщений пока нет</div>
            )}
            {(Array.isArray(messages) ? messages : []).map((msg, idx) => {
              let bubbleClasses = '';
              if (msg.role === 'user') {
                bubbleClasses = 'bg-white shadow-sm text-[var(--text-primary)]';
              } else if (msg.role === 'assistant') {
                bubbleClasses = 'bg-[var(--surface-secondary)] text-[var(--text-primary)]';
              } else if (msg.role === 'manager') {
                bubbleClasses = 'bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-sm';
              } else {
                bubbleClasses = 'bg-[var(--surface-secondary)] text-[var(--text-primary)]';
              }
              return (
                <div
                  key={msg.id || idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[70%] rounded-lg p-3 cursor-pointer ${bubbleClasses} transition-all hover:shadow-sm`}
                    onClick={() => onMessageClick(msg)}
                  >
                    <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                    {msg.metadata?.latency_ms && (
                      <div className="text-xs text-[var(--text-muted)] mt-1">
                        ⏱️ {msg.metadata.latency_ms}ms | 🧠 {msg.metadata.tokens || 0} токенов
                      </div>
                    )}
                    {msg.metadata?.explanation && (
                      <div className="text-xs text-[var(--accent-primary)] mt-1">
                        📖 {msg.metadata.explanation}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {threadId && (
            <div className="p-4">
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
                  placeholder="Введите ответ..."
                  className="flex-1 resize-none rounded-lg bg-[var(--surface-secondary)] text-[var(--text-primary)] p-2 focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] transition-all"
                  rows={2}
                  disabled={isSending}
                />
                <button
                  onClick={handleSend}
                  disabled={!inputText.trim() || isSending}
                  className="px-4 py-2 bg-[var(--accent-primary)] text-white rounded-lg disabled:opacity-50 hover:bg-[var(--accent-hover)] transition-all hover:shadow-sm flex items-center gap-2"
                >
                  <Send className="w-4 h-4" />
                  Отправить
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
