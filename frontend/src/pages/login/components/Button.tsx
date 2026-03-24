import React from 'react';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary';
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({ variant = 'primary', children, className = '', ...props }) => {
  const base = 'px-5 py-2.5 rounded-xl font-medium transition-all duration-200 cursor-pointer';
  const primary = 'bg-[#B87333] text-white shadow-sm hover:bg-[#a5662d] active:scale-[0.98]';
  const secondary = 'bg-transparent border border-[#E5E2DA] text-[#1E1E1E] hover:bg-white/80 active:scale-[0.98]';
  const variantClass = variant === 'primary' ? primary : secondary;

  return (
    <button className={`${base} ${variantClass} ${className}`} {...props}>
      {children}
    </button>
  );
};
