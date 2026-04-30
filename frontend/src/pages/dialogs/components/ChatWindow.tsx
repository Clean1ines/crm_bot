import React, { useEffect, useRef, useState } from 'react';
import { ChevronLeft, Info, Send } from 'lucide-react';

import { useAppStore } from '../../../app/store';
import type { Message } from '../../../entities/thread/model/types';
import { threadsApi } from '../../../shared/api/modules/threads';
import { getClientDisplayName } from '../../../shared/lib/clients';
import { getMessagePresentation } from '../../../shared/lib/threadMessages';

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
    selectedThreadClient,
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
  const clientName = getClientDisplayName(selectedThreadClient, 'Клиент');

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

        if (
          data &&
          typeof data === 'object' &&
          'messages' in data &&
          Array.isArray(data.messages)
        ) {
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

    void loadMessages();
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
          if (
            data &&
            typeof data === 'object' &&
            'messages' in data &&
            Array.isArray(data.messages)
          ) {
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
    <div
      className={`flex h-full min-h-0 flex-col bg-transparent ${
        mobile ? '' : 'items-center justify-center'
      }`}
    >
      <div className={`flex min-h-0 w-full flex-1 ${mobile ? '' : 'mx-4 my-4 max-w-3xl'}`}>
        <div
          className={`flex min-h-0 w-full flex-1 flex-col overflow-hidden bg-[var(--surface-elevated)] shadow-card transition-all ${
            mobile ? 'rounded-none' : 'rounded-2xl'
          }`}
        >
          <div className="flex items-center justify-between p-3 shadow-[0_1px_0_var(--divider-soft)] sm:p-4">
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
                  {threadId ? clientName : 'Выберите диалог'}
                </div>
                <div className="text-xs text-[var(--text-muted)]">
                  {threadId ? `Диалог ${threadId.slice(0, 8)}` : 'Сначала выберите диалог'}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              {mobile && (
                <button
                  type="button"
                  onClick={onOpenInspector}
                  disabled={!threadId}
                  className="inline-flex min-h-9 items-center gap-1 rounded-lg bg-[var(--surface-hover)] px-3 py-2 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--accent-primary)] disabled:opacity-50"
                >
                  <Info className="h-4 w-4" />
                  Сводка
                </button>
              )}
            </div>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 sm:space-y-6 sm:p-4">
            {isLoadingMessages && (
              <div className="text-center text-[var(--text-muted)]">Загрузка сообщений...</div>
            )}
            {loadError && (
              <div className="text-center text-sm text-[var(--accent-danger-text)]">
                {loadError}
              </div>
            )}
            {!isLoadingMessages && !loadError && threadId && messages.length === 0 && (
              <div className="text-center text-sm text-[var(--text-muted)]">
                Сообщений пока нет
              </div>
            )}
            {messages.map((msg, idx) => {
              const presentation = getMessagePresentation(msg, selectedThreadClient);
              let bubbleClasses = '';

              if (msg.role === 'user') {
                bubbleClasses =
                  'bg-[var(--surface-raised)] shadow-sm text-[var(--text-primary)]';
              } else if (msg.role === 'assistant') {
                bubbleClasses = 'bg-[var(--surface-secondary)] text-[var(--text-primary)]';
              } else if (msg.role === 'manager') {
                bubbleClasses =
                  'bg-[var(--accent-muted)] text-[var(--accent-primary)] shadow-sm';
              } else {
                bubbleClasses = 'bg-[var(--surface-secondary)] text-[var(--text-primary)]';
              }

              return (
                <div
                  key={msg.id || idx}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] cursor-pointer rounded-xl p-3 transition-all hover:shadow-sm sm:max-w-[70%] ${bubbleClasses}`}
                    onClick={() => onMessageClick(msg)}
                  >
                    <div className="mb-1 text-xs font-medium opacity-80">
                      {presentation.label}
                    </div>
                    <div className="whitespace-pre-wrap text-sm leading-relaxed">
                      {presentation.content}
                    </div>
                    {msg.metadata?.latency_ms && (
                      <div className="mt-1 text-xs text-[var(--text-muted)]">
                        Latency: {msg.metadata.latency_ms}ms | Tokens:{' '}
                        {msg.metadata.tokens || 0}
                      </div>
                    )}
                    {msg.metadata?.explanation && (
                      <div className="mt-1 text-xs text-[var(--accent-primary)]">
                        Обоснование: {msg.metadata.explanation}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
            <div ref={messagesEndRef} />
          </div>

          {threadId && (
            <div className="p-3 shadow-[0_-1px_0_var(--divider-soft)] sm:p-4">
              <div className="flex gap-2">
                <textarea
                  value={inputText}
                  onChange={(e) => setInputText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault();
                      void handleSend();
                    }
                  }}
                  placeholder="Введите ответ..."
                  className="min-h-11 flex-1 resize-none rounded-lg bg-[var(--control-bg)] p-2 text-sm leading-relaxed text-[var(--text-primary)] placeholder:text-[var(--text-muted)] transition-all focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/20"
                  rows={mobile ? 1 : 2}
                  disabled={isSending}
                />
                <button
                  onClick={() => void handleSend()}
                  disabled={!inputText.trim() || isSending}
                  className="flex min-h-11 items-center gap-2 rounded-lg bg-[var(--accent-primary)] px-3 py-2 text-sm font-medium text-white transition-all hover:bg-[var(--accent-hover)] hover:shadow-sm disabled:opacity-50 sm:px-4"
                >
                  <Send className="h-4 w-4" />
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
