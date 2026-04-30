import React from 'react';

interface BaseModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  cancelLabel?: string;
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
  cancelLabel = 'Cancel',
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center bg-black/15 p-4 backdrop-blur-sm">
      <div className="w-full max-w-md rounded-2xl bg-[var(--surface-elevated)] p-4 text-[var(--text-primary)] shadow-[var(--shadow-heavy)] sm:p-6">
        <h2 className="mb-4 text-lg font-semibold leading-tight text-[var(--text-primary)]">{title}</h2>
        {children}
        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="min-h-9 rounded-lg bg-[var(--control-bg)] px-3 py-1.5 text-xs font-medium text-[var(--text-primary)] shadow-[var(--shadow-sm)] transition-colors hover:bg-[var(--control-bg-hover)] focus:outline-none focus:ring-2 focus:ring-[var(--accent-primary)]/25"
          >
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
};
