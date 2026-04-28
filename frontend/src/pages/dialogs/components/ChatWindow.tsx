import React, { useEffect, useRef, useState } from 'react';
import { useAppStore } from '../../../app/store';
import { threadsApi } from '../../../shared/api/modules/threads';
import type { Message } from '../../../entities/thread/model/types';
import { ChevronLeft, Info, Send } from 'lucide-react';

interface ChatWindowProps {
  threadId: string | null;
  projectId: string;
  mobile?: boolean;
  onBack?: () => void;
  onOpenInspector?: () => void;
}

export const ChatWindow: React.FC<ChatWindowProps> = ({
  threadId,
  mobile = false,
  onBack,
  onOpenInspector,
}) => {
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
    <div className={`flex h-full min-h-0 flex-col bg-transparent ${mobile ? '' : 'items-center justify-center'}`}>
      <div className={`flex min-h-0 w-full flex-1 ${mobile ? '' : 'max-w-3xl mx-4 my-4'}`}>
        <div className={`flex min-h-0 w-full flex-1 flex-col overflow-hidden border border-[var(--border-subtle)] bg-[var(--surface-card)] shadow-card transition-all ${mobile ? 'border-x-0 border-t-0 rounded-none' : 'rounded-xl'}`}>
          <div className="flex items-center justify-between border-b border-[var(--border-subtle)] p-3 sm:p-4">
            <div className="flex min-w-0 items-center gap-2">
              {mobile && (
                <button
                  type="button"
                  onClick={onBack}
                  className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-[var(--text-secondary)] transition-colors hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]"
                  aria-label="Назад к списку диалогов"
                >
                  <ChevronLeft className="h-5 w-5" />
                </button>
              )}
              <div className="min-w-0">
                <div className="truncate font-medium text-[var(--text-primary)]">
                  {threadId ? `Диалог ${threadId.slice(0, 8)}` : 'Выберите диалог'}
                </div>
                {mobile && (
                  <div className="text-xs text-[var(--text-muted)]">
                    {threadId ? 'Переписка с клиентом' : 'Сначала выберите диалог'}
                  </div>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              {mobile && (
                <button
                  type="button"
                  onClick={onOpenInspector}
                  disabled={!threadId}
                  className="inline-flex items-center gap-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:text-[var(--accent-primary)] disabled:opacity-50"
                >
                  <Info className="h-4 w-4" />
                  Сводка
                </button>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-3 space-y-4 sm:p-4 sm:space-y-6">
            {isLoadingMessages && <div className="text-center text-[var(--text-muted)]">Загрузка сообщений...</div>}
            {loadError && <div className="text-center text-sm text-red-600">{loadError}</div>}
            {!isLoadingMessages && !loadError && threadId && (!Array.isArray(messages) || messages.length === 0) && (
              <div className="text-center text-sm text-[var(--text-muted)]">Сообщений пока нет</div>
            )}
            {(Array.isArray(messages) ? messages : []).map((msg, idx) => {
              let bubbleClasses = '';
              if (msg.role === 'user') {
                bubbleClasses = 'bg-[var(--surface-card)] border border-[var(--border-subtle)] shadow-sm text-[var(--text-primary)]';
              } else if (msg.role === 'assistant') {
                bubbleClasses = 'bg-[var(--surface-secondary)] border border-[var(--border-subtle)] text-[var(--text-primary)]';
              } else if (msg.role === 'manager') {
                bubbleClasses = 'bg-[var(--accent-muted)] border border-[var(--border-subtle)] text-[var(--accent-primary)] shadow-sm';
              } else {
                bubbleClasses = 'bg-[var(--surface-secondary)] border border-[var(--border-subtle)] text-[var(--text-primary)]';
              }
              return (
                <div
                  key={msg.id || idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-lg p-3 cursor-pointer ${bubbleClasses} transition-all hover:shadow-sm sm:max-w-[70%]`}
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
            <div className="border-t border-[var(--border-subtle)] p-3 sm:p-4">
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
                  className="min-h-[44px] flex-1 resize-none rounded-lg border border-[var(--border-subtle)] bg-[var(--surface-secondary)] p-2 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)] transition-all"
                  rows={mobile ? 1 : 2}
                  disabled={isSending}
                />
                <button
                  onClick={handleSend}
                  disabled={!inputText.trim() || isSending}
                  className="flex items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-white transition-all hover:bg-[var(--accent-hover)] hover:shadow-sm disabled:opacity-50 sm:px-4"
                >
                  <Send className="w-4 h-4" />
                  <span className="hidden sm:inline">Отправить</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
