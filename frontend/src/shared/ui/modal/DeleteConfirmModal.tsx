import React from 'react';
import { BaseModal } from './BaseModal';

interface DeleteConfirmModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => Promise<void>;
  itemName: string;
  itemType: string;
  isPending?: boolean;
  projectName?: string;
}

export const DeleteConfirmModal: React.FC<DeleteConfirmModalProps> = ({
  isOpen,
  onClose,
  onConfirm,
  itemName,
  itemType,
  isPending = false,
}) => {
  const handleConfirm = async () => {
    await onConfirm();
  };

  return (
    <BaseModal isOpen={isOpen} onClose={onClose} title={`Delete ${itemType}`}>
      <p className="mb-4 text-sm leading-relaxed text-[var(--text-primary)]">
        Are you sure you want to delete {itemType}{' '}
        <span className="font-semibold text-[var(--accent-primary)]">"{itemName}"</span>? This action cannot be undone.
      </p>
      <div className="flex justify-end gap-2">
        <button
          onClick={handleConfirm}
          disabled={isPending}
          className="min-h-9 rounded-lg bg-[var(--accent-danger)] px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-[var(--accent-danger-text)] disabled:opacity-30 focus:outline-none focus:ring-2 focus:ring-[var(--accent-danger)]/25"
        >
          {isPending ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </BaseModal>
  );
};
