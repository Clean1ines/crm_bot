import React, { useEffect, useRef } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

interface ChatMessageProps {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ role, content, isStreaming }) => {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  if (role === 'user') {
    return (
      <div className="border-l-2 border-zinc-800 pl-6 text-sm text-zinc-400" ref={ref}>
        {content}
      </div>
    );
  }

  // Преобразуем markdown в HTML и очищаем от потенциально опасного кода
  const rawHtml = marked.parse(content) as string;
  const cleanHtml = DOMPurify.sanitize(rawHtml, { USE_PROFILES: { html: true } });

  return (
    <div className="markdown-body" ref={ref}>
      <div dangerouslySetInnerHTML={{ __html: cleanHtml }} />
      {isStreaming && <span className="inline-block w-2 h-4 bg-cyan-400 animate-pulse ml-1" />}
    </div>
  );
};
