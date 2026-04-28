import React, { useState, useRef, useEffect } from 'react';
import { useSendMessage } from '@features/chat/send-message/useSendMessage';

interface ChatCanvasProps {
  projectId: string;
  model?: string;
  onModelChange?: (model: string) => void;
  availableModels?: { id: string; name: string }[];
}

export const ChatCanvas: React.FC<ChatCanvasProps> = ({
  projectId,
  model,
  onModelChange,
  availableModels = [],
}) => {
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [input, setInput] = useState('');
  const { sendMessage, isStreaming } = useSendMessage(projectId);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return;
    const userMessage = input.trim();
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setInput('');

    let assistantContent = '';
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    await sendMessage(
      userMessage,
      (chunk) => {
        assistantContent += chunk;
        setMessages(prev => {
          const newMessages = [...prev];
          const lastIndex = newMessages.length - 1;
          if (newMessages[lastIndex]?.role === 'assistant') {
            newMessages[lastIndex] = { ...newMessages[lastIndex], content: assistantContent };
          }
          return newMessages;
        });
      },
      () => {
        // окончательный текст уже установлен
      },
      model
    );
  };

  return (
    <div className="flex h-full flex-col bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed shadow-[var(--shadow-sm)] ${msg.role === 'user' ? 'bg-[var(--accent-primary)] text-white' : 'bg-[var(--surface-secondary)] text-[var(--text-primary)]'}`}>
              {msg.content || (msg.role === 'assistant' && isStreaming && '...')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="flex gap-2 p-4 shadow-[0_-1px_0_var(--divider-soft)]">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSend()}
          className="min-h-11 flex-1 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          placeholder="Введите сообщение..."
          disabled={isStreaming}
        />
        {availableModels.length > 0 && onModelChange && (
          <select
            value={model || ''}
            onChange={(e) => onModelChange(e.target.value)}
            className="min-h-11 rounded-lg bg-[var(--control-bg)] px-3 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          >
            <option value="">Model</option>
            {availableModels.map(m => (
              <option key={m.id} value={m.id}>{m.name}</option>
            ))}
          </select>
        )}
        <button
          onClick={handleSend}
          disabled={isStreaming}
          className="min-h-11 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50"
        >
          Отправить
        </button>
      </div>
    </div>
  );
};