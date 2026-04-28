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
      <p className="text-[var(--text-primary)] mb-4">
        Are you sure you want to delete {itemType}{' '}
        <span className="font-semibold text-[var(--accent-primary)]">"{itemName}"</span>? This action cannot be undone.
      </p>
      <div className="flex justify-end gap-2">
        <button
          onClick={handleConfirm}
          disabled={isPending}
          className="px-3 py-1.5 text-xs font-semibold rounded bg-[var(--accent-danger)] text-white hover:bg-[var(--accent-danger-text)] transition-colors disabled:opacity-30"
        >
          {isPending ? 'Deleting...' : 'Delete'}
        </button>
      </div>
    </BaseModal>
  );
};
