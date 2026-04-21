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
  const baseStyles = 'inline-flex items-center justify-center font-medium transition-all duration-200 active:scale-[0.98] disabled:opacity-50 disabled:pointer-events-none gap-2';
  
  const variants = {
    primary: 'bg-[--accent-primary] text-white shadow-[0_2px_10px_-3px_rgba(139,94,60,0.4)] hover:bg-[--accent-hover] hover:shadow-[0_4px_15px_-3px_rgba(139,94,60,0.5)]',
    secondary: 'bg-[--accent-muted]/20 text-[--accent-primary] hover:bg-[--accent-muted]/40 border border-[--accent-muted]/30',
    danger: 'bg-[--accent-danger-bg] text-[--accent-danger-text] hover:bg-[--accent-danger-border] border border-[--accent-danger-border]',
    ghost: 'bg-transparent text-[--text-secondary] hover:bg-[--surface-secondary] hover:text-[--text-primary]',
    outline: 'bg-transparent border border-[--accent-muted] text-[--accent-primary] hover:border-[--accent-primary] hover:bg-[--accent-muted]/10',
  };

  const sizes = {
    sm: 'px-3 py-1.5 text-xs rounded-[--radius-md]',
    md: 'px-5 py-2.5 text-sm rounded-[--radius-xl]',
    lg: 'px-8 py-3.5 text-base rounded-[--radius-2xl]',
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
