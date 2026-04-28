import React from 'react';

export const HeroSection: React.FC = () => {
  return (
    <div className="space-y-4">
      <h1 className="text-3xl font-semibold leading-tight tracking-tight text-[var(--text-primary)] sm:text-4xl lg:text-5xl">
        Ассистент, который отвечает клиентам за тебя
      </h1>
      <p className="max-w-xl text-base leading-relaxed text-[var(--text-muted)] sm:text-lg">
        Загрузи свои материалы — и он начнёт общаться как твой менеджер.
      </p>
    </div>
  );
};
