import React from 'react';
import { Button } from './Button';

export const Navbar: React.FC = () => {
  return (
    <nav className="flex justify-between items-center py-4 px-6 md:px-12 border-b border-[#E5E2DA]">
      <div className="flex items-center gap-2">
        <div className="w-6 h-6 rounded-full bg-[#B87333]"></div>
        <span className="font-semibold text-[#1E1E1E] text-lg">Logo</span>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="secondary">Войти</Button>
        <Button variant="primary">Начать бесплатно</Button>
      </div>
    </nav>
  );
};
