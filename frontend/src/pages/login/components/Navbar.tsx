import React from 'react';
import { Button } from './Button';

interface NavbarProps {
  onLoginClick?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({ onLoginClick }) => {
  return (
    <nav className="flex items-center justify-between px-4 py-4 shadow-[0_1px_0_var(--divider-soft)] sm:px-6 lg:px-8">
      <div className="flex items-center gap-2">
        <div className="h-6 w-6 rounded-full bg-[var(--accent-primary)] shadow-[var(--shadow-sm)]"></div>
        <span className="text-lg font-semibold tracking-tight text-[var(--text-primary)]">OMNICA</span>
      </div>
      <div className="flex items-center gap-3">
        <Button variant="secondary" onClick={onLoginClick}>Войти</Button>
      </div>
    </nav>
  );
};
