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
    <div className="fixed inset-0 bg-black bg-opacity-70 flex items-center justify-center z-[1100] p-4 backdrop-blur-[2px]">
      <div className="w-full max-w-md bg-[var(--ios-glass-dark)] backdrop-blur-[var(--blur-std)] border border-[var(--ios-border)] rounded-2xl shadow-[var(--shadow-heavy)] p-6">
        <h2 className="text-xl font-bold text-[var(--bronze-base)] mb-4">{title}</h2>
        {children}
        <div className="flex justify-end gap-2 mt-6">
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--ios-glass-dark)] border border-[var(--ios-border)] text-[var(--text-main)] hover:bg-[var(--ios-glass-bright)] transition-colors"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  );
};
