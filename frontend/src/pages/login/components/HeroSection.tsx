import React from 'react';

export const HeroSection: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1E1E1E] leading-tight">
        Ассистент, который отвечает клиентам за тебя
      </h1>
      <p className="text-lg text-[#6B6B6B]">
        Загрузи свои материалы — и он начнёт общаться как твой менеджер.
      </p>
    </div>
  );
};
