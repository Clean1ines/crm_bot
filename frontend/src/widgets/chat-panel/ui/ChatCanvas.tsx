import React, { useRef, useEffect } from 'react'; // удалён неиспользуемый useState
import { useAppStore, ChatMessageData } from '@/app/store';
import { useProjectStore } from '@entities/project';
import { useNotification } from '@/shared/lib/notification/useNotifications';
import { useMediaQuery } from '@/shared/lib/hooks/useMediaQuery';
import { ChatMessage } from '@/entities/chat/ui/ChatMessage';
import { useSendMessage } from '@/features/chat/send-message/useSendMessage';
import { useExecutionMessages } from '@entities/chat/api/useExecutionMessages';
import {
  TEXTAREA_LINE_HEIGHT,
  TEXTAREA_MAX_ROWS_DESKTOP,
  TEXTAREA_MAX_ROWS_MOBILE,
  TEXTAREA_MIN_HEIGHT,
} from '@/shared/lib/constants/canvas';

const ExpandingTextarea: React.FC<{
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
  onSend: () => void;
  placeholder: string;
  isMobile: boolean;
}> = ({ value, onChange, onKeyDown, onSend, placeholder, isMobile }) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const lineHeight = TEXTAREA_LINE_HEIGHT;
  const maxRows = isMobile ? TEXTAREA_MAX_ROWS_MOBILE : TEXTAREA_MAX_ROWS_DESKTOP;
  const maxHeight = lineHeight * maxRows;

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      const newHeight = Math.min(textareaRef.current.scrollHeight, maxHeight);
      textareaRef.current.style.height = `${newHeight}px`;
      textareaRef.current.style.overflowY = textareaRef.current.scrollHeight > maxHeight ? 'auto' : 'hidden';
    }
  }, [value, maxHeight]);

  return (
    <div className={`relative w-full ${isMobile ? 'max-w-full' : 'max-w-[40%]'} mx-auto`}>
      <textarea
        ref={textareaRef}
        value={value}
        onChange={onChange}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        rows={1}
        className="w-full bg-[var(--ios-glass)] border border-[var(--ios-border)] rounded-lg px-4 py-3 pr-16 text-sm text-[var(--text-main)] outline-none focus:border-[var(--bronze-base)] resize-none overflow-hidden"
        style={{ minHeight: `${TEXTAREA_MIN_HEIGHT}px` }}
      />
      <button
        onClick={onSend}
        disabled={!value.trim()}
        className="absolute bottom-2 right-2 px-3 py-1 text-xs font-semibold rounded bg-[var(--bronze-base)] text-black hover:bg-[var(--bronze-bright)] transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
      >
        Send
      </button>
    </div>
  );
};

interface ChatCanvasProps {
  executionId?: string;
}

export const ChatCanvas: React.FC<ChatCanvasProps> = ({ executionId }) => {
  const messages = useAppStore(s => s.messages);
  const currentProjectId = useProjectStore(s => s.currentProjectId);
  const showNotification = useNotification().showNotification;
  const scrollRef = useRef<HTMLDivElement>(null);
  const isMobile = useMediaQuery('(max-width: 768px)');

  // Загружаем историю сообщений, если передан executionId
  const { isLoading, error } = useExecutionMessages(executionId || null);

  // Параметризованный хук отправки сообщений
  const { sendMessage, isStreaming, inputValue, setInputValue } = useSendMessage(executionId);

  useEffect(() => {
    if (error) {
      showNotification('Failed to load messages', 'error');
    }
  }, [error, showNotification]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isStreaming]);

  const handleSend = async () => {
    if (!inputValue.trim()) return;
    await sendMessage(inputValue);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const showMrakBrand = messages.length === 0 && !isStreaming && !isLoading;

  return (
    <div className="flex-1 flex flex-col h-full">
      <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-4 p-4 relative">
        {isLoading && (
          <div className="text-center text-gray-500 py-4">Loading conversation...</div>
        )}
        {showMrakBrand && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-6xl font-bold text-[var(--bronze-base)] opacity-[0.03] select-none">
              MADE IN MRAK
            </div>
          </div>
        )}
        {messages.map((msg: ChatMessageData, idx: number) => (
          <ChatMessage key={idx} role={msg.role} content={msg.content} />
        ))}
        {isStreaming && (
          <ChatMessage role="assistant" content="..." isStreaming />
        )}
      </div>
      <div className="p-4 border-t border-[var(--ios-border)] bg-[var(--ios-glass-dark)]">
        <ExpandingTextarea
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onKeyDown={handleKeyDown}
          onSend={handleSend}
          placeholder={currentProjectId ? "Type your message..." : "Select a project first"}
          isMobile={isMobile}
        />
      </div>
    </div>
  );
};