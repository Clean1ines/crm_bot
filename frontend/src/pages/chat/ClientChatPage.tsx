import React, { useState, useRef, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { streamFetch } from '@shared/api/client';

export const ClientChatPage: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const [messages, setMessages] = useState<Array<{ role: 'user' | 'assistant'; content: string }>>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const sendMessage = async () => {
    if (!input.trim() || isStreaming) return;
    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsStreaming(true);

    let assistantContent = '';
    setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

    await streamFetch(
      `/api/chat/projects/${projectId}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage }),
      },
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
        setIsStreaming(false);
      },
      (err) => {
        console.error('Stream error:', err);
        setMessages(prev => {
          const newMessages = [...prev];
          const lastIndex = newMessages.length - 1;
          if (newMessages[lastIndex]?.role === 'assistant') {
            newMessages[lastIndex] = { ...newMessages[lastIndex], content: 'Ошибка: не удалось получить ответ' };
          }
          return newMessages;
        });
        setIsStreaming(false);
      }
    );
  };

  return (
    <div className="flex flex-col h-screen">
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.map((msg, idx) => (
          <div key={idx} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[70%] rounded-lg p-2 ${msg.role === 'user' ? 'bg-blue-500 text-white' : 'bg-gray-200'}`}>
              {msg.content || (msg.role === 'assistant' && isStreaming && '...')}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="border-t p-4 flex">
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
          className="flex-1 border rounded-l px-3 py-2"
          placeholder="Введите сообщение..."
          disabled={isStreaming}
        />
        <button
          onClick={sendMessage}
          disabled={isStreaming}
          className="bg-blue-600 text-white px-4 py-2 rounded-r"
        >
          Отправить
        </button>
      </div>
    </div>
  );
};