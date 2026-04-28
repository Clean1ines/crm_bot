import React from 'react';

interface MessageBubbleProps {
  role: 'user' | 'assistant';
  content: string;
}

export const MessageBubble: React.FC<MessageBubbleProps> = ({ role, content }) => {
  const isUser = role === 'user';
  return (
    <div className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm leading-relaxed ${
          isUser
            ? 'bg-[var(--surface-raised)] text-[var(--text-primary)] shadow-[var(--shadow-sm)]'
            : 'bg-[var(--surface-secondary)] text-[var(--text-primary)]'
        }`}
      >
        {content}
      </div>
    </div>
  );
};
