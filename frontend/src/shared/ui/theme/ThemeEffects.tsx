import React, { memo } from 'react';

const ThemeEffects: React.FC = () => {
  return (
    <div className="pointer-events-none fixed inset-0 z-[9999] overflow-hidden">
      {/* Сканлайны (CRT Lines) */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(18,16,16,0)_50%,rgba(0,0,0,0.25)_50%),linear-gradient(90deg,rgba(255,0,0,0.06),rgba(0,255,0,0.02),rgba(0,0,255,0.06))] bg-[length:100%_2px,3px_100%] opacity-[0.03] mix-blend-overlay" />

      {/* Виньетка и свечение */}
      <div className="absolute inset-0 shadow-[inset_0_0_100px_rgba(0,255,65,0.15)]" />

      {/* Анимированная полоса сканирования */}
      <div className="absolute h-[2px] w-full bg-green-500/10 animate-scanline will-change-transform" />
    </div>
  );
};

export default memo(ThemeEffects);