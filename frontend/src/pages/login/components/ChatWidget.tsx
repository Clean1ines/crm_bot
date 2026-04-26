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
    <div className="bg-white rounded-2xl shadow-xl border border-[#E5E2DA] flex flex-col h-[500px]">
      <div className="flex items-center gap-3 p-4 border-b border-[#E5E2DA]">
        <div className="w-8 h-8 rounded-full bg-[#B87333] flex items-center justify-center text-white text-sm font-medium">
          A
        </div>
        <span className="font-medium text-[#1E1E1E]">Ассистент</span>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {staticMessages.map((msg, idx) => (
          <MessageBubble key={idx} role={msg.role} content={msg.content} />
        ))}
      </div>

      <div className="p-4 border-t border-[#E5E2DA] flex gap-2">
        <input
          type="text"
          placeholder="Напишите сообщение..."
          className="flex-1 px-4 py-2 border border-[#E5E2DA] rounded-xl bg-white text-[#1E1E1E] focus:outline-none focus:ring-1 focus:ring-[#B87333]"
          disabled
        />
        <button
          className="px-4 py-2 bg-[#B87333] text-white rounded-xl hover:bg-[#a5662d] transition-colors disabled:opacity-50"
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
