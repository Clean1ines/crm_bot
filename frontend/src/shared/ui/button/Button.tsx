import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost' | 'outline';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  isLoading,
  leftIcon,
  rightIcon,
  children,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex min-h-10 items-center justify-center gap-2 font-medium leading-none transition-all duration-200 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25';
  
  const variants = {
    primary: 'bg-[var(--accent-primary)] text-white shadow-[0_2px_10px_-3px_rgba(139,94,60,0.4)] hover:bg-[var(--accent-hover)] hover:shadow-[0_4px_15px_-3px_rgba(139,94,60,0.5)]',
    secondary: 'bg-[var(--control-bg)] text-[var(--text-primary)] shadow-[var(--shadow-sm)] hover:bg-[var(--control-bg-hover)]',
    danger: 'bg-[var(--accent-danger-bg)] text-[var(--accent-danger-text)] shadow-[var(--shadow-sm)] hover:bg-[var(--accent-danger-bg)]/80',
    ghost: 'bg-transparent text-[var(--text-secondary)] hover:bg-[var(--surface-secondary)] hover:text-[var(--text-primary)]',
    outline: 'bg-[var(--control-bg)] text-[var(--accent-primary)] shadow-[var(--shadow-sm)] hover:bg-[var(--control-bg-hover)]',
  };

  const sizes = {
    sm: 'min-h-8 rounded-lg px-3 py-1.5 text-xs',
    md: 'min-h-10 rounded-lg px-4 py-2 text-sm',
    lg: 'min-h-11 rounded-xl px-5 py-2.5 text-base',
  };

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && (
        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {!isLoading && leftIcon}
      {children}
      {!isLoading && rightIcon}
    </button>
  );
};
