import React from 'react';
import { Button } from './Button';

export const HeroSection: React.FC = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-[#1E1E1E] leading-tight">
        Ассистент, который отвечает клиентам за тебя
      </h1>
      <p className="text-lg text-[#6B6B6B]">
        Загрузи свои материалы — и он начнёт общаться как твой менеджер.
      </p>
      <div className="flex flex-wrap gap-4 pt-2">
        <Button variant="primary">Попробовать в чате</Button>
        <Button variant="secondary">Подключить бизнес</Button>
      </div>
    </div>
  );
};
