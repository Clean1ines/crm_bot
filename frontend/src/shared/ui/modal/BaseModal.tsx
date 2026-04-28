import React from 'react';

interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}

/**
 * Базовая модалка с затемнённым фоном и стеклянным эффектом.
 * Используется как основа для всех модальных окон в приложении.
 */
export const BaseModal: React.FC<BaseModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/15 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl bg-[var(--surface-elevated)] p-6 text-[var(--text-primary)] shadow-[var(--shadow-heavy)]">
        <h2 className="mb-4 text-xl font-bold text-[var(--text-primary)]">{title}</h2>
        {children}
        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="rounded-lg bg-[var(--control-bg)] px-3 py-1.5 text-xs font-semibold text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)]"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
