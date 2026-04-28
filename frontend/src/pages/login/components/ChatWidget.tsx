import React from 'react';
import { MessageBubble } from './MessageBubble';

type ChatMessage = {
  role: 'user' | 'assistant';
  content: string;
};

const staticMessages: ChatMessage[] = [
  { role: 'user', content: 'Привет! Чем вы занимаетесь?' },
  { role: 'assistant', content: 'Здравствуйте! Мы создаём ассистентов для бизнеса' },
  { role: 'user', content: 'Сколько это стоит?' },
  { role: 'assistant', content: 'Стоимость зависит от ваших задач. Могу рассказать подробнее!' },
];

export const ChatWidget: React.FC = () => {
  return (
    <div className="flex h-[500px] flex-col overflow-hidden rounded-2xl bg-[var(--surface-elevated)] shadow-[var(--shadow-card)]">
      <div className="flex items-center gap-3 p-4 shadow-[0_1px_0_var(--divider-soft)]">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-[var(--accent-primary)] text-sm font-medium text-white shadow-[var(--shadow-sm)]">
          A
        </div>
        <span className="text-sm font-medium text-[var(--text-primary)]">Ассистент</span>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {staticMessages.map((msg, idx) => (
          <MessageBubble key={idx} role={msg.role} content={msg.content} />
        ))}
      </div>

      <div className="flex gap-2 p-4 shadow-[0_-1px_0_var(--divider-soft)]">
        <input
          type="text"
          placeholder="Напишите сообщение..."
          className="min-h-10 flex-1 rounded-lg bg-[var(--control-bg)] px-4 py-2 text-sm text-[var(--text-primary)] shadow-[var(--shadow-sm)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          disabled
        />
        <button
          className="min-h-10 rounded-lg bg-[var(--accent-primary)] px-4 py-2 text-white transition-colors hover:bg-[var(--accent-hover)] disabled:opacity-50"
          disabled
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
          </svg>
        </button>
      </div>
    </div>
  );
};
