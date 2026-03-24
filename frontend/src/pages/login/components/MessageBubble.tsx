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
        className={`max-w-[80%] px-4 py-2 rounded-2xl ${
          isUser
            ? 'bg-white text-[#1E1E1E] shadow-sm'
            : 'bg-[#F1ECE5] text-[#1E1E1E]'
        }`}
      >
        {content}
      </div>
    </div>
  );
};
