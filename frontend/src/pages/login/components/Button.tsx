import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({ variant = 'primary', children, className = '', ...props }) => {
  const base = 'inline-flex min-h-10 items-center justify-center rounded-lg px-4 py-2 text-sm font-medium leading-none transition-all duration-200 cursor-pointer active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25';
  const primary = 'bg-[var(--accent-primary)] text-white shadow-[var(--shadow-sm)] hover:bg-[var(--accent-hover)]';
  const secondary = 'bg-[var(--control-bg)] text-[var(--text-primary)] shadow-[var(--shadow-sm)] hover:bg-[var(--control-bg-hover)]';
  const variantClass = variant === 'primary' ? primary : secondary;

  return (
    <button className={`${base} ${variantClass} ${className}`} {...props}>
      {children}
    </button>
  );
};
